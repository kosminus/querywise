import time
from collections.abc import AsyncIterator
from typing import Any

import openai

from app.llm.base_provider import (
    BaseLLMProvider,
    LLMConfig,
    LLMMessage,
    LLMProviderType,
    LLMResponse,
)


class OpenAIProvider(BaseLLMProvider):
    provider_type = LLMProviderType.OPENAI

    def __init__(self, api_key: str | None = None):
        self._client = openai.AsyncOpenAI(api_key=api_key, timeout=30.0)

    async def complete(
        self,
        messages: list[LLMMessage],
        config: LLMConfig,
    ) -> LLMResponse:
        oai_messages = [{"role": m.role, "content": m.content} for m in messages]
        request_params = self._completion_params(
            messages=oai_messages,
            config=config,
            stop=config.stop_sequences or None,
        )

        start = time.monotonic()
        response = await self._create_completion(request_params)
        elapsed_ms = (time.monotonic() - start) * 1000

        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            finish_reason=choice.finish_reason or "stop",
            latency_ms=elapsed_ms,
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        config: LLMConfig,
    ) -> AsyncIterator[str]:
        oai_messages = [{"role": m.role, "content": m.content} for m in messages]
        request_params = self._completion_params(
            messages=oai_messages,
            config=config,
            stream=True,
        )

        stream = await self._create_completion(request_params)

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def generate_embedding(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return response.data[0].embedding

    def list_models(self) -> list[str]:
        return [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
        ]

    def _completion_params(
        self,
        *,
        messages: list[dict[str, str]],
        config: LLMConfig,
        **overrides: Any,
    ) -> dict[str, Any]:
        return {
            "model": config.model,
            "messages": messages,
            "temperature": config.temperature,
            "max_completion_tokens": config.max_tokens,
            "top_p": config.top_p,
            **overrides,
        }

    async def _create_completion(self, params: dict[str, Any]) -> Any:
        try:
            return await self._client.chat.completions.create(**params)
        except openai.BadRequestError as exc:
            if not self._is_unsupported_temperature_error(exc):
                raise

            retry_params = {key: value for key, value in params.items() if key != "temperature"}
            return await self._client.chat.completions.create(**retry_params)

    def _is_unsupported_temperature_error(self, exc: openai.BadRequestError) -> bool:
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            error = body.get("error", body)
            return (
                isinstance(error, dict)
                and error.get("param") == "temperature"
                and error.get("code") == "unsupported_value"
            )

        message = str(exc).lower()
        return "temperature" in message and "unsupported" in message
