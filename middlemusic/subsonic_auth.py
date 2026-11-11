import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken


def encrypt_password(password: str, secret_key: str) -> str:
    key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode()).digest())
    return Fernet(key).encrypt(password.encode("utf-8")).decode("ascii")


def decrypt_password(encrypted_password: str | None, secret_key: str) -> str | None:
    if not encrypted_password:
        return None
    key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode()).digest())
    try:
        return Fernet(key).decrypt(encrypted_password.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError):
        return None


def verify_token(password: str, token: str, salt: str) -> bool:
    expected = hashlib.md5(f"{password}{salt}".encode()).hexdigest()
    return hmac.compare_digest(expected, token.lower())
