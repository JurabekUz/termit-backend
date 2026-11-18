import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def generate_totp_secret(num_bytes: int = 20) -> str:
    """Generate a Base32-encoded secret compatible with Google Authenticator."""
    raw = secrets.token_bytes(num_bytes)
    return base64.b32encode(raw).decode('ascii').rstrip('=')


def get_totp_uri(secret: str, account_name: str = 'super-access', issuer: str = 'Termit Academy') -> str:
    """Build an otpauth:// URI for provisioning into an authenticator app."""
    clean_secret = secret.strip().replace(' ', '').upper()
    label = f"{quote(issuer)}:{quote(account_name)}"
    return f"otpauth://totp/{label}?secret={clean_secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"


def _decode_base32_secret(secret: str) -> bytes:
    normalized = secret.strip().replace(' ', '').upper()
    padding = (-len(normalized)) % 8
    return base64.b32decode(normalized + ('=' * padding), casefold=True)


def compute_totp(secret: str, counter: int, digits: int = 6) -> str:
    """Compute an RFC 4226 / RFC 6238 HMAC-SHA1 TOTP code for a given counter."""
    key = _decode_base32_secret(secret)
    msg = struct.pack('>Q', counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code_int % (10 ** digits)).zfill(digits)


def verify_totp(
    secret: str,
    code: str,
    valid_window: int = 1,
    step_seconds: int = 30,
    now: float | None = None,
) -> tuple[bool, int | None]:
    """Verify a 6-digit TOTP code and return (is_valid, matched_time_step)."""
    clean_code = (code or '').strip().replace(' ', '')
    if len(clean_code) != 6 or not clean_code.isdigit() or not secret or not secret.strip():
        return False, None

    try:
        current_time = time.time() if now is None else now
        current_step = int(current_time // step_seconds)
        for offset in range(-valid_window, valid_window + 1):
            candidate_step = current_step + offset
            if candidate_step < 0:
                continue
            expected = compute_totp(secret, candidate_step)
            if hmac.compare_digest(clean_code, expected):
                return True, candidate_step
    except Exception:
        return False, None

    return False, None
