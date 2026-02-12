# Vault & Secrets

> AES-256-GCM encryption for `.env` files and project secrets.

---

## Overview

The vault encrypts sensitive files (`.env`, credentials, tokens) so they can be
safely committed to version control. The encrypted file (`.env.vault`) replaces
the plaintext original.

## How It Works

```
.env (plaintext)
    │
    ▼  Lock (passphrase)
.env.vault (AES-256-GCM encrypted)
    │
    ▼  Unlock (passphrase)
.env (plaintext restored)
```

### Encryption Specs

| Property | Value |
|----------|-------|
| Algorithm | AES-256-GCM |
| Key derivation | PBKDF2-SHA256 |
| KDF iterations | 480,000 (standard), 600,000 (portable exports) |
| Salt | 16 bytes random |
| IV | 12 bytes random |
| Auth tag | 16 bytes (GCM) |
| Secure delete | 3-pass random overwrite before unlink |

---

## Vault Operations

### Lock

Encrypts `.env` → `.env.vault` and securely deletes the plaintext.

```
POST /api/vault/lock
Body: { "passphrase": "..." }
```

### Unlock

Decrypts `.env.vault` → `.env` using the passphrase.

```
POST /api/vault/unlock
Body: { "passphrase": "..." }
```

### Quick-Lock

Re-encrypts using the in-memory passphrase (no re-entry needed). Only
available when the passphrase is registered in the current session.

```
POST /api/vault/lock
```

### Auto-Lock

The vault automatically re-locks after a configurable period of inactivity.
The timer resets on any vault operation. Default: 15 minutes.

### Register

Store the passphrase in memory without locking/unlocking. Enables quick-lock
and auto-lock without requiring passphrase re-entry.

```
POST /api/vault/register
Body: { "passphrase": "..." }
```

### Export

Creates a portable encrypted backup with higher KDF iterations (600,000).
Suitable for sharing or backup storage.

```
POST /api/vault/export
```

### Import

Restores from an exported vault file. Shows a diff preview before applying.

```
POST /api/vault/import
```

---

## Secrets Management

The Secrets tab provides a UI for managing individual keys in `.env`:

- **List keys** — shows all keys with masked values
- **Add/Edit** — set or update a key-value pair
- **Delete** — remove a key
- **Push/Pull** — synchronize secrets between environments

The secrets editor works on the plaintext `.env` file. If the vault is locked,
it must be unlocked first.

---

## Security Measures

1. **Rate limiting** — failed passphrase attempts are throttled
2. **Session passphrase** — stored in memory only (never persisted)
3. **Threading lock** — vault operations are serialized
4. **Secure delete** — 3-pass random overwrite of plaintext files
5. **Graceful shutdown** — vault auto-locks when the server shuts down

---

## Web Admin Integration

The vault status (🔒 locked / 🔓 unlocked) is always visible in the navigation
bar. Clicking it toggles the vault state.

Tabs that require plaintext access (Secrets, Content) show a lock overlay
when the vault is locked, prompting for the passphrase.

---

## See Also

- [CONTENT.md](CONTENT.md) — Content file encryption (different format)
- [WEB_ADMIN.md](WEB_ADMIN.md) — Web dashboard guide
