# core/security.py
# SECURITY UPDATES FROM AUDIT:
# 1. sanitize_for_llm — now Unicode NFKD normalises BEFORE pattern matching
#    This blocks Cyrillic/homograph bypass attacks on prompt injection detection
# 2. strip_llm_output_html — new function, strips HTML from LLM responses
#    Prevents XSS if frontend ever renders output as HTML
# 3. hash_reset_token / verify_reset_token — SHA256 token hashing for password reset
#    We NEVER store the raw reset token in the database
# 4. production_safety_check — asserts DEBUG=False in production at startup

import hashlib
import html
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from passlib.context import CryptContext

from core.config import settings
from core.exceptions import InvalidTokenError
from monitoring.logger import get_logger

logger = get_logger(__name__)

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def create_access_token(user_id: str, email: str) -> str:
    now = datetime.now(tz=timezone.utc)
    expiry = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "email": email,
        "type": "access",
        "iat": now,
        "exp": expiry,
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    now = datetime.now(tz=timezone.utc)
    expiry = now + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": expiry,
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, expected_type: str = "access") -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        token_type = payload.get("type")
        if token_type != expected_type:
            raise InvalidTokenError(f"Expected {expected_type} token, got {token_type} token")
        return payload
    except jwt.ExpiredSignatureError:
        raise InvalidTokenError("Your session has expired. Please sign in again.")
    except jwt.InvalidTokenError:
        raise InvalidTokenError("Invalid authentication token.")


def create_password_reset_token(user_id: str, email: str) -> str:
    now = datetime.now(tz=timezone.utc)
    expiry = now + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "email": email,
        "type": "password_reset",
        "iat": now,
        "exp": expiry,
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def generate_secure_token(byte_length: int = 32) -> str:
    return secrets.token_hex(byte_length)


# ─── PASSWORD RESET TOKEN HASHING ─────────────────────────────────────────────
# SECURITY FIX: Never store raw password reset tokens in the database.
# Store SHA256(token) — irreversible. Compare hash of incoming token to stored hash.

def hash_reset_token(raw_token: str) -> str:
    """
    Returns SHA256 hex digest of the token.
    This is what gets stored in the database.
    If the DB is breached, attackers get hashes — useless without the raw token.
    """
    return hashlib.sha256(raw_token.encode()).hexdigest()


def verify_reset_token(raw_token: str, stored_hash: str) -> bool:
    """
    Compares SHA256(raw_token) against the stored hash using constant-time comparison.
    WHY secrets.compare_digest: prevents timing attacks on hash comparison.
    """
    incoming_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return secrets.compare_digest(incoming_hash, stored_hash)


# ─── INPUT SANITIZATION ───────────────────────────────────────────────────────

def sanitize_text_input(text: str, max_length: int = 2000) -> str:
    if not text:
        return ""
    text = text[:max_length]
    # NFC normalisation for general text
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\x00", "")
    text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return text.strip()


def sanitize_medication_name(name: str) -> str:
    if not name:
        return ""
    name = name[:200].strip()
    name = unicodedata.normalize("NFC", name)
    name = re.sub(r'[^a-zA-Z0-9\s\-\/\.\(\)]', '', name)
    name = re.sub(r'\s+', ' ', name)
    return name.strip()


