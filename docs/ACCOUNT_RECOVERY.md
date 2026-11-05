# Account recovery and email verification

## User flows

- **Forgot password** (`/reset-password`): the user enters their email. The
  request endpoint always returns `202 Accepted`, whether or not the address
  exists, so the page cannot be used to enumerate accounts.
- **Reset link** (`/reset-password?token=...`): the user chooses a new password.
  A valid token is single-use, expires after `PASSWORD_RESET_TOKEN_MINUTES`
  (default 30), and revokes every existing browser session for that account.
- **Verify email** (`/verify-email?token=...`): confirms the address and sets
  `users.email_verified_at`. Registration sends a verification link
  automatically; an authenticated user can request another from the account
  controls.
- **Verify email request**: authenticated `POST
  /api/v1/auth/email-verification/request` issues a fresh link and invalidates
  older unused verification tokens.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/v1/auth/password-reset/request` | public, rate-limited | request a reset link |
| POST | `/api/v1/auth/password-reset/confirm` | token | set a new password |
| POST | `/api/v1/auth/email-verification/request` | session | resend verification |
| POST | `/api/v1/auth/email-verification/confirm` | token | verify an address |

Tokens are generated with `secrets.token_urlsafe(32)` and only a SHA-256 hash
is stored in `auth_tokens`. Used and expired tokens are pruned by the daily
account-lifecycle task after `AUTH_TOKEN_RETENTION_DAYS`.

## Email delivery

Set these in the deployment environment:

```
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
SMTP_FROM=no-reply@example.com
SMTP_STARTTLS=true
SMTP_USE_SSL=false
SMTP_TIMEOUT_SECONDS=15
PUBLIC_APP_BASE_URL=https://app.example.com
```

In development, leaving `SMTP_HOST` empty does not break registration or reset
requests; the one-time link is written to the application log instead. In
production, an unconfigured SMTP transport logs a warning and no email is
delivered.

## Migration

`0200_auth_tokens` adds the `auth_tokens` table. It applies cleanly after the
existing `0100_account_owned_bet_journal` head. Compose deployments run
`python -m scripts.apply_migrations`: an existing database upgrades through
Alembic, while an empty database is bootstrapped from the current metadata and
stamped at head. The historical baseline migration is not replayed on a fresh
database because it creates the current ORM schema rather than a historical
snapshot.
