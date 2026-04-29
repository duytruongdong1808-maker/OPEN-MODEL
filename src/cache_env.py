from __future__ import annotations

import os
from pathlib import Path


def configure_repo_cache_env(repo_root: Path | None = None) -> None:
    """Default Hugging Face caches to the repo drive unless the user set them."""
    resolved_root = Path(__file__).resolve().parents[1] if repo_root is None else repo_root
    cache_root = resolved_root / ".cache"
    hf_home = cache_root / "huggingface"

    os.environ.setdefault("HF_HOME", str(hf_home))
    os.environ.setdefault("HF_HUB_CACHE", str(hf_home / "hub"))
    os.environ.setdefault("HF_DATASETS_CACHE", str(hf_home / "datasets"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(hf_home / "transformers"))
