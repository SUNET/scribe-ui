# Encryption of User Secrets

This document describes how Sunet Scribe protects sensitive data (e.g. the
user's encryption passphrase) that is stored in the session between page loads.

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Key Management](#key-management)
4. [Encryption Flow Step by Step](#encryption-flow-step-by-step)
5. [URL Encryption](#url-encryption)
6. [The Storage Class](#the-storage-class)
7. [Security Properties](#security-properties)
8. [Limitations and Considerations](#limitations-and-considerations)

---

## Overview

The application uses NiceGUI's built-in storage mechanisms:

| Storage              | Location                       | Lifetime              |
|----------------------|--------------------------------|-----------------------|
| `app.storage.browser`| Signed cookie in the browser   | Browser session       |
| `app.storage.user`   | Server filesystem or Redis     | Persistent per user   |

Sensitive values (defined in `SECRET_KEYS`) are encrypted with **AES-256-GCM**
before being written to `app.storage.user`. The encryption key is derived from
two independent secrets that are never stored together:

- **Browser key** (`_bk`) — a random token that only exists in the browser's
  signed cookie.
- **`STORAGE_SECRET`** — a server-side secret configured via environment variable.

Neither one alone is sufficient to decrypt any data.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                            Browser                                   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  Signed cookie (app.storage.browser)                         │    │
│  │  ┌───────────────────────────────────────────────────────┐   │    │
│  │  │  _bk = "random 32-byte token (url-safe base64)"       │   │    │
│  │  └───────────────────────────────────────────────────────┘   │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
                                │
                                │ Sent with every HTTP request
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                             Server                                   │
│                                                                      │
│  ┌───────────────────────────────┐   ┌────────────────────────────┐  │
│  │  Environment variable         │   │  app.storage.user          │  │
│  │  STORAGE_SECRET = "..."       │   │  (per user, disk/Redis)    │  │
│  └───────────────┬───────────────┘   │                            │  │
│                  │                   │  salt = "a3f2..."          │  │
│                  │                   │  _secret_encryption_       │  │
│                  │                   │    password = "base64..."  │  │
│                  │                   │  token = "jwt-plaintext"   │  │
│                  │                   └────────────────────────────┘  │
│                  │                              ▲                    │
│                  ▼                              │                    │
│         ┌────────────────────────────────────────-┐                  │
│         │         Key derivation (HKDF)           │                  │
│         │                                         │                  │
│         │  STORAGE_SECRET ──HKDF──► storage_salt  │                  │
│         │  _bk + storage_salt ──HKDF──► AES key   │                  │
│         │                                         │                  │
│         │         AES-256-GCM encryption          │                  │
│         │  plaintext + nonce + AAD ──► ciphertext │                  │
│         └────────────────────────────────────────-┘                  │
└──────────────────────────────────────────────────────────────────────┘
```

## Key Management

### Browser Key (`_bk`)

Generated on the first page load in `Storage.ensure_browser_key()`:

```python
app.storage.browser["_bk"] = secrets.token_urlsafe(32)
```

- **32 bytes** of entropy (256 bits), encoded as URL-safe base64.
- Stored only in `app.storage.browser`, which is a **signed cookie** managed
  by NiceGUI/Starlette. The cookie is signed with `STORAGE_SECRET` so that
  the client cannot tamper with it.
- **Never written to disk** on the server — it exists only in the HTTP
  response and in subsequent requests from the browser.
- Generated **once** per browser session and reused as long as the cookie
  persists.

### Salt

A 16-byte random salt is generated per user the first time a secret is
encrypted:

```python
salt = os.urandom(16)
app.storage.user["salt"] = salt.hex()
```

The salt is stored in plaintext in `app.storage.user` — it is not secret but
ensures that identical keys and passwords produce unique encryption keys for
different users.

### STORAGE_SECRET

A server-side secret configured via the `STORAGE_SECRET` environment variable.
It is used in two places:

1. **NiceGUI cookie signing** — to verify that `app.storage.browser` has not
   been tampered with.
2. **Key derivation** — as a second independent secret source in HKDF.

### Key Derivation (HKDF)

The final AES key is derived in two HKDF steps (HMAC-based Key Derivation
Function with SHA-256):

**Step 1 — Derive storage salt:**
```
HKDF(
    algorithm  = SHA-256
    length     = 32 bytes
    salt       = user's random salt (16 bytes)
    info       = b"storage-secret"
    ikm        = STORAGE_SECRET (UTF-8)
) → storage_salt (32 bytes)
```

**Step 2 — Derive AES key:**
```
HKDF(
    algorithm  = SHA-256
    length     = 32 bytes
    salt       = storage_salt (from step 1)
    info       = b"browser-storage"
    ikm        = _bk / browser key (UTF-8)
) → AES-256 key (32 bytes)
```

Both secrets (`_bk` and `STORAGE_SECRET`) are required independently.
Knowing only one of them reveals no information about the AES key.

## Encryption Flow Step by Step

### Encrypting (writing a secret)

The flow starts at `storage["encryption_password"] = "my-password"`:

```
1. Storage.__setitem__ detects that "encryption_password" ∈ SECRET_KEYS

2. The browser key (_bk) is retrieved from the cookie via app.storage.browser

3. _get_aesgcm(browser_key) is called:
   a. The salt is retrieved (or generated) from app.storage.user["salt"]
   b. HKDF step 1: STORAGE_SECRET → storage_salt
   c. HKDF step 2: _bk + storage_salt → 256-bit AES key
   d. AESGCM(key) is returned

4. _encrypt(value, browser_key, aad) is called:
   a. A 12-byte random nonce is generated: os.urandom(12)
   b. AES-256-GCM encrypts:
      - Plaintext: the password encoded as UTF-8
      - Nonce:     12 random bytes
      - AAD:       the key name ("encryption_password") encoded as UTF-8
   c. The result (nonce ‖ ciphertext ‖ GCM tag) is base64url-encoded

5. The encrypted value is stored in app.storage.user:
   app.storage.user["_secret_encryption_password"] = "<base64url>"
```

### Decrypting (reading a secret)

The flow starts at `storage.get("encryption_password")`:

```
1. Storage.get detects that "encryption_password" ∈ SECRET_KEYS

2. The browser key (_bk) is retrieved from the cookie
   → If missing, the default value (None) is returned

3. The encrypted value is retrieved:
   app.storage.user.get("_secret_encryption_password")
   → If missing, the default value (None) is returned

4. _decrypt(encrypted_value, browser_key, aad) is called:
   a. The base64url string is decoded
   b. The first 12 bytes are extracted as the nonce
   c. The remainder is ciphertext + GCM tag
   d. AES-256-GCM decrypts and verifies:
      - Integrity: the GCM tag verifies that ciphertext has not been tampered with
      - AAD:       the key name ("encryption_password") must match
   e. Plaintext is returned as a UTF-8 string

5. If decryption fails (wrong key, tampered data, mismatched AAD),
   the exception is caught and the default value is returned.
```

### Deletion

When `storage["encryption_password"] = None` or `del storage["encryption_password"]`:

```
1. The "_secret_encryption_password" entry is removed from app.storage.user
2. No cryptographic material needs to be cleared — the browser key
   remains in the cookie until the session ends
```

On logout (`/logout`), all secrets are explicitly set to `None`:

```python
storage["encryption_password"] = None
```

## URL Encryption

In addition to session secrets, the module provides `encrypt_for_url()` and
`decrypt_from_url()` for encrypting sensitive values that need to pass through
URL query parameters (e.g. in video proxy requests).

This mechanism differs from session secrets:

| Property            | Session secrets              | URL encryption                |
|---------------------|------------------------------|-------------------------------|
| Key sources         | _bk + STORAGE_SECRET         | STORAGE_SECRET only           |
| Purpose             | Protect data at rest         | Protect data in URL params    |
| Browser key required| Yes                          | No                            |
| Salt                | Per user, reused             | Per encryption, unique        |

**Ciphertext format:**
```
base64url( salt[16] ‖ nonce[12] ‖ ciphertext ‖ GCM-tag[16] )
```

The server can decrypt these values without access to the browser cookie
because the key is derived solely from `STORAGE_SECRET`.

## The Storage Class

The `Storage` class in `utils/storage.py` provides a unified dict-like
interface that automatically encrypts/decrypts secrets:

```python
from utils.storage import storage

# Non-secret values — written in plaintext to app.storage.user
storage["token"] = "jwt-token"
value = storage["token"]

# Secret values — automatically encrypted
storage["encryption_password"] = "my-password"     # encrypts
value = storage.get("encryption_password")          # decrypts

# Deletion
storage["encryption_password"] = None               # removes encrypted entry
del storage["token"]                                 # removes plaintext entry
```

### Which keys are encrypted?

Keys that belong to `SECRET_KEYS` are encrypted:

```python
SECRET_KEYS = frozenset({"encryption_password"})
```

All other keys are stored in plaintext in `app.storage.user`. To add more
secrets, simply extend this set.

### Methods

| Method                    | Behavior                                                      |
|---------------------------|---------------------------------------------------------------|
| `ensure_browser_key()`    | Creates `_bk` in the cookie if it does not exist              |
| `__setitem__(key, value)` | Encrypts if `key ∈ SECRET_KEYS`, otherwise plaintext          |
| `__getitem__(key)`        | Decrypts if `key ∈ SECRET_KEYS`, raises `KeyError` on failure |
| `get(key, default=None)`  | Like `__getitem__` but returns `default` on failure           |
| `__contains__(key)`       | Checks if the key exists (checks `_secret_` prefix)           |
| `__delitem__(key)`        | Removes encrypted or plaintext entry                          |

## Security Properties

### Dual-secret key derivation
Decryption requires that **both** secrets are available:
- **Browser key** — exists only in the client's cookie.
- **STORAGE_SECRET** — exists only on the server.

If the server's storage leaks (disk or Redis), an attacker cannot decrypt
data without also having access to the respective user's browser cookie.

### Authenticated encryption (AES-GCM)
AES-GCM provides both **confidentiality** and **integrity**:
- Ciphertext cannot be decrypted without the correct key.
- Any attempt to modify the ciphertext, nonce, or AAD is detected by the
  GCM tag and results in an `InvalidTag` exception.

### Additional Authenticated Data (AAD)
The key name (e.g. `"encryption_password"`) is passed as AAD during encryption.
AAD is not encrypted but is authenticated by the GCM tag. This prevents:

- **Key relocation** — ciphertext encrypted for the key `"encryption_password"`
  cannot be decrypted if it is copied to a different key
  (e.g. `"_secret_other_key"`), because the AAD will not match.

### Unique salt per user
Each user has their own random HKDF salt. Identical passwords for different
users produce entirely different AES keys and ciphertext.

### Random nonce per encryption
Each encryption call generates a fresh 12-byte nonce with `os.urandom(12)`.
This means the same plaintext encrypted at different times produces different
ciphertext, protecting against pattern recognition.

### Cookie signing
`app.storage.browser` is signed by NiceGUI/Starlette with `STORAGE_SECRET`.
The client cannot read or modify the cookie contents (including `_bk`) without
invalidating the signature.

## Limitations and Considerations

### Cookie lifetime
If the user clears their cookies, the browser key is lost. Secrets encrypted
with the old key can no longer be decrypted. `Storage.get()` handles this by
returning `default` on decryption failure, which in practice causes the
application to prompt the user to re-enter their encryption passphrase.

### STORAGE_SECRET rotation
If `STORAGE_SECRET` is changed, no existing secrets can be decrypted.
There is currently no migration mechanism — all users will need to re-enter
their encryption passphrases.

### Redis vs. file storage
With NiceGUI's default configuration, `app.storage.user` is written to JSON
files on disk. It is strongly recommended to use Redis without persistence
(`--save ''`) to avoid having encrypted secrets and salts written to permanent
storage. See `README.md` for Redis configuration.

### Thread safety
The `Storage` class holds no state of its own — all data is fetched from
NiceGUI's storage objects on every call. Thread safety therefore depends on
NiceGUI's own guarantees.

### Extending SECRET_KEYS
To encrypt additional keys, add them to `SECRET_KEYS`:

```python
SECRET_KEYS = frozenset({"encryption_password", "api_key", "other_secret"})
```

No other changes are required — the `Storage` class handles encryption and
decryption automatically based on this set.