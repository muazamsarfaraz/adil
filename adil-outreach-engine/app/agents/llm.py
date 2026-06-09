from langchain_core.language_models.chat_models import BaseChatModel


# Default-stack pivot 2026-06-04: research + classify swapped from gemini-2.5-flash
# to claude-haiku-4-5 so the entire outreach engine talks to one model vendor.
# Compose stays on Sonnet for higher-quality drafting. Per-campaign llm_config
# can still override any node back to gemini if a specific tone/persona prefers
# it — get_llm() supports all three providers.
DEFAULT_LLM_CONFIG = {
    "research": {"provider": "anthropic", "model": "claude-haiku-4-5"},
    "compose": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
    "classify": {"provider": "anthropic", "model": "claude-haiku-4-5"},
}


def get_default_llm_config() -> dict:
    """Return default LLM configuration for each agent node."""
    return DEFAULT_LLM_CONFIG.copy()


def get_llm(config: dict, **kwargs) -> BaseChatModel:
    """
    Instantiate a LangChain chat model from campaign llm_config.

    Args:
        config: Dict with "provider" and "model" keys.
                e.g. {"provider": "gemini", "model": "gemini-2.5-flash"}
        **kwargs: Passed through to the model constructor (temperature, max_tokens, etc.)

    Returns:
        BaseChatModel instance.

    Raises:
        ValueError: If provider is not supported.
    """
    provider = config["provider"]
    model = config["model"]

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=model, **kwargs)
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, **kwargs)
    elif provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model, **kwargs)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
