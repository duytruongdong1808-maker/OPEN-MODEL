# Agent Tools

Phase 3 adds a small tool-calling agent loop over the email I/O layer.

## Run the backend

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.server.app:app --host 127.0.0.1 --port 8000
```

The tools and agent endpoints require:

```env
AGENT_OPS_TOKEN=local-dev-token
```

Use a different token outside local development.

## Tool smoke checks

```powershell
$headers = @{ Authorization = "Bearer local-dev-token" }

Invoke-RestMethod `
  "http://127.0.0.1:8000/tools/inbox?limit=5&unread_only=false" `
  -Headers $headers
```

## Agent run

```powershell
$headers = @{ Authorization = "Bearer local-dev-token" }

Invoke-RestMethod `
  "http://127.0.0.1:8000/agent/run" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json" `
  -Body '{"message":"Read my latest 3 emails and summarize them.","max_steps":5}'
```

The model must answer with either:

```json
{"tool_call":{"name":"read_inbox","arguments":{"limit":3,"unread_only":false}}}
```

or:

```json
{"final":"..."}
```

## Approval decisions

If a send returns `pending_approval`, approve or reject it:

```powershell
Invoke-RestMethod `
  "http://127.0.0.1:8000/agent/approvals/<approval_id>/approve" `
  -Method Post `
  -Headers $headers
```

```powershell
Invoke-RestMethod `
  "http://127.0.0.1:8000/agent/approvals/<approval_id>/reject" `
  -Method Post `
  -Headers $headers
```

