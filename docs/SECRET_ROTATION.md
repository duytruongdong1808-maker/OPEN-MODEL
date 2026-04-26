# P0 Secret Rotation Runbook

Use this runbook before deploying any environment that has ever used real credentials in a local `.env` file.

## Secrets To Rotate

Rotate every value in this list if it has ever existed in `.env`, shell history, logs, screenshots, chat, or issue comments:

- `AGENT_OPS_TOKEN`
- `AUTH_SECRET`
- `AUTH_PASSWORD`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `AUTH_GOOGLE_SECRET`
- `AGENT_IMAP_PASS`
- `AGENT_SMTP_PASS`
- Gmail app passwords
- `GOOGLE_OAUTH_TOKEN_ENCRYPTION_KEY`

## Generate New Local Secrets

PowerShell:

```powershell
[Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
[Convert]::ToHexString([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLower()
```

OpenSSL:

```bash
openssl rand -base64 32
openssl rand -hex 32
```

Recommended mapping:

- `AUTH_SECRET`: base64 32-byte value.
- `AGENT_OPS_TOKEN`: hex 32-byte value.
- `GOOGLE_OAUTH_TOKEN_ENCRYPTION_KEY`: generate with `Fernet.generate_key()` or the app helper that stores Gmail tokens.

## Google OAuth

1. Open Google Cloud Console.
2. Go to APIs and Services, then Credentials.
3. Open the OAuth client used by Open Model.
4. Create a new client secret.
5. Update deployment secrets with the new value.
6. Delete the old client secret.
7. Confirm the old secret no longer works.

If using NextAuth Google sign-in, rotate `AUTH_GOOGLE_SECRET`. If using the legacy Gmail OAuth flow, rotate `GOOGLE_OAUTH_CLIENT_SECRET`.

## Gmail App Passwords

1. Open the Google Account security page for the mailbox.
2. Revoke existing app passwords used by Open Model.
3. Create new app passwords only if IMAP/SMTP password auth is still required.
4. Prefer OAuth for Gmail access where possible.
5. Update deployment secrets and test IMAP/SMTP auth.

## Local `.env` Reset

After rotation:

```powershell
Copy-Item .env.example .env
```

Then fill only the newly rotated values needed for the current local run. Never commit `.env`.

## Session Invalidation

Changing `AUTH_SECRET` invalidates existing NextAuth JWT sessions. Users must sign in again after deployment.

## Verification Checklist

- Old `AGENT_OPS_TOKEN` returns `401`.
- Old password login fails if `AUTH_PASSWORD` was rotated.
- Old Google OAuth client secret no longer works.
- Old Gmail app password no longer works.
- `git status --ignored --short` shows `.env` as ignored.
- `gitleaks detect --source . --log-opts="--all" --redact --verbose` has no findings, or historical findings have been purged with an explicit force-push plan.
- CI secret scan passes.
