# AIOS Credential Management

AIOS includes a secure credential storage system for managing passwords, API keys, and other secrets used by plugins.

## Overview

The credential system provides:
- **Encrypted Storage**: Credentials are encrypted at rest using Fernet (AES-128-CBC)
- **Master Password**: A single password protects all stored credentials
- **Key Derivation**: PBKDF2-HMAC-SHA256 with 480,000 iterations
- **Plugin Integration**: Plugins can securely store and retrieve credentials
- **Shell Commands**: Manage credentials from the AIOS shell

## How It Works

### Encryption Architecture

```
Master Password
       │
       ▼
┌──────────────────────┐
│  PBKDF2-HMAC-SHA256  │◄──── Random 16-byte salt
│  480,000 iterations  │
└──────────┬───────────┘
           │
           ▼
     Encryption Key
           │
           ▼
┌──────────────────────┐
│   Fernet Encryption  │──── AES-128-CBC + HMAC-SHA256
│   (encrypt/decrypt)  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  credentials.enc     │──── [16-byte salt][encrypted data]
│  ~/.config/aios/     │
└──────────────────────┘
```

### Storage Location

```
~/.config/aios/credentials.enc
```

The file is created with `0600` permissions (owner read/write only).

### File Format

The encrypted file contains:
- **Bytes 0-15**: Random salt (generated once on creation)
- **Bytes 16+**: Fernet-encrypted JSON payload

## Shell Commands

### List Credentials

```
credentials
```
or
```
/credentials
```

Shows stored credential names (values are never displayed):

```
Stored Credentials

  ● github
    user: maciej, password: ****, api_key: ****

  ● ansible-router
    user: admin, password: ****

  ● aws
    api_key: ****, extra: 2 fields

Use 'credential add <name>' or 'credential delete <name>' to manage.
```

## Credential Data Model

Each credential can store:

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique identifier for the credential |
| `username` | string (optional) | Username or login ID |
| `password` | string (optional) | Password or secret |
| `api_key` | string (optional) | API key or token |
| `extra` | dict (optional) | Additional key-value pairs |

## Python API

### Quick Functions

```python
from aios.credentials import (
    store_credential,
    get_credential,
    delete_credential,
    list_credentials,
)

# Store a credential
store_credential(
    name="my-service",
    username="admin",
    password="s3cret",
    api_key="sk-abc123",
    region="us-east-1",        # Extra fields via **kwargs
    endpoint="https://api.example.com"
)

# Retrieve a credential
cred = get_credential("my-service")
if cred:
    print(cred.username)       # "admin"
    print(cred.password)       # "s3cret"
    print(cred.api_key)        # "sk-abc123"
    print(cred.extra["region"])  # "us-east-1"

# List all credential names
names = list_credentials()     # ["my-service", "github", ...]

# Delete a credential
delete_credential("my-service")
```

### CredentialStore Class

For more control, use the `CredentialStore` class directly:

```python
from aios.credentials import CredentialStore
from pathlib import Path

# Create with custom path
store = CredentialStore(store_path=Path("/custom/path/creds.enc"))

# Initialize with master password
store.initialize(master_password="my-master-pass")

# CRUD operations
store.set("service", username="user", password="pass")
cred = store.get("service")
store.delete("service")
names = store.list()

# Check existence
if store.exists("service"):
    print("Credential exists")
```

### Plugin Integration

Plugins can use credentials to authenticate with external services:

```python
from aios.plugins import PluginBase
from aios.credentials import get_credential, store_credential

class MyNetworkPlugin(PluginBase):
    def _handle_connect(self, params):
        device = params["device"]

        # Try to get stored credentials
        cred = get_credential(f"device-{device}")

        if cred is None:
            # Prompt user to provide credentials
            return {
                "success": False,
                "message": f"No credentials stored for {device}. "
                           f"Use '/credentials' to add them."
            }

        # Use credentials to connect
        connection = connect_to_device(
            host=device,
            username=cred.username,
            password=cred.password
        )

        return {"success": True, "output": f"Connected to {device}"}
```

## Security Considerations

### Strengths

- **PBKDF2 with 480,000 iterations**: Resistant to brute-force attacks on the master password
- **Random salt**: Prevents rainbow table attacks
- **Fernet encryption**: Provides authenticated encryption (AES-CBC + HMAC-SHA256)
- **File permissions**: `0600` ensures only the file owner can access the credential store
- **No plaintext**: Credentials are never written to disk in plaintext

### Limitations

- **Master password quality**: Security depends on master password strength. Use a strong, unique password
- **In-memory exposure**: Decrypted credentials exist in memory during the session
- **Single-user**: The credential store is per-user, not suitable for multi-user scenarios
- **No key rotation**: The encryption key is derived from the master password; changing it requires re-encrypting all credentials

### Best Practices

1. **Strong master password**: Use at least 12 characters with mixed case, numbers, and symbols
2. **Don't share the credential file**: Keep `~/.config/aios/credentials.enc` private
3. **Back up carefully**: If you back up credentials, ensure the backup is also encrypted
4. **Rotate credentials**: Periodically update stored passwords and API keys
5. **Minimal storage**: Only store credentials that plugins actually need
