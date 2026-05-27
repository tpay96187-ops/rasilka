from cryptography.fernet import Fernet
from backend.config import settings

_cipher = None

def get_cipher():
    global _cipher
    if _cipher is None:
        _cipher = Fernet(settings.encryption_key.encode())
    return _cipher

def encrypt_value(value: str) -> str:
    cipher = get_cipher()
    return cipher.encrypt(value.encode()).decode()

def decrypt_value(encrypted: str) -> str:
    cipher = get_cipher()
    return cipher.decrypt(encrypted.encode()).decode()