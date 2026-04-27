# Inference Architecture

The backend can run either the original in-process local model loader or a separate vLLM OpenAI-compatible service.

```text
Browser
  |
  | SSE /conversations/{id}/messages/stream
  v
Next.js proxy
  |
  | signed user headers + bearer token
  v
FastAPI backend
  |
  | SupportsStreamingReply
  |  - local: transformers + TextIteratorStreamer
  |  - vllm: httpx SSE client
  v
Inference service
  |
  | POST /v1/chat/completions stream=true
  v
vLLM container
  |
  | Qwen/Qwen2.5-1.5B-Instruct + LoRA adapter
  v
NVIDIA GPU
```

Local mode is the CPU/dev fallback and keeps the model inside the FastAPI process. vLLM mode moves generation into the `inference` container, allowing multiple backend workers or API replicas to share one GPU-serving endpoint.

Readiness is split:

- `/health/live` reports whether the FastAPI process is alive.
- `/health/ready` checks the database and, for vLLM mode, pings `${OPEN_MODEL_VLLM_URL}/models`.

The backend does not warm up the model when `OPEN_MODEL_INFERENCE_BACKEND=vllm`; vLLM owns model loading in its container.
