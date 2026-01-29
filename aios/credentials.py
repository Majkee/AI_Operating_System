"""
Credential management for AIOS skills.

Provides secure storage and retrieval of credentials like
passwords, API keys, and SSH keys for skills.
"""

import os
import json
import base64
import hashlib
import getpass
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, field
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


@dataclass
class Credential:
    """A stored credential."""
    name: str
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    extra: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "username": self.username,
            "password": self.password,
            "api_key": self.api_key,
            "extra": self.extra
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Credential":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            username=data.get("username"),
            password=data.get("password"),
            api_key=data.get("api_key"),
            extra=data.get("extra", {})
        )


class CredentialStore:
    """Secure credential storage for AIOS skills."""

    def __init__(self, store_path: Optional[Path] = None):
        """Initialize the credential store."""
        self.store_path = store_path or (
            Path.home() / ".config" / "aios" / "credentials.enc"
        )
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

        self._credentials: Dict[str, Credential] = {}
        self._fernet: Optional[Fernet] = None
        self._initialized = False

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """Derive encryption key from password."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key

    def initialize(self, master_password: Optional[str] = None) -> bool:
        """
        Initialize the credential store.

        If no master password provided, prompts for one.
        Returns True if successful.
        """
        if self._initialized:
            return True

        # Check if store exists
        if self.store_path.exists():
            return self._load_store(master_password)
        else:
            return self._create_store(master_password)

    def _create_store(self, master_password: Optional[str] = None) -> bool:
        """Create a new credential store."""
        if master_password is None:
            print("Creating new credential store.")
            master_password = getpass.getpass("Enter master password: ")
            confirm = getpass.getpass("Confirm master password: ")
            if master_password != confirm:
                print("Passwords do not match.")
                return False

        # Generate salt and derive key
        salt = os.urandom(16)
        key = self._derive_key(master_password, salt)
        self._fernet = Fernet(key)

        # Save empty store with salt
        self._save_store(salt)
        self._initialized = True
        return True

    def _load_store(self, master_password: Optional[str] = None) -> bool:
        """Load existing credential store."""
        try:
            with open(self.store_path, 'rb') as f:
                data = f.read()

            # Extract salt (first 16 bytes)
            salt = data[:16]
            encrypted_data = data[16:]

            if master_password is None:
                master_password = getpass.getpass("Enter master password: ")

            # Derive key and decrypt
            key = self._derive_key(master_password, salt)
            self._fernet = Fernet(key)

            decrypted = self._fernet.decrypt(encrypted_data)
            store_data = json.loads(decrypted.decode())

            # Load credentials
            self._credentials = {
                name: Credential.from_dict(cred_data)
                for name, cred_data in store_data.get("credentials", {}).items()
            }

            self._initialized = True
            return True

        except Exception as e:
            print(f"Failed to load credential store: {e}")
            return False

    def _save_store(self, salt: Optional[bytes] = None) -> bool:
        """Save credential store to disk."""
        if not self._fernet:
            return False

        try:
            # Serialize credentials
            store_data = {
                "credentials": {
                    name: cred.to_dict()
                    for name, cred in self._credentials.items()
                }
            }

            # Encrypt
            encrypted = self._fernet.encrypt(json.dumps(store_data).encode())

            # Read existing salt if not provided
            if salt is None and self.store_path.exists():
                with open(self.store_path, 'rb') as f:
                    salt = f.read(16)
            elif salt is None:
                salt = os.urandom(16)

            # Write salt + encrypted data
            with open(self.store_path, 'wb') as f:
                f.write(salt + encrypted)

            # Secure file permissions (owner read/write only)
            os.chmod(self.store_path, 0o600)

            return True

        except Exception as e:
            print(f"Failed to save credential store: {e}")
            return False

    def set(
        self,
        name: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        api_key: Optional[str] = None,
        **extra
    ) -> bool:
        """Store a credential."""
        if not self._initialized:
            if not self.initialize():
                return False

        self._credentials[name] = Credential(
            name=name,
            username=username,
            password=password,
            api_key=api_key,
            extra=extra
        )

        return self._save_store()

    def get(self, name: str) -> Optional[Credential]:
        """Retrieve a credential by name."""
        if not self._initialized:
            if not self.initialize():
                return None

        return self._credentials.get(name)

    def delete(self, name: str) -> bool:
        """Delete a credential."""
        if not self._initialized:
            if not self.initialize():
                return False

        if name in self._credentials:
            del self._credentials[name]
            return self._save_store()
        return False

    def list(self) -> list[str]:
        """List all credential names."""
        if not self._initialized:
            if not self.initialize():
                return []

        return list(self._credentials.keys())

    def exists(self, name: str) -> bool:
        """Check if a credential exists."""
        if not self._initialized:
            return False
        return name in self._credentials


# Global credential store instance
_credential_store: Optional[CredentialStore] = None


def get_credential_store() -> CredentialStore:
    """Get the global credential store instance."""
    global _credential_store
    if _credential_store is None:
        _credential_store = CredentialStore()
    return _credential_store


def store_credential(
    name: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
    api_key: Optional[str] = None,
    **extra
) -> bool:
    """Store a credential in the global store."""
    return get_credential_store().set(
        name=name,
        username=username,
        password=password,
        api_key=api_key,
        **extra
    )


def get_credential(name: str) -> Optional[Credential]:
    """Get a credential from the global store."""
    return get_credential_store().get(name)


def delete_credential(name: str) -> bool:
    """Delete a credential from the global store."""
    return get_credential_store().delete(name)


def list_credentials() -> list[str]:
    """List all stored credential names."""
    return get_credential_store().list()
