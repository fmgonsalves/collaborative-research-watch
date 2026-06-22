from __future__ import annotations

from .ai_generation import AIGenerationOutput
from .models import AISafeSourceInput

FAKE_MODEL_NAME = "fake-local-generator"


def fake_summary(source_input: AISafeSourceInput) -> str:
    content_length = len(source_input.content_text)
    return f"Fake summary for {source_input.title}. Extracted {content_length} characters for Path 2 validation."


def fake_tags(source_input: AISafeSourceInput) -> list[str]:
    return ["ai-test", source_input.source_type, "validation"]


def fake_generate(source_input: AISafeSourceInput) -> AIGenerationOutput:
    return AIGenerationOutput(
        summary=fake_summary(source_input),
        ai_generated_tags=fake_tags(source_input),
        model=FAKE_MODEL_NAME,
    )
