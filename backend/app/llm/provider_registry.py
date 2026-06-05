from app.llm.base_provider import BaseLLMProvider, LLMProviderType

_PROVIDER_CLASSES: dict[LLMProviderType, type[BaseLLMProvider]] = {}
_instances: dict[str, BaseLLMProvider] = {}


def _register_defaults() -> None:
    """Lazily register built-in providers."""
    if _PROVIDER_CLASSES:
        return
    from app.llm.providers.anthropic_provider import AnthropicProvider
    from app.llm.providers.azure_openai_provider import AzureOpenAIProvider
    from app.llm.providers.ollama_provider import OllamaProvider
    from app.llm.providers.openai_provider import OpenAIProvider

    _PROVIDER_CLASSES[LLMProviderType.ANTHROPIC] = AnthropicProvider
    _PROVIDER_CLASSES[LLMProviderType.OPENAI] = OpenAIProvider
    _PROVIDER_CLASSES[LLMProviderType.OLLAMA] = OllamaProvider
    _PROVIDER_CLASSES[LLMProviderType.AZURE_OPENAI] = AzureOpenAIProvider


def register_provider(provider_type: LLMProviderType, cls: type[BaseLLMProvider]) -> None:
    _PROVIDER_CLASSES[provider_type] = cls


def get_provider(provider_type: str, api_key: str | None = None) -> BaseLLMProvider:
    """Get or create a provider instance."""
    _register_defaults()

    cache_key = f"{provider_type}:{api_key or 'default'}"
    if cache_key in _instances:
        return _instances[cache_key]

    try:
        pt = LLMProviderType(provider_type)
    except ValueError:
        raise ValueError(
            f"Unknown provider: {provider_type}. "
            f"Available: {[t.value for t in LLMProviderType]}"
        )

    cls = _PROVIDER_CLASSES.get(pt)
    if cls is None:
        raise ValueError(f"Provider '{provider_type}' is not registered.")

    instance = cls(api_key=api_key) if api_key else cls()
    _instances[cache_key] = instance
    return instance


def get_embedding_provider(api_key: str | None = None) -> BaseLLMProvider:
    """Get a provider that supports embeddings.

    Uses the configured LLM provider: Ollama embeds locally, OpenAI uses
    text-embedding-3-small, Anthropic falls back to OpenAI.
    """
    from app.config import settings

    provider_type = settings.default_llm_provider

    # Anthropic doesn't support embeddings — fall back to OpenAI
    if provider_type == "anthropic":
        provider_type = "openai"

    return get_provider(provider_type, api_key=api_key)
