#!/usr/bin/env bash
set -euo pipefail

BACKEND_IMAGE="${BACKEND_IMAGE:-open-model-backend:ci}"
WEB_IMAGE="${WEB_IMAGE:-open-model-web:ci}"
BACKEND_MAX_BYTES=$((2 * 1024 * 1024 * 1024))   # 2 GiB
WEB_MAX_BYTES=$((400 * 1024 * 1024))            # 400 MiB

fail() { echo "ERROR: $*" >&2; exit 1; }

verify_non_root() {
  local image="$1"
  local uid
  uid="$(docker run --rm --entrypoint id "$image" -u)"
  [[ "$uid" != "0" ]] || fail "$image runs as root (uid=0)"
  echo "OK: $image runs as uid=$uid"
}

verify_size() {
  local image="$1" max="$2"
  local size
  size="$(docker image inspect "$image" --format '{{.Size}}')"
  (( size <= max )) || fail "$image size $size > limit $max"
  echo "OK: $image size $size <= $max"
}

verify_trivy() {
  local image="$1"
  if ! command -v trivy >/dev/null; then
    echo "WARN: trivy not installed locally; skipping scan for $image"
    return 0
  fi
  trivy image --severity HIGH,CRITICAL --exit-code 1 --ignore-unfixed "$image"
}

for image in "$BACKEND_IMAGE" "$WEB_IMAGE"; do
  [[ -n "$(docker image ls -q "$image")" ]] || fail "$image not present locally"
done

verify_non_root "$BACKEND_IMAGE"
verify_non_root "$WEB_IMAGE"
verify_size "$BACKEND_IMAGE" "$BACKEND_MAX_BYTES"
verify_size "$WEB_IMAGE" "$WEB_MAX_BYTES"
verify_trivy "$BACKEND_IMAGE"
verify_trivy "$WEB_IMAGE"

echo "All image verification checks passed."
