from langchain_core.language_models.chat_models import BaseChatModel


DEFAULT_LLM_CONFIG = {
    "research": {"provider": "gemini", "model": "gemini-2.5-flash"},
    "compose": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
    "classify": {"provider": "gemini", "model": "gemini-2.5-flash"},
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
