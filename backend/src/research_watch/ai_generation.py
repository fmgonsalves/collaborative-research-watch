from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from typing import Callable

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from .models import AISafeSourceInput

logger = logging.getLogger(__name__)

AI_INPUT_CHAR_LIMIT = 30_000

AI_GENERATION_INSTRUCTIONS = """Generate per-source research enrichment from the provided source text and safe source metadata.
Write a practical 2-4 sentence summary that helps a teammate decide whether to read the source.
Generate 3-8 concise lowercase tags useful for browsing and filtering.
Base the output only on the provided source content and metadata. Do not speculate beyond it.
"""


class AIProviderOutput(BaseModel):
    summary: str
    ai_generated_tags: list[str] = Field(min_length=3, max_length=8)


class AIGenerationOutput(AIProviderOutput):
    model: str | None = None


class AIGenerationConfig(BaseModel):
    api_key: str
    model: str


class AIGenerationError(Exception):
    def __init__(self, safe_message: str) -> None:
        super().__init__(safe_message)
        self.safe_message = safe_message


class AIConfigurationError(AIGenerationError):
    pass


AIGenerator = Callable[[AISafeSourceInput], AIGenerationOutput]


def openai_config_from_env(environ: Mapping[str, str] = os.environ) -> AIGenerationConfig:
    api_key = environ.get("OPENAI_API_KEY", "").strip()
    model = environ.get("RESEARCH_WATCH_OPENAI_MODEL", "").strip()
    missing = []
    if not api_key:
        missing.append("OPENAI_API_KEY")
    if not model:
        missing.append("RESEARCH_WATCH_OPENAI_MODEL")
    if missing:
        raise AIConfigurationError(f"AI generation is not configured. Missing: {', '.join(missing)}.")
    return AIGenerationConfig(api_key=api_key, model=model)


def capped_ai_safe_input(source_input: AISafeSourceInput) -> AISafeSourceInput:
    if len(source_input.content_text) <= AI_INPUT_CHAR_LIMIT:
        return source_input
    return source_input.model_copy(update={"content_text": source_input.content_text[:AI_INPUT_CHAR_LIMIT]})


def ai_generation_payload(source_input: AISafeSourceInput) -> str:
    capped_input = capped_ai_safe_input(source_input)
    return json.dumps(
        {
            "source_id": capped_input.source_id,
            "source_type": capped_input.source_type,
            "title": capped_input.title,
            "original_url": capped_input.original_url,
            "filename": capped_input.filename,
            "content_text": capped_input.content_text,
        },
        ensure_ascii=True,
        sort_keys=True,
    )


def normalize_provider_output(output: AIProviderOutput) -> AIProviderOutput:
    try:
        return AIProviderOutput(
            summary=output.summary.strip(),
            ai_generated_tags=[tag.strip().lower() for tag in output.ai_generated_tags if tag.strip()],
        )
    except ValidationError as error:
        raise AIGenerationError("AI provider returned an invalid structured response.") from error


def generate_with_openai(source_input: AISafeSourceInput) -> AIGenerationOutput:
    config = openai_config_from_env()
    client = OpenAI(api_key=config.api_key)
    try:
        response = client.responses.parse(
            model=config.model,
            instructions=AI_GENERATION_INSTRUCTIONS,
            input=ai_generation_payload(source_input),
            text_format=AIProviderOutput,
            text={"verbosity": "low"},
            store=False,
        )
    except Exception as error:
        logger.exception(
            "OpenAI generation request failed source_id=%s source_type=%s model=%s",
            source_input.source_id,
            source_input.source_type,
            config.model,
        )
        raise AIGenerationError("AI provider request failed.") from error
    if response.output_parsed is None:
        logger.error(
            "OpenAI generation returned empty parsed output source_id=%s source_type=%s model=%s",
            source_input.source_id,
            source_input.source_type,
            config.model,
        )
        raise AIGenerationError("AI provider returned an invalid structured response.")
    output = normalize_provider_output(response.output_parsed)
    return AIGenerationOutput(
        summary=output.summary,
        ai_generated_tags=output.ai_generated_tags,
        model=config.model,
    )
