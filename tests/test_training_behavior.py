from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from src.utils import ROOT_DIR


def should_reexec_train_script(source: str) -> bool:
    return "sys.flags.utf8_mode != 1" in source and 'os.environ.get("PYTHONUTF8") != "1"' in source


def apply_completion_only_mask(input_ids: list[int], completion_mask: list[int], max_length: int) -> list[int]:
    labels = list(input_ids) + ([-100] * (max_length - len(input_ids)))
    padded_completion_mask = list(completion_mask) + ([0] * (max_length - len(completion_mask)))
    return [token if mask else -100 for token, mask in zip(labels, padded_completion_mask, strict=True)]


def test_trl_source_still_prefers_prompt_completion_and_masks_non_completion_tokens() -> None:
    spec = importlib.util.find_spec("trl.trainer.sft_trainer")
    if spec is None or spec.origin is None:
        pytest.skip("TRL is not installed in this environment.")

    source_path = Path(spec.origin)
    source = source_path.read_text(encoding="utf-8")

    assert 'if "prompt" in example' in source
    assert 'output["completion_mask"] = completion_mask' in source
    assert 'output["labels"][completion_mask == 0] = -100' in source


def test_completion_only_mask_example_matches_local_trl_logic() -> None:
    assert apply_completion_only_mask([10, 11, 12, 13], [0, 0, 1, 1], max_length=4) == [-100, -100, 12, 13]
    assert apply_completion_only_mask([20, 21], [0, 1], max_length=4) == [-100, 21, -100, -100]


def test_model_loading_paths_keep_trust_remote_code_disabled() -> None:
    for relative_path in ["src/train_lora.py", "src/utils.py", "src/merge_adapter.py"]:
        source = (ROOT_DIR / relative_path).read_text(encoding="utf-8")
        assert '"trust_remote_code": False' in source or "trust_remote_code=False" in source


def test_train_script_utf8_restart_respects_python_utf8_flag() -> None:
    source = (ROOT_DIR / "src/train_lora.py").read_text(encoding="utf-8")

    assert should_reexec_train_script(source)


def test_train_script_supports_val_dataset_path_and_epoch_eval() -> None:
    source = (ROOT_DIR / "src/train_lora.py").read_text(encoding="utf-8")

    assert "--val_dataset_path" in source
    assert 'eval_strategy="epoch" if eval_enabled else "no"' in source
