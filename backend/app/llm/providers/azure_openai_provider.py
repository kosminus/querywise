"""Azure OpenAI provider.

Lets the entire QueryWise pipeline (SQL generation + embeddings) run against an
Azure OpenAI deployment inside a customer's VPC. It reuses ``OpenAIProvider``'s
request/response handling and only swaps the underlying client for
``AsyncAzureOpenAI``.

Configure via ``settings``:
    AZURE_OPENAI_ENDPOINT     e.g. https://my-resource.openai.azure.com
    AZURE_OPENAI_API_KEY      Azure OpenAI key
    AZURE_OPENAI_API_VERSION  e.g. 2024-10-21
    AZURE_OPENAI_DEPLOYMENT   embedding deployment name (optional)

On Azure, ``model`` names map to *deployment* names. Set DEFAULT_LLM_MODEL /
EMBEDDING_MODEL to your deployment names.
"""

from __future__ import annotations

import openai

from app.config import settings
from app.llm.base_provider import LLMProviderType
from app.llm.providers.openai_provider import OpenAIProvider


class AzureOpenAIProvider(OpenAIProvider):
    provider_type = LLMProviderType.AZURE_OPENAI

    def __init__(self, api_key: str | None = None) -> None:
        endpoint = settings.azure_openai_endpoint
        if not endpoint:
            raise ValueError("AZURE_OPENAI_ENDPOINT must be set to use the azure_openai provider.")
        # Don't call super().__init__ — it builds a plain OpenAI client.
        self._client = openai.AsyncAzureOpenAI(
            api_key=api_key or settings.azure_openai_api_key,
            azure_endpoint=endpoint,
            api_version=settings.azure_openai_api_version,
            timeout=30.0,
        )

    async def generate_embedding(self, text: str) -> list[float]:
        # On Azure the embedding "model" is the deployment name.
        model = settings.azure_openai_deployment or settings.embedding_model
        response = await self._client.embeddings.create(model=model, input=text)
        return response.data[0].embedding

    def list_models(self) -> list[str]:
        # Azure exposes customer-named deployments, not fixed model ids.
        return [settings.default_llm_model]
