from __future__ import annotations

import json
import logging

import pytest

from research_watch.ai_generation import (
    AI_INPUT_CHAR_LIMIT,
    AIGenerationError,
    AIProviderOutput,
    ai_generation_payload,
    capped_ai_safe_input,
    normalize_provider_output,
    openai_config_from_env,
)
from research_watch.models import AISafeSourceInput


def source_input(**overrides: object) -> AISafeSourceInput:
    values: dict[str, object] = {
        "source_id": "src_abc123",
        "source_type": "document",
        "title": "Example Paper",
        "content_text": "Allowed source text.",
        "filename": "paper.md",
    }
    values.update(overrides)
    return AISafeSourceInput.model_validate(values)


def test_openai_config_requires_key_and_model() -> None:
    with pytest.raises(AIGenerationError, match="OPENAI_API_KEY, RESEARCH_WATCH_OPENAI_MODEL"):
        openai_config_from_env({})


def test_ai_generation_payload_contains_only_source_public_keys() -> None:
    payload = json.loads(ai_generation_payload(source_input()))

    assert set(payload) == {
        "source_id",
        "source_type",
        "title",
        "original_url",
        "filename",
        "content_text",
    }


def test_ai_generation_payload_excludes_forbidden_values() -> None:
    forbidden_values = [
        "Human comment: read this first",
        "human-created-priority-tag",
        "Ada Lovelace",
        "ada@example.com",
        "selected-user@example.com",
        "/Users/fred/shared/private-workspace/sources/team-confidential/project-alpha/paper.md",
        "sources/team-confidential/project-alpha",
        "team-confidential",
        "project-alpha",
        "123456",
        "987654321",
        "PDF parser traceback",
        "Raw parser error",
        "cache-key-123",
        "run-internal-456",
    ]

    payload_json = ai_generation_payload(source_input())

    for value in forbidden_values:
        assert value not in payload_json
    assert "paper.md" in payload_json


def test_ai_generation_payload_caps_long_content() -> None:
    long_text = "a" * (AI_INPUT_CHAR_LIMIT + 50)
    payload = json.loads(ai_generation_payload(source_input(content_text=long_text)))

    assert len(payload["content_text"]) == AI_INPUT_CHAR_LIMIT


def test_capped_ai_safe_input_leaves_short_content_unchanged() -> None:
    payload = source_input(content_text="short")

    assert capped_ai_safe_input(payload) == payload


def test_normalize_provider_output_normalizes_valid_structured_response() -> None:
    output = normalize_provider_output(
        AIProviderOutput(
            summary="  A concise summary.  ",
            ai_generated_tags=["Methods", " Climate ", "DATA"],
        )
    )

    assert output.summary == "A concise summary."
    assert output.ai_generated_tags == ["methods", "climate", "data"]


def test_normalize_provider_output_rejects_malformed_structured_response() -> None:
    with pytest.raises(AIGenerationError, match="invalid structured response"):
        normalize_provider_output(AIProviderOutput(summary="Some blanks.", ai_generated_tags=["one", " ", ""]))


def test_generate_with_openai_logs_provider_exception(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    class FailingResponses:
        def parse(self, **_kwargs: object) -> object:
            raise RuntimeError("provider exploded")

    class FailingClient:
        def __init__(self, api_key: str) -> None:
            self.responses = FailingResponses()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("RESEARCH_WATCH_OPENAI_MODEL", "test-model")
    monkeypatch.setattr("research_watch.ai_generation.OpenAI", FailingClient)

    from research_watch.ai_generation import generate_with_openai

    with caplog.at_level(logging.ERROR, logger="research_watch.ai_generation"):
        with pytest.raises(AIGenerationError, match="AI provider request failed"):
            generate_with_openai(source_input())

    assert "OpenAI generation request failed" in caplog.text
    assert "source_id=src_abc123" in caplog.text
    assert "model=test-model" in caplog.text
    assert "provider exploded" in caplog.text


def test_generate_with_openai_sends_verbosity_in_text_config(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_kwargs: dict[str, object] = {}

    class ParsedResponse:
        output_parsed = AIProviderOutput(
            summary="Generated summary.",
            ai_generated_tags=["methods", "research", "document"],
        )

    class CapturingResponses:
        def parse(self, **kwargs: object) -> ParsedResponse:
            captured_kwargs.update(kwargs)
            return ParsedResponse()

    class CapturingClient:
        def __init__(self, api_key: str) -> None:
            self.responses = CapturingResponses()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("RESEARCH_WATCH_OPENAI_MODEL", "test-model")
    monkeypatch.setattr("research_watch.ai_generation.OpenAI", CapturingClient)

    from research_watch.ai_generation import generate_with_openai

    output = generate_with_openai(source_input())

    assert output.summary == "Generated summary."
    assert output.model == "test-model"
    assert captured_kwargs["text"] == {"verbosity": "low"}
    assert "verbosity" not in captured_kwargs
