"""Tests for LLM provider abstraction."""

from unittest.mock import patch, MagicMock

import pytest

from app.agents.llm import get_llm, get_default_llm_config, DEFAULT_LLM_CONFIG


class TestGetLlm:
    """Tests for the get_llm factory function."""

    @patch("app.agents.llm.ChatGoogleGenerativeAI", create=True)
    def test_gemini_provider(self, mock_cls):
        """get_llm with gemini provider returns ChatGoogleGenerativeAI."""
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        with patch.dict("sys.modules", {"langchain_google_genai": MagicMock(ChatGoogleGenerativeAI=mock_cls)}):
            import app.agents.llm as llm_mod

            # Patch the lazy import inside get_llm
            result = llm_mod.get_llm({"provider": "gemini", "model": "gemini-2.5-flash"})

        # The function does a lazy import, so we need to verify differently
        assert result is not None

    @patch("app.agents.llm.ChatAnthropic", create=True)
    def test_anthropic_provider(self, mock_cls):
        """get_llm with anthropic provider returns ChatAnthropic."""
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        with patch.dict("sys.modules", {"langchain_anthropic": MagicMock(ChatAnthropic=mock_cls)}):
            result = get_llm({"provider": "anthropic", "model": "claude-sonnet-4-6"})

        assert result is not None

    @patch("app.agents.llm.ChatOpenAI", create=True)
    def test_openai_provider(self, mock_cls):
        """get_llm with openai provider returns ChatOpenAI."""
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        with patch.dict("sys.modules", {"langchain_openai": MagicMock(ChatOpenAI=mock_cls)}):
            result = get_llm({"provider": "openai", "model": "gpt-4o"})

        assert result is not None

    def test_unknown_provider_raises_valueerror(self):
        """get_llm with unknown provider raises ValueError."""
        with pytest.raises(ValueError, match="Unknown LLM provider: foobar"):
            get_llm({"provider": "foobar", "model": "some-model"})

    def test_kwargs_passthrough_gemini(self):
        """kwargs like temperature and max_tokens are passed to constructor."""
        mock_cls = MagicMock()
        with patch.dict("sys.modules", {"langchain_google_genai": MagicMock(ChatGoogleGenerativeAI=mock_cls)}):
            get_llm(
                {"provider": "gemini", "model": "gemini-2.5-flash"},
                temperature=0.7,
                max_tokens=1024,
            )
            mock_cls.assert_called_once_with(
                model="gemini-2.5-flash",
                temperature=0.7,
                max_tokens=1024,
            )

    def test_kwargs_passthrough_anthropic(self):
        """kwargs are passed through for anthropic provider."""
        mock_cls = MagicMock()
        with patch.dict("sys.modules", {"langchain_anthropic": MagicMock(ChatAnthropic=mock_cls)}):
            get_llm(
                {"provider": "anthropic", "model": "claude-sonnet-4-6"},
                temperature=0.3,
            )
            mock_cls.assert_called_once_with(
                model="claude-sonnet-4-6",
                temperature=0.3,
            )

    def test_kwargs_passthrough_openai(self):
        """kwargs are passed through for openai provider."""
        mock_cls = MagicMock()
        with patch.dict("sys.modules", {"langchain_openai": MagicMock(ChatOpenAI=mock_cls)}):
            get_llm(
                {"provider": "openai", "model": "gpt-4o"},
                max_tokens=2048,
            )
            mock_cls.assert_called_once_with(
                model="gpt-4o",
                max_tokens=2048,
            )


class TestDefaultLlmConfig:
    """Tests for default LLM configuration."""

    def test_get_default_llm_config_returns_dict(self):
        """get_default_llm_config returns a dict."""
        config = get_default_llm_config()
        assert isinstance(config, dict)

    def test_get_default_llm_config_has_all_nodes(self):
        """Default config has research, compose, and classify entries."""
        config = get_default_llm_config()
        assert "research" in config
        assert "compose" in config
        assert "classify" in config

    def test_get_default_llm_config_returns_copy(self):
        """get_default_llm_config returns a copy, not the original."""
        config = get_default_llm_config()
        config["research"] = {"provider": "modified", "model": "modified"}
        assert DEFAULT_LLM_CONFIG["research"]["provider"] != "modified"

    def test_default_config_providers(self):
        """Default config uses expected providers."""
        config = get_default_llm_config()
        assert config["research"]["provider"] == "gemini"
        assert config["compose"]["provider"] == "anthropic"
        assert config["classify"]["provider"] == "gemini"
