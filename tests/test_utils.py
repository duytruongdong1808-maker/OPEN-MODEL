from __future__ import annotations

import builtins
import json

import pytest

from src.download_sample_data import normalize_row
from src.utils import (
    DEFAULT_RUNTIME_PRESET,
    WINDOWS_4BIT_DISABLED_MESSAGE,
    collect_cli_option_names,
    coerce_required_text,
    format_user_message,
    format_missing_dependency_error,
    generate_response_from_messages,
    read_jsonl,
    read_yaml_dict,
    render_training_record,
    resolve_runtime_preset,
    should_default_to_4bit,
    should_show_windows_4bit_disabled_banner,
    trim_chat_messages,
    write_jsonl,
)


class FakeTokenizer:
    eos_token = "<eos>"

    @staticmethod
    def apply_chat_template(messages, tokenize=False, add_generation_prompt=True):
        assert tokenize is False
        assert add_generation_prompt is True
        return json.dumps(messages, ensure_ascii=False)


def test_render_training_record_golden_output() -> None:
    row = {
        "instruction": "Explain LoRA simply.",
        "input": "For a beginner.",
        "output": "LoRA trains a small adapter instead of the full model.",
    }

    rendered = render_training_record(FakeTokenizer(), row, system_prompt="You are concise.")

    assert rendered == {
        "instruction": "Explain LoRA simply.",
        "input": "For a beginner.",
        "output": "LoRA trains a small adapter instead of the full model.",
        "prompt": json.dumps(
            [
                {"role": "system", "content": "You are concise."},
                {"role": "user", "content": "Instruction:\nExplain LoRA simply.\n\nInput:\nFor a beginner."},
            ],
            ensure_ascii=False,
        ),
        "completion": "LoRA trains a small adapter instead of the full model.<eos>",
    }


def test_resolve_runtime_preset_merges_with_fallback_defaults() -> None:
    fallback = {
        "max_length": 2048,
        "per_device_train_batch_size": 2,
        "gradient_accumulation_steps": 4,
        "load_in_4bit": False,
        "custom_value": "kept",
    }

    resolved = resolve_runtime_preset(DEFAULT_RUNTIME_PRESET, "train", fallback)

    assert resolved["max_length"] == 512
    assert resolved["per_device_train_batch_size"] == 1
    assert resolved["gradient_accumulation_steps"] == 8
    assert resolved["custom_value"] == "kept"


def test_windows_4bit_banner_only_shows_for_implicit_windows_fallback() -> None:
    assert should_show_windows_4bit_disabled_banner(False, False, system_name="Windows") is True
    assert should_show_windows_4bit_disabled_banner(False, True, system_name="Windows") is False
    assert should_show_windows_4bit_disabled_banner(True, False, system_name="Windows") is False
    assert should_show_windows_4bit_disabled_banner(False, False, system_name="Linux") is False
    assert "4-bit disabled on Windows" in WINDOWS_4BIT_DISABLED_MESSAGE


def test_should_default_to_4bit_returns_false_when_torch_is_missing(monkeypatch) -> None:
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "torch":
            raise ModuleNotFoundError("No module named 'torch'", name="torch")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert should_default_to_4bit() is False


def test_format_missing_dependency_error_mentions_virtualenv_for_torch() -> None:
    message = format_missing_dependency_error(ModuleNotFoundError("No module named 'torch'", name="torch"))

    assert "Missing dependency: torch." in message
    assert "pip install -r requirements.txt" in message
    assert ".venv\\Scripts\\python.exe" in message


def test_collect_cli_option_names_supports_equals_and_space_forms() -> None:
    option_names = collect_cli_option_names(
        ["--config", "configs/run.yaml", "--learning-rate=1e-4", "--load_in_4bit", "false"]
    )

    assert option_names == {"config", "learning_rate", "load_in_4bit"}


def test_trim_chat_messages_keeps_system_and_latest_turns() -> None:
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "u3"},
        {"role": "assistant", "content": "a3"},
    ]

    assert trim_chat_messages(messages, max_history_turns=2) == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "u3"},
        {"role": "assistant", "content": "a3"},
    ]


def test_read_yaml_dict_round_trip(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("learning_rate: 0.0001\nreport_to: tensorboard\n", encoding="utf-8")

    assert read_yaml_dict(path) == {"learning_rate": 0.0001, "report_to": "tensorboard"}


def test_format_user_message_matches_training_chat_structure() -> None:
    assert format_user_message("say something in vietnamese") == "Instruction:\nsay something in vietnamese"


def test_read_write_jsonl_round_trip(tmp_path) -> None:
    path = tmp_path / "records.jsonl"
    rows = [
        {"instruction": "One", "input": "", "output": "A"},
        {"instruction": "Two", "input": "B", "output": "C"},
    ]

    write_jsonl(path, rows)

    assert read_jsonl(path) == rows


def test_normalize_row_skips_rows_with_empty_required_fields() -> None:
    assert (
        normalize_row({"instruction": "   ", "context": "ctx", "response": "answer"}, "databricks/databricks-dolly-15k")
        is None
    )
    assert (
        normalize_row({"instruction": "question", "context": "ctx", "response": "   "}, "databricks/databricks-dolly-15k")
        is None
    )
    assert normalize_row(
        {"instruction": "question", "context": "ctx", "response": "answer"},
        "databricks/databricks-dolly-15k",
    ) == {"instruction": "question", "input": "ctx", "output": "answer"}


def test_read_jsonl_rejects_empty_file(tmp_path) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="No rows found"):
        read_jsonl(path)


@pytest.mark.parametrize(
    ("value", "field_name", "expected_message"),
    [
        (None, "instruction", "string 'instruction'"),
        ("   ", "output", "non-empty 'output'"),
        (123, "instruction", "string 'instruction'"),
    ],
)
def test_coerce_required_text_validation(value, field_name, expected_message) -> None:
    with pytest.raises(ValueError, match=expected_message):
        coerce_required_text(value, field_name)


def test_generate_response_from_messages_omits_sampling_kwargs_when_temperature_is_zero() -> None:
    class FakeTensor:
        def __init__(self, shape):
            self.shape = shape

        def to(self, _device):
            return self

        def __getitem__(self, item):
            if isinstance(item, slice):
                return []
            return self

    class FakeModel:
        def __init__(self):
            self.last_kwargs = None

        def parameters(self):
            class FakeParameter:
                device = "cpu"

            yield FakeParameter()

        def generate(self, **kwargs):
            self.last_kwargs = kwargs
            return [[101, 102]]

    class FakeInferenceTokenizer:
        pad_token_id = 0
        eos_token_id = 1

        @staticmethod
        def apply_chat_template(messages, tokenize=False, add_generation_prompt=True):
            assert tokenize is False
            assert add_generation_prompt is True
            return json.dumps(messages)

        def __call__(self, prompt, return_tensors="pt"):
            assert return_tensors == "pt"
            return {"input_ids": FakeTensor((1, 2)), "attention_mask": FakeTensor((1, 2))}

        @staticmethod
        def decode(tokens, skip_special_tokens=True):
            assert skip_special_tokens is True
            return "ok"

    model = FakeModel()
    tokenizer = FakeInferenceTokenizer()

    response = generate_response_from_messages(
        model=model,
        tokenizer=tokenizer,
        messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "hello"}],
        temperature=0.0,
        top_p=0.9,
    )

    assert response == "ok"
    assert model.last_kwargs["do_sample"] is False
    assert "temperature" not in model.last_kwargs
    assert "top_p" not in model.last_kwargs
