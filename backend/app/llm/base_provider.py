from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum


class LLMProviderType(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"
    AZURE_OPENAI = "azure_openai"


@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    finish_reason: str
    latency_ms: float


@dataclass
class LLMConfig:
    model: str
    temperature: float = 0.0
    max_tokens: int = 4096
    top_p: float = 1.0
    stop_sequences: list[str] = field(default_factory=list)


class BaseLLMProvider(ABC):
    """Abstract interface for LLM providers."""

    provider_type: LLMProviderType

    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        config: LLMConfig,
    ) -> LLMResponse:
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[LLMMessage],
        config: LLMConfig,
    ) -> AsyncIterator[str]:
        ...

    @abstractmethod
    async def generate_embedding(self, text: str) -> list[float]:
        ...

    @abstractmethod
    def list_models(self) -> list[str]:
        ...
