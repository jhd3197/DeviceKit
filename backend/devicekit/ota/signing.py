"""Ed25519 release signing for OTA (plan 25 part 3).

The backend holds a private key and signs each release **manifest** (which pins the APK's
sha256); the agent verifies the manifest against a **pinned public key** before it ever
touches the downloaded bytes. Asymmetric on purpose: the agent never holds anything that
could forge a release, so a compromised device can't publish updates to its peers.

Greenfield — plan 29 (the shared signing plan) was never written, so OTA brings its own,
mirroring the HMAC helpers' shape in ``agent_device.py``. The manifest is serialized
canonically (sorted keys, no whitespace) so the same dict always signs/verifies to the same
bytes on both sides.
"""
import json
import os

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature


def canonical_bytes(manifest):
    """Deterministic serialization of a manifest dict for signing/verifying.

    The ``signature`` / ``public_key`` fields are excluded so a signed, distributed manifest
    (which carries them) round-trips to the exact bytes that were signed.
    """
    payload = {k: v for k, v in (manifest or {}).items()
               if k not in ("signature", "public_key")}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_or_create_private_key(path):
    """Return an Ed25519 private key, generating + persisting one (PEM, 0600) if absent.

    ``path``'s directory is created if needed. A freshly generated key is written before it
    is returned so a crash between generate and first sign can't leave releases signed by a
    key nobody can reproduce.
    """
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)
    key = Ed25519PrivateKey.generate()
    if path:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption())
        # Write private-then-restrict; best-effort chmod (no-op semantics on Windows).
        with open(path, "wb") as f:
            f.write(pem)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return key


def public_key_hex(private_key):
    """Raw 32-byte Ed25519 public key as hex — what the agent pins."""
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    return raw.hex()


def sign_manifest(private_key, manifest):
    """Return the hex Ed25519 signature over the canonical manifest bytes."""
    return private_key.sign(canonical_bytes(manifest)).hex()


def verify_manifest(public_key_hex_str, manifest, signature_hex):
    """True iff ``signature_hex`` is a valid signature over ``manifest`` for the given public
    key. Never raises — a malformed key/signature is a verification failure, not a crash."""
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex_str))
        pub.verify(bytes.fromhex(signature_hex), canonical_bytes(manifest))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
