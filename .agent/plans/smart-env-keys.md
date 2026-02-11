# Smart .env Key Management — Implementation Plan

## Comment Metadata Format

Metadata tags use `@ ` prefix in the comment line ABOVE the key:

```env
# ── Content Vault ──────────────────────────
# @encoding:base64
CONTENT_ENCRYPTION_KEY=LS0tLS1CRUdJTi...

# ── Feature Flags ──────────────────────────
# @type:toggle
ENABLE_DEBUG=true

# @type:select @options:debug,info,warn,error
LOG_LEVEL=info

# ── Credentials ────────────────────────────
# @type:password @generated:password @length:32
DB_PASSWORD=randomsecretvalue

# @encoding:base64 @generated:ssh-ed25519
SSH_DEPLOY_KEY=LS0tLS1CRUdJTi...

# @encoding:base64 @generated:cert-selfsigned
TLS_CERTIFICATE=LS0tLS1CRUdJTi...
```

### Tag Reference

| Tag | Values | UI Effect |
|-----|--------|-----------|
| `@type:toggle` | — | On/off toggle instead of text input |
| `@type:select` | — | Dropdown (needs `@options`) |
| `@type:password` | — | Password field with show/hide + generate |
| `@type:multiline` | — | Textarea for long values |
| `@options:a,b,c` | csv | Options for select type |
| `@encoding:base64` | — | Show decode/view toggle, base64 badge |
| `@generated:password` | — | Shows 🔄 regenerate button |
| `@generated:ssh-ed25519` | — | Shows 🔄 regenerate button |
| `@generated:ssh-rsa` | — | Shows 🔄 regenerate button |
| `@generated:cert-selfsigned` | — | Shows 🔄 regenerate button |
| `@generated:token` | — | Shows 🔄 regenerate button |
| `@length:N` | number | For password/token generation |

### Legacy Compat
- `# local-only` remains as-is (alias for `@local-only`)
- Tags can be combined: `# @local-only @encoding:base64 @generated:ssh-ed25519`

## Implementation Steps

### Phase 1: Backend — Parser + Generators

1. **Update `vault_io.py`**: Parse `@` metadata tags from comment lines
   - `list_env_keys()`: attach `meta` dict to each key
   - `list_env_sections()`: same
   
2. **Add `POST /keys/generate`** endpoint in `routes_secrets.py`:
   - `type: password` → random password with configurable length
   - `type: token` → URL-safe random token
   - `type: ssh-ed25519` → ed25519 keypair (private + public)
   - `type: ssh-rsa` → RSA keypair
   - `type: cert-selfsigned` → self-signed TLS cert + key
   - Returns: `{ value, public_value?, base64 }`

3. **Add `POST /vault/set-meta`** endpoint:
   - Set/update metadata tags for a key in .env comments

### Phase 2: Frontend — Smart Rendering

4. **Update `renderSecretsForm()`** in `_secrets_render.html`:
   - Toggle switch for `@type:toggle`
   - `<select>` for `@type:select @options:...`
   - Password show/hide for `@type:password`
   - Base64 decode/encode badge for `@encoding:base64`
   - 🔄 Regenerate button for `@generated:*`

### Phase 3: Frontend — Smart Add Modal

5. **Upgrade `showAddKeysModal()`** in `_secrets_keys.html`:
   - Tab bar: Manual | 🔑 Password | 🔐 SSH Key | 📜 Certificate | 🎫 Token
   - Each tab has generator-specific UI
   - Preview generated value before adding
   - Auto-set metadata tags
   - Base64 encoding toggle
