![CI](https://github.com/duytruongdong1808-maker/OPEN-MODEL/actions/workflows/ci.yml/badge.svg)

# open-model-v1

A clean, minimal starter repo for supervised fine-tuning a small open-weight language model with LoRA or QLoRA.

This v1 project is meant to be easy to read and easy to extend. It focuses on a simple workflow:

1. Start with raw JSONL training data.
2. Optionally download a small open instruction sample.
3. Curate the raw data into keep/review sets with quality metadata.
4. Build a balanced chat-core dataset from curated sources.
5. Convert it into processed train and validation datasets aligned with the base model tokenizer.
6. Fine-tune a small instruct model with LoRA or QLoRA.
7. Save checkpoints and a final adapter.
8. Run quick evaluation prompts or open a local terminal chat loop.

## What This Repo Does

- Uses Python and Hugging Face tooling.
- Defaults to `Qwen/Qwen2.5-3B-Instruct` as the base model.
- Supports raw training examples in this format:

```json
{"instruction":"...", "input":"...", "output":"..."}
```

- Prepares a processed training file with:
  - `prompt`
  - `completion`
- Adds a curation stage with:
  - `task_type`
  - `language`
  - `quality_score`
  - `flags`
  - `source`
  - `action`
- Fine-tunes with:
  - `transformers`
  - `datasets`
  - `peft`
  - `trl`
  - `bitsandbytes` for 4-bit QLoRA where supported

## Project Layout

```text
open-model-v1/
  .github/
    workflows/
      ci.yml
  .pre-commit-config.yaml
  LICENSE
  data/
    curated/
      curation_report.json
      train_curated.jsonl
      review_candidates.jsonl
      chat_vi_en_seed_curated.jsonl
      mail_triage_vi_en_seed_curated.jsonl
      chat_core_vi_en_train.jsonl
    raw/
      chat_vi_en_seed.jsonl
      mail_triage_vi_en_seed.jsonl
      sample.jsonl
      train.jsonl
    processed/
      train_sft.jsonl
      val_sft.jsonl
  docs/
    expected-loss-curve.svg
  src/
    __init__.py
    build_dataset.py
    curate_data.py
    download_sample_data.py
    generate_mail_triage_seed.py
    prepare_data.py
    train_lora.py
    merge_adapter.py
    eval.py
    chat.py
    utils.py
  configs/
    rtx4060ti_8gb.yaml
    a100_40gb.yaml
  outputs/
    analysis/
    app/
    comparisons/
    databases/
    evaluations/
    logs/
  .gitignore
  pyproject.toml
  README.md
  requirements-dev.txt
  requirements.lock
  requirements.txt
```

## Environment Setup

### 1. Create a virtual environment

From the repo root:

```bash
python -m venv .venv
```

Activate it:

```bash
# PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

If you are training on GPU, install the correct PyTorch build for your CUDA version from the official PyTorch install page first, then run:

```bash
pip install -r requirements.txt
```

If you want a fully pinned environment from this repo snapshot:

```bash
pip install -r requirements.lock
```

`requirements.lock` is a fully pinned snapshot of the current Python 3.11 development environment. For the most portable install path across machines, keep using `requirements.txt`.

CLI scripts accept `--log_level DEBUG|INFO|WARNING|ERROR|CRITICAL`. The default keeps output terse, while `DEBUG` dumps tokenizer and model config details that are useful when validating a run.

For local automation, this repo also includes optional [pre-commit](https://pre-commit.com/) hooks for `ruff` and `black`.

### Observability stack

For local Prometheus, Grafana, and Tempo:

```bash
cp secrets/grafana_password.example secrets/grafana_password
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d
```

Grafana runs on `http://localhost:3001`, Prometheus on `http://localhost:9090`, and backend metrics are available at `/metrics`. See [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md) for production wiring, Sentry DSN guidance, dashboard import details, and alert rules.

### 3. Windows PowerShell note

On Windows, the most reliable way to run the training and inference scripts is to call the repo virtualenv interpreter directly:

```powershell
.\.venv\Scripts\python.exe -u -X utf8 src\train_lora.py --config configs\rtx4060ti_8gb.yaml
```

The `-u` flag keeps logs unbuffered so startup and progress messages appear immediately. The training script also re-execs itself in UTF-8 mode on Windows when needed, but using `-X utf8` explicitly keeps the terminal behavior predictable.

### Training Qwen2.5-3B on RTX 4060 Ti via WSL2

Native Windows is fine for app development, but the committed 3B QLoRA training path is intended for WSL2/Linux because `bitsandbytes` CUDA support is Linux-first. For the RTX 4060 Ti 8 GB path, use WSL2 with NVIDIA GPU passthrough, install the CUDA PyTorch build, then install this repo's requirements:

```bash
pip install --upgrade pip
pip install -r requirements.txt
python -c "import bitsandbytes; print(bitsandbytes.__version__)"
```

Use the committed 8 GB config for smoke tests and full runs:

```bash
python src/train_lora.py --config configs/rtx4060ti_8gb.yaml --max_steps 50
python src/train_lora.py --config configs/rtx4060ti_8gb.yaml
```

If the 3B run still hits CUDA OOM, lower `max_length` from `768` to `512` in `configs/rtx4060ti_8gb.yaml` and keep `per_device_train_batch_size=1`.

The training/eval scripts default Hugging Face caches to the repo-local `.cache/` directory. If the repo lives at `/mnt/d/OPEN-MODEL`, model and dataset cache files go under `/mnt/d/OPEN-MODEL/.cache/` instead of filling the WSL filesystem on `C:`.

## Data Preparation

For a meaningful first fine-tune, download a small public instruction sample into `data/raw/train.jsonl`:

```bash
python src/download_sample_data.py
```

On Windows PowerShell, the equivalent is:

```powershell
.\.venv\Scripts\python.exe -X utf8 src\download_sample_data.py
```

By default this downloads 1,000 rows from `databricks/databricks-dolly-15k` and normalizes them into the repo's raw-data schema. The original three hand-written examples now live at `data/raw/sample.jsonl` for smoke tests, `data/raw/chat_vi_en_seed.jsonl` contains 310 bilingual seed examples for chatbox-core behavior, and `data/raw/mail_triage_vi_en_seed.jsonl` contains 3,600 clean email-triage seed samples generated from gold triage records. The mail seed is English-first, covers ops/support/billing/product/sales/internal/admin scenarios, includes mixed-language cases, and standardizes priority values to `high|medium|low`.

Put your raw source data in `data/raw/train.jsonl`. The new default workflow does not train from raw directly.

Expected format per line:

```json
{"instruction":"Explain LoRA simply.", "input":"", "output":"LoRA trains small adapter weights instead of updating the full model."}
```

Run curation first:

```bash
python src/curate_data.py
```

This writes:

```text
data/curated/train_curated.jsonl
data/curated/review_candidates.jsonl
data/curated/curation_report.json
```

To regenerate the committed email-triage raw seed:

```bash
python src/generate_mail_triage_seed.py --total_rows 3000
```

`--total_rows` must be a positive multiple of `8`, because each gold record expands into summary, classify-only, action extraction, action-only, deadline-only, draft-reply, thread-summary, and full-triage tasks.

Then curate it:

```bash
python src/curate_data.py \
  --input_path data/raw/mail_triage_vi_en_seed.jsonl \
  --output_path data/curated/mail_triage_vi_en_seed_curated.jsonl \
  --review_path data/curated/mail_triage_vi_en_seed_review.jsonl \
  --report_path data/curated/mail_triage_vi_en_seed_report.json \
  --source seed_mail_triage_vi_en
```

Then build the final chat-core dataset:

```bash
python src/build_dataset.py
```

This writes:

```text
data/curated/chat_core_vi_en_train.jsonl
```

By default the builder now mixes the general curated train set, the bilingual chat seed, and the email-triage seed with the `chat_balanced_with_mail` profile. That profile targets 30% Vietnamese general chat, 25% English general chat, 25% English mail, 10% Vietnamese mail, and 10% mixed utility rows.

Then prepare the SFT dataset:

```bash
python src/prepare_data.py
```

This writes:

```text
data/processed/train_sft.jsonl
data/processed/val_sft.jsonl
```

The curated files keep the original fields plus metadata such as `task_type`, `language`, `quality_score`, `flags`, `source`, and `action`. The built dataset balances Vietnamese, English, and mixed-language chat-core tasks with deterministic sampling. The processed files then add model-ready `prompt` and `completion` fields built with the base model tokenizer. Validation splitting is deterministic by hash and defaults to `--val_ratio 0.05`.

If you only want a tiny smoke test on the hand-written examples:

```bash
python src/prepare_data.py --input_path data/raw/sample.jsonl --val_ratio 0
```

If you want to prepare data for a different base model:

```bash
python src/prepare_data.py --base_model Qwen/Qwen2.5-1.5B-Instruct
```

If you change the base model, rerun data preparation before training. If you change the curated inputs, rerun both `curate_data.py` and `build_dataset.py` before `prepare_data.py`. Pass `--model_revision` if you want to lock the tokenizer to a specific Hugging Face revision for reproducibility.
If the tokenizer has no pad token, the repo adds a dedicated `<|pad|>` token and resizes the model embeddings so padding stays distinct from EOS. TRL then masks padded positions to `-100` before loss.
`prepare_data.py` downloads the tokenizer from Hugging Face on first run, so the first invocation may take longer than later cached runs.

End-to-end PowerShell example:

```powershell
.\.venv\Scripts\python.exe -X utf8 src\download_sample_data.py
.\.venv\Scripts\python.exe -X utf8 src\curate_data.py
.\.venv\Scripts\python.exe -X utf8 src\build_dataset.py
.\.venv\Scripts\python.exe -X utf8 src\prepare_data.py
```

## Training

Default training command:

```bash
python src/train_lora.py
```

If you want a committed YAML to describe the run:

```bash
python src/train_lora.py --config configs/rtx4060ti_8gb.yaml
```

Recommended Windows PowerShell command:

```powershell
.\.venv\Scripts\python.exe -u -X utf8 src\train_lora.py --config configs\rtx4060ti_8gb.yaml
```

CLI arguments still override the file:

```bash
python src/train_lora.py --config configs/rtx4060ti_8gb.yaml --learning_rate 5e-5
```

This will:

- load the processed train and validation datasets
- load the base model
- use `Qwen/Qwen2.5-3B-Instruct`
- default to `max_length=768` for the 8 GB preset
- use 4-bit QLoRA in the committed RTX 4060 Ti config
- train LoRA adapters
- evaluate on `data/processed/val_sft.jsonl` every `save_steps`
- save checkpoints under `outputs/`
- save the final adapter to:

```text
outputs/qwen2.5_3b_lora_v2/final_adapter
```

Preset for your current GPU target:

```bash
python src/train_lora.py --preset rtx4060ti_8gb
```

This preset is tuned for `Qwen/Qwen2.5-3B-Instruct` QLoRA on GPUs like the RTX 4060 Ti 8 GB and currently applies:

- `max_length=768`
- `per_device_train_batch_size=1`
- `gradient_accumulation_steps=16`
- `load_in_4bit=true` when using `configs/rtx4060ti_8gb.yaml`
- `gradient_checkpointing=true`

Example with a few explicit overrides:

```bash
python src/train_lora.py ^
  --num_train_epochs 1 ^
  --max_length 768 ^
  --per_device_train_batch_size 1 ^
  --gradient_accumulation_steps 16 ^
  --learning_rate 5e-5
```

On macOS or Linux shells:

```bash
python src/train_lora.py \
  --num_train_epochs 1 \
  --max_length 768 \
  --per_device_train_batch_size 1 \
  --gradient_accumulation_steps 16 \
  --learning_rate 5e-5
```

If you want to disable 4-bit loading:

```bash
python src/train_lora.py --load_in_4bit false
```

That is mainly useful for debugging or environments where `bitsandbytes` is not available. On native Windows, this starter now defaults to full-precision loading unless you explicitly opt into 4-bit yourself.
When that Windows fallback is chosen implicitly, the script now prints an explicit banner so you can see that the run is not using QLoRA.
The script also prints a startup banner before importing the heavier ML stack so you can tell immediately that the process has launched.

Reproducibility knobs:

```bash
python src/train_lora.py --seed 42
python src/train_lora.py --model_revision <hf-commit-or-tag>
```

Metric logging is optional and stays off by default:

```bash
python src/train_lora.py --report_to tensorboard
python src/train_lora.py --report_to wandb
```

If `data/processed/val_sft.jsonl` is missing or empty, training skips evaluation automatically. That keeps `data/raw/sample.jsonl` usable for quick smoke tests.

If you switch to a gated base model, log in first:

```bash
huggingface-cli login
```

![Expected loss curve](docs/expected-loss-curve.svg)

## Adapter Merging

Merge the trained adapter into the base model so the result can run with `transformers` alone:

```bash
python src/merge_adapter.py
```

This step is optional. `chat.py` and `eval.py` can load the base model plus the LoRA adapter directly without merging first.

By default this reads the adapter path you pass and writes the merged model beside the adapter output. The current metric-first 3B training config writes to `outputs/qwen2.5_3b_lora_v2/final_adapter`. The legacy 1.5B adapter path and the 3B v1 artifact remain usable if you explicitly set the old base model and adapter path.

The `outputs/qwen2.5_3b_lora_v2/README.md` file you may see after training is the model card autogenerated by Hugging Face tooling for the adapter/checkpoint artifact.

## Publish the Adapter to Hugging Face

Use this path when you want another machine to run the project without training again.
The repo keeps `outputs/` out of git, so publish the trained adapter as a Hugging Face
model repo instead of committing it to GitHub.

First install dependencies and log in with a Hugging Face token that has write access:

```bash
pip install -r requirements.txt
hf auth login
```

Upload the final adapter from this machine:

```bash
python scripts/hf_upload_adapter.py your-hf-username/open-model-qwen25-lora
```

For a private model repo:

```bash
python scripts/hf_upload_adapter.py your-hf-username/open-model-qwen25-lora --private
```

If you prefer to publish the merged full model instead of the lightweight LoRA
adapter, upload the merged folder to a separate model repo:

```bash
python scripts/hf_upload_adapter.py your-hf-username/open-model-qwen25-merged --artifact merged
```

The project artifacts published from this repo are:

```text
HackerBu/mail-agent
HackerBu/mail-agent-merged
```

On another machine, clone or pull this GitHub repo, install dependencies, then download the adapter:

```bash
python scripts/hf_download_adapter.py your-hf-username/open-model-qwen25-lora
```

To download the merged full model instead:

```bash
python scripts/hf_download_adapter.py your-hf-username/open-model-qwen25-merged --artifact merged
```

The downloader writes files to:

```text
outputs/qwen2.5_3b_lora_v1/final_adapter
outputs/qwen2.5_3b_lora_v1/merged
```

After that, the Docker Compose stack can use the adapter without rerunning training:

```bash
docker compose up --build
```

## Evaluation

Run a quick inference smoke test with built-in prompts:

```bash
python src/eval.py
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -X utf8 src\eval.py
```

This loads the base model plus the saved adapter and prints a few sample generations to the terminal.
Like training, 4-bit loading only turns on by default when the local environment supports it.
Evaluation also accepts `--seed` and `--model_revision` for reproducible sampling against the pinned base model snapshot.

For the field-level gold evaluation set used by the mail-triage workflow:

```bash
python src/eval.py --eval_path data/eval/mail_triage_gold.jsonl
```

When the eval file includes `expected` fields, the script now reports parse success plus normalized matches for summary, priority, action items, and deadlines.

If you want the matching evaluation preset:

```bash
python src/eval.py --preset rtx4060ti_8gb
```

If your adapter is saved somewhere else:

```bash
python src/eval.py --adapter_path outputs/qwen2.5_3b_lora_v2/final_adapter
```

For the metric-first comparison flow, keep each adapter output separate and compare JSON reports:

```bash
python scripts/eval_quality.py --base Qwen/Qwen2.5-1.5B-Instruct --adapter outputs/qwen2.5_1.5b_mail_triage_lora_v4/final_adapter --eval-set both --output outputs/evaluations/qwen25_1p5b_mail_triage_v4/eval_qwen25_1p5b_mail_triage_v4.json
python scripts/eval_quality.py --base Qwen/Qwen2.5-3B-Instruct --adapter outputs/qwen2.5_3b_lora_v1/final_adapter --eval-set both --output outputs/evaluations/qwen25_3b_lora_v1/eval_qwen25_3b_lora_v1.json
python scripts/eval_quality.py --base Qwen/Qwen2.5-3B-Instruct --adapter outputs/qwen2.5_3b_lora_v2/final_adapter --eval-set both --output outputs/evaluations/qwen25_3b_lora_v2/eval_qwen25_3b_lora_v2.json
python scripts/compare_eval.py outputs/evaluations/qwen25_1p5b_mail_triage_v4/eval_qwen25_1p5b_mail_triage_v4.json outputs/evaluations/qwen25_3b_lora_v1/eval_qwen25_3b_lora_v1.json --output outputs/comparisons/compare_1p5b_vs_3b_v1.md
python scripts/compare_eval.py outputs/evaluations/qwen25_3b_lora_v1/eval_qwen25_3b_lora_v1.json outputs/evaluations/qwen25_3b_lora_v2/eval_qwen25_3b_lora_v2.json --output outputs/comparisons/compare_3b_v1_vs_3b_v2.md
```

## Local Chat

Start a simple terminal chat loop:

```bash
python src/chat.py
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -X utf8 src\chat.py
```

This v1 chat loop is intentionally simple:

- it loads the base model plus adapter
- it keeps a short multi-turn history in memory
- it supports `/reset` and `/system <prompt>`
- it trims older turns automatically with `--max_history_turns`
- it is still useful for quick local testing, not production serving
- it follows the same environment-aware 4-bit default as the training and eval scripts
- it wraps each user turn into the same `Instruction:` format used during SFT preparation so chat-time prompts match train-time prompts more closely

If you want the matching chat preset:

```bash
python src/chat.py --preset rtx4060ti_8gb
```

Type `exit` or `quit` to stop.

## Web Chat App

This repo now includes a ChatGPT-style internal MVP with:

- a `FastAPI` backend under `src/server/`
- a `Next.js` frontend under `web/`
- conversation, audit, Gmail credential, and send-ledger storage through SQLAlchemy with
  PostgreSQL for compose/prod and SQLite fallback for local dev
- streaming assistant replies over `SSE`
- a read-only mail agent that can inspect inbox summaries and full emails, then produce prioritized briefs with action items

### Inference backend

The FastAPI backend supports two inference backends:

- `local` keeps the original `transformers` + `TextIteratorStreamer` flow in the API process. Use this for CPU-only development, quick debugging, and environments without vLLM.
- `vllm` sends OpenAI-compatible chat-completion requests to the separate `inference` container. Use this for GPU serving and concurrent web users.

Switch with:

```bash
OPEN_MODEL_INFERENCE_BACKEND=local
OPEN_MODEL_INFERENCE_BACKEND=vllm
OPEN_MODEL_AGENT_CONSTRAINED_DECODING=true
OPEN_MODEL_VLLM_URL=http://inference:8001/v1
OPEN_MODEL_VLLM_MODEL=adapter
OPEN_MODEL_VLLM_TIMEOUT_S=120
```

The vLLM compose service runs `Qwen/Qwen2.5-3B-Instruct-AWQ` with the LoRA adapter from `outputs/qwen2.5_3b_lora_v5/final_adapter`. GPU hosts need CUDA 12+, `nvidia-container-toolkit`, and an 8 GB card is the intended target. The compose command uses a conservative `--max-model-len 1024`, `--max-num-seqs 4`, and `--dtype half` profile for lower-memory GPUs. If vLLM runs out of memory, lower `--max-model-len` or `--gpu-memory-utilization` in `docker-compose.yml`.

#### Agent constrained decoding

When the agent runs on the `vllm` backend, the backend sends a compact JSON Schema through vLLM `guided_json` so the model can only emit either a single `tool_call` object or a `final` answer. This grammar-enforced path requires vLLM 0.6+ structured output support and keeps the schema out of the system prompt.

Disable the constraint for debugging with:

```bash
OPEN_MODEL_AGENT_CONSTRAINED_DECODING=false
```

Measure parse reliability with `python scripts/eval_agent_parse.py --backend vllm --n 100`. Expected failure rate is below 1% on vLLM with constrained decoding, compared with roughly 15-30% for local or unconstrained runs.

For CPU-only compose development, use the override file. It replaces the GPU inference container with a tiny healthcheck stub and makes the backend use `LocalModelChatService`:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

See [Inference Architecture](docs/inference-architecture.md) for the service layout and readiness behavior.

### Run the backend

From the repo root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.server.app:app --reload
```

Optional environment variables:

- `OPEN_MODEL_BASE_MODEL`
- `OPEN_MODEL_ADAPTER_PATH`
- `OPEN_MODEL_MODEL_REVISION`
- `OPEN_MODEL_LOAD_IN_4BIT`
- `OPEN_MODEL_DB_PATH`
- `OPEN_MODEL_DATABASE_URL`
- `OPEN_MODEL_DATABASE_PASSWORD_FILE`
- `OPEN_MODEL_LEDGER_DB_PATH`
- `OPEN_MODEL_LEDGER_DATABASE_URL`
- `OPEN_MODEL_CORS_ORIGINS`
- `OPEN_MODEL_MAX_REQUEST_BYTES`
- `OPEN_MODEL_MAX_NEW_TOKENS`
- `OPEN_MODEL_TEMPERATURE`
- `OPEN_MODEL_TOP_P`
- `OPEN_MODEL_INFERENCE_BACKEND`
- `OPEN_MODEL_AGENT_CONSTRAINED_DECODING`
- `OPEN_MODEL_VLLM_URL`
- `OPEN_MODEL_VLLM_MODEL`
- `OPEN_MODEL_VLLM_TIMEOUT_S`
- `INTERNAL_HMAC_SECRET`

If `OPEN_MODEL_ADAPTER_PATH` is not set, the API tries the default adapter path for `OPEN_MODEL_BASE_MODEL` first and falls back to the base model if no adapter is present.

The chat API endpoints use the same bearer token as the tools API plus signed internal user headers. Set `AGENT_OPS_TOKEN` and `INTERNAL_HMAC_SECRET` on both the backend and the Next.js server. The Next.js app below sends the bearer token and HMAC-signed user identity server-side through its API proxy, so the browser bundle never receives either secret.

The web chat runs the mail agent in read-only mode by default. Gmail OAuth credentials are encrypted and stored per verified web user in the application database. If a user has not connected Gmail, the mail tools can still fall back to the shared `AGENT_IMAP_*` configuration for ops/internal use; that IMAP fallback is not per-user.

Security audit events are stored in the application database. NextAuth login success/failure is logged by a best-effort server-side call to `POST /audit/login` using `AGENT_OPS_TOKEN`; passwords are never sent to the audit endpoint.

### Run the frontend

In a second terminal:

```powershell
cd web
npm install
npm run dev
```

If your API is not on `http://127.0.0.1:8000`, set:

```powershell
$env:OPEN_MODEL_API_BASE_URL="http://127.0.0.1:8000"
```

For local/internal testing against the protected chat API, set the server-side proxy token to the same value as `AGENT_OPS_TOKEN`:

```powershell
$env:AGENT_OPS_TOKEN="<token>"
$env:INTERNAL_HMAC_SECRET="<at-least-32-byte-secret>"
```

Do not expose this token with a `NEXT_PUBLIC_*` variable; anything with that prefix is bundled into client-side JavaScript.

### Redis rate limiting

The authenticated Next.js backend proxy rate-limits each user before forwarding to FastAPI. Defaults are `120` requests per `60` seconds and can be changed with:

```powershell
$env:AUTH_RATE_LIMIT_MAX_REQUESTS="120"
$env:AUTH_RATE_LIMIT_WINDOW_MS="60000"
```

Set `REDIS_URL` to share rate-limit state across Next.js processes and restarts:

```powershell
$env:REDIS_URL="redis://127.0.0.1:6379"
```

If `REDIS_URL` is not set, local development falls back to an in-memory limiter. If Redis is configured but unavailable, the proxy logs the limiter error and fails open so chat traffic keeps flowing. Rate-limited proxy responses include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset`; blocked requests also include `Retry-After`.

To use `Continue with Google` and let the web mail agent read the signed-in account's Gmail, configure the Next.js environment with:

```powershell
$env:AUTH_SECRET="<random-secret>"
$env:AUTH_GOOGLE_ID="<google-oauth-client-id>"
$env:AUTH_GOOGLE_SECRET="<google-oauth-client-secret>"
```

Add this authorized redirect URI in Google Cloud:

```text
http://localhost:3000/api/auth/callback/google
```

These `AUTH_GOOGLE_*` settings are for web sign-in. The `GOOGLE_OAUTH_*` settings configure the separate Gmail connect flow. Gmail OAuth state is kept in process memory for 10 minutes, so multi-instance deployments must route the Google callback back to the same backend instance that started the flow, for example with sticky sessions.

Then open:

```text
http://localhost:3000
```

### Run with Docker Compose

Create the Postgres password secret before the first compose boot:

```bash
mkdir -p secrets
openssl rand -base64 32 > secrets/postgres_password
chmod 600 secrets/postgres_password
```

```powershell
docker compose up --build
```

The compose stack starts Postgres and the vLLM `inference` service first, waits for them to become healthy, and then starts the backend with `OPEN_MODEL_DATABASE_URL=postgresql+psycopg://openmodel@postgres:5432/openmodel` and `OPEN_MODEL_INFERENCE_BACKEND=vllm`. The database password is read from the Docker secret mount, not baked into the image or `.env`.

The compose stack only publishes the web app on `http://localhost:3000`. The FastAPI backend is exposed on the internal Docker network as `http://backend:8000` so browser traffic must pass through the authenticated Next.js proxy.

To debug the backend directly from inside the compose network:

```powershell
docker compose exec backend curl -fsS http://localhost:8000/health
```

### Database migrations

Application storage is managed with Alembic. By default migrations read `OPEN_MODEL_DB_PATH` and build a SQLite SQLAlchemy URL for that file. To use Postgres or another explicit SQLAlchemy URL, set `OPEN_MODEL_DATABASE_URL`.

Run migrations from the repo root:

```powershell
alembic upgrade head
```

Migration `0002` adds `conversations.user_id` with a default value of `legacy` for pre-existing rows. Operators must either backfill those rows to a real user ID or accept that legacy chats are inaccessible through the signed per-user API. To assign all legacy conversations to a user:

```powershell
python scripts/backfill_user_id.py --user-id local-user
```

Migration `0003` adds `gmail_credentials` for per-user encrypted Gmail OAuth tokens. Legacy `gmail_token.json` files are ignored; each user must reconnect Gmail so credentials can be stored under their verified user ID.

Migration `0005` changes `audit_log.detail_json` to `JSONB` on Postgres. SQLite keeps text storage for local compatibility.

### Migrating from SQLite to Postgres

Start with an empty Postgres database whose schema is at the current Alembic head, then run:

```bash
python scripts/migrate_sqlite_to_postgres.py \
  --sqlite-path ./outputs/app/chat.sqlite3 \
  --postgres-url postgresql+psycopg://openmodel:REDACTED@localhost:5432/openmodel
```

The script copies rows in batches of 500 and uses `ON CONFLICT DO NOTHING`, so it is safe to retry. It verifies row counts after the copy and exits non-zero if any table differs. Use `--dry-run` to print the source row counts without writing.

### Postgres backups

The included `scripts/backup_postgres.sh` is cron-compatible and runs `pg_dump --format=custom` to `/backups/openmodel-YYYY-MM-DD-HHMM.dump`. Production operators should schedule a daily backup and copy it to durable object storage such as S3 or GCS; cloud backup automation is intentionally outside this ticket.

## Common Troubleshooting

### `bitsandbytes` install or runtime errors

- Native Windows support can be inconsistent.
- The cleanest path for QLoRA is Linux or WSL with an NVIDIA GPU.
- If you only want to test the code path, try:

```bash
python src/train_lora.py --load_in_4bit false
```

### CUDA out-of-memory

- Start with fewer examples.
- Lower `--max_length`.
- Keep `--per_device_train_batch_size 1`.
- Increase `--gradient_accumulation_steps`.
- On 8 GB GPUs, start with the default `--max_length 512` and only raise it after a successful run.

### Tokenizer or prompt mismatch after changing models

- Rerun:

```bash
python src/prepare_data.py --base_model <your-model>
```

- Then train again with the same base model name.

### Training data errors

Each JSONL row must include:

- `instruction` as a non-empty string
- `output` as a non-empty string
- `input` may be empty

If you use the curated pipeline, review rows are written separately and should not be fed directly into training.

### Very slow CPU inference

- This starter is designed mainly for GPU experimentation.
- CPU runs can still work for smoke tests, but they will be slow.

## Security Notes

- This repo keeps `trust_remote_code=False` in the model-loading paths.
- Rotate every value that has ever appeared in a local `.env` before deployment. See [P0 Secret Rotation Runbook](docs/SECRET_ROTATION.md).
- Publish a privacy and retention policy before enabling public Gmail OAuth traffic. See [Open Model Privacy and Data Retention Policy](docs/PRIVACY.md).
- Treat `data/raw/` as sensitive local input. Do not put PII, secrets, or proprietary data there unless you are intentionally working in a secure environment.
- Review any third-party dataset or base model license before redistribution of derived artifacts.

## Notes For Extending Later

Good next steps after this v1:

- expose inference behind a small FastAPI service
- support DPO or preference tuning later

This repo is intentionally not that yet. It is the first working version.
