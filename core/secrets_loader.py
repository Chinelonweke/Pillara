# core/secrets_loader.py
import os

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
    "ALERT_FROM_EMAIL": "ALERT_FROM_EMAIL",
    "ALERT_EMAIL": "ALERT_EMAIL",
    "FRONTEND_URL": "FRONTEND_URL",
    "FROM_EMAIL": "FROM_EMAIL",
    "ENVIRONMENT": "ENVIRONMENT",
    "DEBUG": "DEBUG",
    "REDIS_URL": "REDIS_URL",
    "CHROMA_HOST": "CHROMA_HOST",
    "CHROMA_PORT": "CHROMA_PORT",
    "ALLOWED_ORIGINS": "ALLOWED_ORIGINS",
    "VAPID_PUBLIC_KEY": "VAPID_PUBLIC_KEY",
    "VAPID_PRIVATE_KEY": "VAPID_PRIVATE_KEY",
    "AT_USERNAME": "AT_USERNAME",
    "AT_API_KEY": "AT_API_KEY",
    "SENTRY_DSN": "SENTRY_DSN",
    "POSTHOG_API_KEY": "POSTHOG_API_KEY",
}


def load_secrets_from_infisical() -> None:
    from infisical_sdk import InfisicalSDKClient

    client_id = os.getenv("INFISICAL_CLIENT_ID")
    client_secret = os.getenv("INFISICAL_CLIENT_SECRET")
    project_id = os.getenv("INFISICAL_PROJECT_ID")
    infisical_environment = os.getenv("INFISICAL_ENVIRONMENT", "dev")
    site_url = os.getenv("INFISICAL_SITE_URL", "https://app.infisical.com")

    if not all([client_id, client_secret, project_id]):
        raise RuntimeError(
            "USE_INFISICAL=true but INFISICAL_CLIENT_ID, INFISICAL_CLIENT_SECRET, "
            "or INFISICAL_PROJECT_ID is missing."
        )

    try:
        client = InfisicalSDKClient(host=site_url)
        client.auth.universal_auth.login(client_id=client_id, client_secret=client_secret)

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
            print(f"[secrets_loader] WARNING: these optional secrets were not found in Infisical: {missing}")

    except Exception as error:
        print(f"[secrets_loader] ERROR: failed to connect to Infisical: {error}")
        raise RuntimeError(f"Could not load secrets from Infisical: {error}")