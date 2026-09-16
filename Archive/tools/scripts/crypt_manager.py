import os
import sys
import keyring
from cryptography.fernet import Fernet
from dotenv import load_dotenv

FoveAI_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
ENV_PATH = os.path.join(FoveAI_ROOT, ".env")

load_dotenv(ENV_PATH)

def get_or_create_key():
    # 1. Try to fetch from .env
    key = os.getenv("FoveAI_VAULT_KEY")
    
    # 2. If missing, try to fetch from Windows Credential Manager
    if not key:
        try:
            key = keyring.get_password("Lumax", "VaultKey")
            if key:
                print("[Vault] Recovered Master Key from Windows Credential Manager.")
                # Restore to .env
                with open(ENV_PATH, "a") as f:
                    f.write(f"\nFoveAI_VAULT_KEY={key}\n")
                os.environ["FoveAI_VAULT_KEY"] = key
        except Exception as e:
            print(f"[Vault] Failed to query Credential Manager: {e}")

    # 3. If still missing, generate a new one
    if not key:
        print("[Vault] Generating new AES-256 Master Key...")
        key = Fernet.generate_key().decode('utf-8')
        # Save to .env
        with open(ENV_PATH, "a") as f:
            f.write(f"\nFoveAI_VAULT_KEY={key}\n")
        os.environ["FoveAI_VAULT_KEY"] = key
        
        # Save to Windows Credential Manager
        try:
            keyring.set_password("Lumax", "VaultKey", key)
            print("[Vault] Key securely injected into Windows Credential Manager.")
        except Exception as e:
            print(f"[Vault] Failed to save to Credential Manager: {e}")

    return key.encode('utf-8')

_cipher_suite = None

def _get_cipher():
    global _cipher_suite
    if _cipher_suite is None:
        key = get_or_create_key()
        _cipher_suite = Fernet(key)
    return _cipher_suite

def encrypt(data: str) -> str:
    """Encrypts a string and returns a base64 encoded token string."""
    if not data:
        return data
    cipher = _get_cipher()
    return cipher.encrypt(data.encode('utf-8')).decode('utf-8')

def decrypt(token: str) -> str:
    """Decrypts a base64 encoded token string back to plain text."""
    if not token:
        return token
    # If the text doesn't look like a fernet token (e.g. legacy plain text), return it
    if not token.startswith("gAAAAAB"):
        return token
    try:
        cipher = _get_cipher()
        return cipher.decrypt(token.encode('utf-8')).decode('utf-8')
    except Exception as e:
        print(f"[Vault] Decryption failed: {e}")
        return token
