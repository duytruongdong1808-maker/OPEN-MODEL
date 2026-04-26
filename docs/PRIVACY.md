# Open Model Privacy and Data Retention Policy

Last updated: 2026-04-26

## Scope

This policy covers the Open Model internal web chat, Gmail OAuth integration, read-only mail agent, and local API services in this repository.

## Data We Collect

Open Model may process the following data when a user signs in or uses the product:

- Account data: sign-in identifier, display name, and email address provided by the configured authentication provider.
- Chat data: conversation titles, user messages, assistant messages, timestamps, and source metadata shown in the chat UI.
- Gmail connection data: OAuth access and refresh token material, granted scopes, connected Gmail address, and token timestamps.
- Gmail content used by the read-only mail agent: email metadata, snippets, sender and recipient addresses, subject lines, timestamps, labels, attachment flags, and full message body text when a user asks the agent to read an email.
- Operational data: request timestamps, route names, health check status, error details, and security events needed to operate and debug the service.

Open Model does not intentionally collect payment data, government identifiers, or unrelated browser history.

## How We Use Data

Open Model uses collected data to:

- authenticate users;
- display and preserve chat conversations;
- connect a user's Gmail account after explicit authorization;
- let the read-only mail agent summarize inbox items and individual messages requested by the user;
- protect the service from abuse;
- debug failures and investigate security incidents.

Gmail data is not used for advertising and is not sold.

## Gmail Permissions

The Gmail integration is intended to be read-only in the web chat workflow. The agent may list recent inbox messages and read individual messages so it can produce summaries, priorities, and action items.

Users can disconnect Gmail from the application. Disconnecting Gmail must revoke or delete locally stored token material for that user. Users may also revoke app access from their Google Account security settings.

## Data Retention

Default retention targets:

- Chat conversations: retained until the user deletes them or asks for account deletion.
- Gmail OAuth tokens: retained until the user disconnects Gmail, revokes access, or asks for account deletion.
- Cached Gmail message data: retained only as part of conversation history or local operational storage; production deployments should expire cached email body content after 30 days unless a shorter period is required.
- Audit logs: retained for 90 days, then purged unless needed for an active security investigation. Audit entries record security metadata such as action names, timestamps, user IDs, truncated IPs in user-facing views, and redacted details; they must not contain passwords, tokens, OAuth codes, raw email bodies, snippets, or full email subjects.
- Other operational logs: retained for up to 90 days unless needed for an active security investigation.
- Local development artifacts under `outputs/`: not production records and must not be committed to git.

Production deployments should automate deletion jobs for cached Gmail content and old operational logs before public traffic is allowed. Audit retention can be enforced with `python scripts/purge_old_audit.py --days 90`, scheduled via cron or a Kubernetes CronJob.

## User Rights and Deletion

Users may request:

- a copy of their conversation and Gmail connection metadata;
- deletion of their chat history;
- Gmail disconnect and deletion of locally stored OAuth token material;
- deletion of their account data.

Account deletion must remove user-owned conversations, messages, Gmail token material, and audit records that are not required for security or legal retention. The account deletion endpoint is intentionally deferred until user isolation is implemented, because deleting account data safely requires user-scoped storage.

## Security Controls

Open Model protects data with:

- server-side authentication for chat routes;
- a Next.js API proxy so browser clients do not receive backend bearer tokens;
- encrypted local Gmail OAuth token storage;
- secret scanning in pre-commit and CI;
- ignored local `.env`, SQLite, token, log, and model output files;
- Docker Compose networking that keeps the backend off host ports by default.

Production deployments must rotate any secret that has ever appeared in a local `.env` file before deploy.

## Contact

For privacy or deletion requests, contact the repository owner or deployment operator for the specific Open Model environment.
