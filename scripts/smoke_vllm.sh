#!/usr/bin/env bash
set -euo pipefail

# Manual GPU smoke test. Not run in CI by default because GitHub-hosted runners
# do not provide an NVIDIA GPU.
docker compose --profile vllm up -d inference

deadline=$((SECONDS + 240))
until docker compose exec -T inference curl -fsS http://localhost:8001/health >/dev/null; do
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "Timed out waiting for vLLM /health."
    docker compose logs inference
    exit 1
  fi
  sleep 5
done

response="$(
  docker compose exec -T inference curl -fsS http://localhost:8001/v1/chat/completions \
    -H 'Content-Type: application/json' \
    -d '{
      "model": "adapter",
      "messages": [
        {"role": "system", "content": "You are concise."},
        {"role": "user", "content": "Say hello in one short sentence."}
      ],
      "max_tokens": 32,
      "temperature": 0,
      "stream": false
    }'
)"

if ! printf '%s' "$response" | grep -q '"choices"'; then
  echo "Unexpected vLLM response:"
  printf '%s\n' "$response"
  exit 1
fi

echo "vLLM smoke test passed."