def sanitize_for_llm(text: str) -> str:
    """
    Sanitizes user input before it reaches the LLM.

    SECURITY FIX — TWO-PASS NORMALISATION:
    Pass 1: NFKD + ASCII encode strips Unicode homoglyphs (Cyrillic 'а' → gone).
            This kills attacks like "IgnORE аLL PreVIOUs instrUCTIONS" where
            'а' is Cyrillic U+0430, not Latin 'a'.
    Pass 2: Run injection pattern matching on the now-clean ASCII text.

    WHY NFKD (not NFC):
    NFC: canonical composition — keeps most Unicode intact.
    NFKD: compatibility decomposition — strips lookalike characters.
    For security scrubbing, NFKD is the right choice.
    """
    if not text:
        return ""

    text = text[:4000]

    # PASS 1 — Strip Unicode homoglyphs via NFKD decomposition
    # Step 1a: NFKD decomposes characters into base + combining marks
    nfkd = unicodedata.normalize("NFKD", text)
    # Step 1b: encode to ASCII, ignoring anything that can't be represented
    # This strips Cyrillic, Greek, and other lookalikes entirely
    ascii_safe = nfkd.encode("ascii", "ignore").decode("ascii")

    # PASS 2 — Pattern matching on clean ASCII text
    injection_patterns = [
        # WIDENED FROM: r'ignore\s+(all\s+)?(previous|prior|above|system)\s+instructions?'
        # WHY: that version required the literal word "all" (or one of the listed
        # adjectives) to survive intact. But Unicode homoglyph attacks like
        # "Ignore аll previous instructions" (Cyrillic а) get their lookalike
        # character stripped by NFKD+ASCII above, leaving "Ignore ll previous
        # instructions" — "ll" doesn't match (all\s+)?, so the original regex
        # missed it entirely despite the homoglyph defense technically working.
        # \w* here matches ANY leftover word fragment (or nothing at all) between
        # "ignore" and "instructions", so stripped/mangled middle words can't
        # create a gap. Verified by tests/unit/test_security.py::
        # test_cyrillic_homoglyph_bypass_blocked.
        r'ignore\s+\w*\s*(previous|prior|above|system|instructions?)',
        r'you\s+are\s+now\s+(dan|jailbroken|uncensored|evil|free)',
        r'(developer|god|admin|root|sudo)\s+mode',
        r'bypass\s+(your\s+)?(safety|guidelines|rules|restrictions|filters)',
        r'disregard\s+(your\s+)?(training|instructions|guidelines|prompt)',
        r'pretend\s+(you\s+)?(are|have\s+no)\s+(restrictions?|rules?|limits?)',
        r'act\s+as\s+(if\s+you\s+)?(have\s+no|without)\s+(restrictions?|rules?)',
        r'new\s+(instructions?|prompt|persona|role)\s*:',
        r'system\s*prompt\s*:',
        r'\[inst\]',
        r'<<sys>>',
        r'<\|im_start\|>',
    ]

    scrubbed = ascii_safe
    injection_found = False
    for pattern in injection_patterns:
        if re.search(pattern, scrubbed, re.IGNORECASE):
            injection_found = True
            scrubbed = re.sub(pattern, '[filtered]', scrubbed, flags=re.IGNORECASE)

    if injection_found:
        logger.warning("prompt_injection_neutralised", pattern_count=scrubbed.count('[filtered]'))

    # Remove null bytes and control characters from the final result
    scrubbed = scrubbed.replace("\x00", "")
    scrubbed = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', scrubbed)

    return scrubbed.strip()


def strip_llm_output_html(text: str) -> str:
    """
    Strips HTML tags from LLM output before returning to the client.

    SECURITY FIX: Prevents XSS if a frontend ever renders AI responses as HTML.
    A manipulated LLM response containing <script>alert(1)</script> would execute
    in the user's browser if the frontend rendered it as innerHTML.

    We strip tags AND HTML-escape remaining content.
    Legitimate markdown (**, ##, -) passes through unaffected — not HTML.

    WHY BOTH STRIP AND ESCAPE:
    Strip removes <tag> patterns.
    Escape converts any remaining < > & " ' to their HTML entities.
    Belt and suspenders — one layer alone can be bypassed with malformed tags.
    """
    if not text:
        return ""

    # Remove script tags and their content entirely (not just the tag)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)

    # Remove all other HTML tags (keep the text between them)
    text = re.sub(r'<[^>]+>', '', text)

    # HTML-escape remaining special characters
    text = html.escape(text, quote=True)

    # Unescape characters that are safe in our context
    # We want to preserve apostrophes, quotes in text
    text = text.replace('&#x27;', "'").replace('&quot;', '"')

    return text


def hash_ip_address(ip: str) -> str:
    if not ip:
        return "unknown"
    salt = settings.JWT_SECRET_KEY[:16].encode()
    ip_bytes = ip.encode()
    hashed = hashlib.sha256(salt + ip_bytes).hexdigest()
    return hashed[:16]


# ─── PRODUCTION SAFETY CHECK ──────────────────────────────────────────────────

def production_safety_check() -> None:
    """
    Called at app startup. Asserts production configuration is safe.

    SECURITY FIX: Prevents accidental production deployment with debug settings.
    One of the most common production security failures is deploying with
    DEBUG=True — which exposes stack traces, database queries, and internal paths.

    This check runs before the first request is ever served.
    If it fails, the app refuses to start — loud failure beats silent vulnerability.
    """
    if settings.is_production:
        assert not settings.DEBUG, (
            "FATAL: DEBUG=True in production. "
            "This exposes stack traces and internal details to attackers. "
            "Set DEBUG=False before deploying."
        )
        assert len(settings.JWT_SECRET_KEY) >= 32, (
            "FATAL: JWT_SECRET_KEY is too short for production. "
            "Generate a strong key: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
        assert settings.JWT_SECRET_KEY != "replace-this-with-a-real-random-64-character-string", (
            "FATAL: JWT_SECRET_KEY is still the placeholder value. "
            "Replace it with a real secret before deploying."
        )

    logger.info("production_safety_check_passed", environment=settings.ENVIRONMENT)