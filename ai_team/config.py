"""Configuration for the AI Dev Team — supports any LLM provider."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Provider → (package import path, class name, required env var, extra kwargs)
PROVIDERS = {
    # ── Paid ──
    "anthropic": {
        "module": "langchain_anthropic",
        "class": "ChatAnthropic",
        "env_key": "ANTHROPIC_API_KEY",
        "model_kwarg": "model",
        "prefixes": ["claude"],
    },
    "openai": {
        "module": "langchain_openai",
        "class": "ChatOpenAI",
        "env_key": "OPENAI_API_KEY",
        "model_kwarg": "model",
        "prefixes": ["gpt", "o1", "o3", "o4"],
    },
    "google": {
        "module": "langchain_google_genai",
        "class": "ChatGoogleGenerativeAI",
        "env_key": "GOOGLE_API_KEY",
        "model_kwarg": "model",
        "prefixes": ["gemini"],
    },
    # ── Free / cheap ──
    "groq": {
        "module": "langchain_groq",
        "class": "ChatGroq",
        "env_key": "GROQ_API_KEY",
        "model_kwarg": "model",
        "prefixes": ["llama", "mixtral", "gemma", "deepseek"],
    },
    "huggingface": {
        "module": "langchain_huggingface",
        "class": "ChatHuggingFace",
        "env_key": "HUGGINGFACEHUB_API_TOKEN",
        "model_kwarg": "model_id",
        "prefixes": [],  # explicit provider only
    },
    "together": {
        "module": "langchain_together",
        "class": "ChatTogether",
        "env_key": "TOGETHER_API_KEY",
        "model_kwarg": "model",
        "prefixes": [],
    },
    "fireworks": {
        "module": "langchain_fireworks",
        "class": "ChatFireworks",
        "env_key": "FIREWORKS_API_KEY",
        "model_kwarg": "model",
        "prefixes": [],
    },
    "mistral": {
        "module": "langchain_mistralai",
        "class": "ChatMistralAI",
        "env_key": "MISTRAL_API_KEY",
        "model_kwarg": "model",
        "prefixes": ["mistral", "codestral", "pixtral"],
    },
    "deepseek": {
        "module": "langchain_openai",
        "class": "ChatOpenAI",
        "env_key": "DEEPSEEK_API_KEY",
        "model_kwarg": "model",
        "prefixes": ["deepseek"],
        "base_url": "https://api.deepseek.com",
    },
    # ── Local / self-hosted ──
    "ollama": {
        "module": "langchain_ollama",
        "class": "ChatOllama",
        "env_key": None,  # no API key needed
        "model_kwarg": "model",
        "prefixes": [],
        "base_url_env": "OLLAMA_BASE_URL",
        "base_url_default": "http://localhost:11434",
    },
    # ── OpenAI-compatible (any provider with OpenAI-compatible API) ──
    "openai_compat": {
        "module": "langchain_openai",
        "class": "ChatOpenAI",
        "env_key": "OPENAI_COMPAT_API_KEY",
        "model_kwarg": "model",
        "prefixes": [],
        "base_url_env": "OPENAI_COMPAT_BASE_URL",
    },
}


def _detect_provider(model: str, explicit_provider: str | None = None) -> str:
    """Detect which provider to use from model name or explicit setting."""
    if explicit_provider:
        if explicit_provider not in PROVIDERS:
            raise ValueError(
                f"Unknown provider: {explicit_provider}. "
                f"Available: {', '.join(PROVIDERS.keys())}"
            )
        return explicit_provider

    model_lower = model.lower()
    for provider_name, cfg in PROVIDERS.items():
        for prefix in cfg["prefixes"]:
            if model_lower.startswith(prefix):
                return provider_name

    # Fallback: check which API keys are set
    for provider_name, cfg in PROVIDERS.items():
        env_key = cfg.get("env_key")
        if env_key and os.getenv(env_key):
            return provider_name

    raise ValueError(
        f"Cannot detect provider for model '{model}'. "
        f"Set LLM_PROVIDER explicitly or provide an API key. "
        f"Available providers: {', '.join(PROVIDERS.keys())}"
    )


def get_llm(
    model_override: str | None = None,
    provider_override: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
):
    """Get the configured LLM instance. Supports any provider.

    Auto-detects provider from model name, or use LLM_PROVIDER env var.
    """
    import importlib

    model = model_override or os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")
    provider_name = provider_override or os.getenv("LLM_PROVIDER")
    provider_name = _detect_provider(model, provider_name)
    cfg = PROVIDERS[provider_name]

    temp = temperature if temperature is not None else float(os.getenv("LLM_TEMPERATURE", "0"))
    tokens = max_tokens or int(os.getenv("LLM_MAX_TOKENS", "8192"))

    # Import the class dynamically
    try:
        mod = importlib.import_module(cfg["module"])
    except ImportError:
        raise ImportError(
            f"Provider '{provider_name}' requires: pip install {cfg['module'].replace('_', '-')}\n"
            f"Run: pip install {cfg['module'].replace('_', '-')}"
        )

    cls = getattr(mod, cfg["class"])

    kwargs = {
        cfg["model_kwarg"]: model,
        "temperature": temp,
        "max_tokens": tokens,
    }

    # Handle API keys
    env_key = cfg.get("env_key")
    if env_key:
        api_key = os.getenv(env_key)
        if api_key:
            # DeepSeek and OpenAI-compat use openai_api_key
            if provider_name in ("deepseek", "openai_compat"):
                kwargs["openai_api_key"] = api_key
            elif provider_name == "openai":
                kwargs["openai_api_key"] = api_key
            elif provider_name == "anthropic":
                kwargs["anthropic_api_key"] = api_key
            elif provider_name == "google":
                kwargs["google_api_key"] = api_key
            else:
                kwargs["api_key"] = api_key

    # Handle custom base URLs
    if "base_url" in cfg:
        kwargs["base_url"] = cfg["base_url"]
    elif "base_url_env" in cfg:
        base_url = os.getenv(cfg["base_url_env"], cfg.get("base_url_default", ""))
        if base_url:
            kwargs["base_url"] = base_url

    return cls(**kwargs)


def get_project_dir(override: str | None = None) -> str:
    """Get the project directory to work on."""
    return override or os.getenv(
        "DEFAULT_PROJECT_DIR", os.path.expanduser("~/Villaex/VoiceAgentAPI")
    )


def get_max_iterations() -> int:
    return int(os.getenv("MAX_ITERATIONS", "5"))
