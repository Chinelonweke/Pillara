# scripts/generate_vapid_keys.py
#
# WHY VAPID KEYS:
# Web Push notifications (the browser-native "Pillara wants to send you
# notifications" prompt) require a VAPID key pair. VAPID identifies your
# server to the browser's push service (Chrome, Firefox, etc.) so it knows
# the push request is legitimately coming from Pillara and not an attacker.
#
# This is a ONE-TIME generation. Run it once, copy the two keys into
# Infisical, and never run it again — regenerating would invalidate every
# existing user's push subscription, forcing them to re-subscribe.

from py_vapid import Vapid01
import base64


def generate_vapid_keys() -> None:
    vapid = Vapid01()
    vapid.generate_keys()

    # py_vapid stores keys as cryptography library key objects —
    # we need them as base64url strings to use in HTTP headers and .env files
    public_key_bytes = vapid.public_key.public_bytes(
        encoding=__import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding"]).Encoding.X962,
        format=__import__("cryptography.hazmat.primitives.serialization", fromlist=["PublicFormat"]).PublicFormat.UncompressedPoint,
    )
    private_key_bytes = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")

    public_key_b64 = base64.urlsafe_b64encode(public_key_bytes).decode("utf-8").rstrip("=")
    private_key_b64 = base64.urlsafe_b64encode(private_key_bytes).decode("utf-8").rstrip("=")

    print("\nVAPID keys generated. Paste these into Infisical:\n")
    print(f"VAPID_PUBLIC_KEY={public_key_b64}")
    print(f"VAPID_PRIVATE_KEY={private_key_b64}")
    print("\nThis is a one-time generation — do not run this again once these are in use.")


if __name__ == "__main__":
    generate_vapid_keys()