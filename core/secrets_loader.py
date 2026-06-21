# core/secrets_loader.py
#
# WHY A SEPARATE FILE (not inline in config.py):
# config.py defines WHAT settings exist. This file defines WHERE secrets
# come from in production. Keeping them separate means config.py stays
# testable and simple — it never imports the Infisical SDK, never makes
# a network call, never depends on credentials being present.
# Only this file knows Infisical exists.
#
# WHY INFISICAL (over .env in production):
# .env files sitting on a production server are a liability:
#   - if the server is compromised, every secret is sitting in plaintext on disk
#   - there's no audit trail of who read which secret, or when
#   - rotating a secret means SSHing in and editing a file by hand
#   - there's no central place to manage secrets across multiple servers/environments
# Infisical solves all four: secrets are stored encrypted, fetched at runtime
# over an authenticated API call, every fetch is logged, and rotating a secret
# means changing it once in the Infisical dashboard — every server picks up
# the new value on next restart (or live, if using their secret-watching SDK).
#
# WHY MACHINE IDENTITY (not a personal login):
# Infisical supports two ways to authenticate: a human logging in via browser,
# or a "machine identity" — a client ID + client secret pair created specifically
# for a server to authenticate itself, with no human involved. We use machine
# identity here because this code runs unattended on a server at startup.
# Treat INFISICAL_CLIENT_SECRET exactly like a master password — it unlocks
# every other secret in the project.

import os

# WHY NOT monitoring.logger HERE:
# This module runs INSIDE core/config.py's get_settings(), before settings
# has finished being constructed. monitoring/logger.py imports `settings`
# from core.config to configure itself — importing it here would create a
# circular import (config -> secrets_loader -> logger -> config, which
# hasn't finished building `settings` yet). This module runs once, early,
# at startup, so plain print() is the correct tool here, not the structured
# logger the rest of the app uses once it's fully initialized.

# Maps: Infisical secret key name -> environment variable name our app expects.
# WHY A MAPPING (not assuming they're identical):
# This makes it explicit and auditable exactly which secrets we pull and
# where they land. If you store a secret in Infisical under a different
# name than the env var Pillara expects, this is the only place to reconcile that.
SECRETS_MAP: dict = {
    "DATABASE_URL": "DATABASE_URL",
    "REDIS_URL": "REDIS_URL",
    "JWT_SECRET_KEY": "JWT_SECRET_KEY",
    "GROQ_API_KEY": "GROQ_API_KEY",
    "CEREBRAS_API_KEY": "CEREBRAS_API_KEY",
    "OPENROUTER_API_KEY": "OPENROUTER_API_KEY",
    "TOGETHER_API_KEY": "TOGETHER_API_KEY",
    "HUGGINGFACE_API_KEY": "HUGGINGFACE_API_KEY",
    "FDA_API_KEY": "FDA_API_KEY",
    "RESEND_API_KEY": "RESEND_API_KEY",
    "TELEGRAM_BOT_TOKEN": "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID": "TELEGRAM_CHAT_ID",
    "VAPID_PUBLIC_KEY": "VAPID_PUBLIC_KEY",
    "VAPID_PRIVATE_KEY": "VAPID_PRIVATE_KEY",
    "AT_USERNAME": "AT_USERNAME",
    "AT_API_KEY": "AT_API_KEY",
    "SENTRY_DSN": "SENTRY_DSN",
    "POSTHOG_API_KEY": "POSTHOG_API_KEY",
}


def load_secrets_from_infisical() -> None:
    """
    Fetches all secrets from Infisical and injects them into os.environ.
    Called once at startup, before Settings() is constructed.

    WHY INJECT INTO os.environ (rather than returning a dict):
    Settings() (Pydantic BaseSettings) already knows how to read os.environ —
    that's its whole job. Injecting into os.environ means we don't have to
    teach Settings() anything new about Infisical. It just sees environment
    variables that happen to already be populated by the time it runs.

    FAILS LOUD: if Infisical is unreachable or auth fails, we raise immediately.
    A silent failure here means the app starts with missing secrets and crashes
    confusingly later, deep inside whichever service needed that secret first.
    Better to fail clearly at startup: "cannot reach secrets manager."
    """
    from infisical_sdk import InfisicalSDKClient
    # WHY infisical_sdk (with underscore) HERE, but infisicalsdk (no underscore)
    # in requirements.txt:
    # These are two genuinely different things that happen to look similar.
    # The PyPI *package name* (what you `pip install`) is "infisicalsdk".
    # The *importable module name* inside that package is "infisical_sdk".
    # This mismatch is a real quirk of how Infisical packaged this SDK —
    # confirmed by inspecting the actual .whl file contents, which contain
    # a folder named infisical_sdk/, not infisicalsdk/.

    client_id = os.getenv("INFISICAL_CLIENT_ID")
    client_secret = os.getenv("INFISICAL_CLIENT_SECRET")
    project_id = os.getenv("INFISICAL_PROJECT_ID")
    infisical_environment = os.getenv("INFISICAL_ENVIRONMENT", "dev")
    site_url = os.getenv("INFISICAL_SITE_URL", "https://app.infisical.com")

    if not all([client_id, client_secret, project_id]):
        raise RuntimeError(
            "USE_INFISICAL=true but INFISICAL_CLIENT_ID, INFISICAL_CLIENT_SECRET, "
            "or INFISICAL_PROJECT_ID is missing. These three values must be set "
            "as plain environment variables on the server itself (e.g. in your "
            "systemd unit file or Docker run command) — they are the keys used "
            "to unlock everything else, so they can't live inside Infisical."
        )

    try:
        client = InfisicalSDKClient(host=site_url)
        # Machine identity login — no human, no browser, just client credentials
        client.auth.universal_auth.login(
            client_id=client_id,
            client_secret=client_secret,
        )

        secrets_response = client.secrets.list_secrets(
            project_id=project_id,
            environment_slug=infisical_environment,
            secret_path="/",
        )

        fetched_keys = {secret.secretKey: secret.secretValue for secret in secrets_response.secrets}

        loaded_count = 0
        missing = []

        for infisical_key, env_var_name in SECRETS_MAP.items():
            if infisical_key in fetched_keys:
                os.environ[env_var_name] = fetched_keys[infisical_key]
                loaded_count += 1
            else:
                missing.append(infisical_key)

        print(f"[secrets_loader] Loaded {loaded_count} secrets from Infisical (environment: {infisical_environment})")

        if missing:
            # WHY WARN (not raise) ON MISSING SECRETS:
            # Some secrets are genuinely optional (e.g. AT_API_KEY if you
            # haven't set up SMS yet). Settings() itself will raise if a
            # REQUIRED field like DATABASE_URL or JWT_SECRET_KEY is still
            # missing after this — that's the right place for a hard failure,
            # since Settings() is the one source of truth on what's required.
            print(f"[secrets_loader] WARNING: these optional secrets were not found in Infisical: {missing}")

    except Exception as error:
        print(f"[secrets_loader] ERROR: failed to connect to Infisical: {error}")
        raise RuntimeError(
            f"Could not load secrets from Infisical: {error}. "
            f"Check INFISICAL_CLIENT_ID/SECRET are valid and the project "
            f"is reachable at {site_url}."
        )