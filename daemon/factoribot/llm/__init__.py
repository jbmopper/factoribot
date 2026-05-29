"""Provider-agnostic LLM layer.

The agent loop talks to an ``LLMClient`` (see ``base.py``). Concrete providers
are imported lazily so the core has zero hard dependencies and stays testable
offline via ``FakeClient``.
"""
from __future__ import annotations

from .base import LLMClient, LLMResponse, Message, ToolCall


def make_client(
    provider: str, model: str | None = None, key_file: str | None = None
) -> LLMClient:
    """Construct a provider client. Adapters are imported lazily."""
    provider = provider.lower()
    if provider == "openai":
        from .openai import OpenAIClient
        return OpenAIClient(model, key_file=key_file)
    if provider == "anthropic":
        from .anthropic import AnthropicClient
        return AnthropicClient(model, key_file=key_file)
    if provider == "gemini":
        from .gemini import GeminiClient
        return GeminiClient(model, key_file=key_file)
    if provider == "ollama":
        from .ollama import OllamaClient
        return OllamaClient(model)
    raise ValueError(
        f"Unknown provider '{provider}'. Available: openai, anthropic, gemini, ollama."
    )


__all__ = ["LLMClient", "LLMResponse", "Message", "ToolCall", "make_client"]
