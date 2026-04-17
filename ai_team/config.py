"""Configuration for the AI Dev Team — supports any LLM provider."""

from __future__ import annotations

import itertools
import os

from dotenv import load_dotenv

load_dotenv()

# ── OpenRouter key rotation ──────────────────────────────────────────────────
def _openrouter_keys() -> list[str]:
    keys = []
    for i in range(1, 10):
        k = os.getenv(f"OPENROUTER_KEY_{i}")
        if k:
            keys.append(k)
    primary = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_COMPAT_API_KEY")
    if primary and primary not in keys:
        keys.insert(0, primary)
    return keys if keys else ([primary] if primary else [])


_or_keys = _openrouter_keys()
_key_cycle = itertools.cycle(_or_keys) if _or_keys else None


def _next_openrouter_key() -> str | None:
    if _key_cycle is None:
        return None
    return next(_key_cycle)

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
        api_key = (
            _next_openrouter_key()
            if provider_name == "openai_compat"
            else os.getenv(env_key)
        )
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


AGENT_ROLE_DEFAULTS: dict[str, str] = {
    "requirements": os.getenv("AGENT_MODEL_REQUIREMENTS", os.getenv("LLM_MODEL_CHEAP", "")),
    "designer":     os.getenv("AGENT_MODEL_DESIGNER",     os.getenv("LLM_MODEL_CHEAP", "")),
    "evaluator":    os.getenv("AGENT_MODEL_EVALUATOR",    os.getenv("LLM_MODEL_CHEAP", "")),
    "docs":         os.getenv("AGENT_MODEL_DOCS",         os.getenv("LLM_MODEL_CHEAP", "")),
    "architect":    os.getenv("AGENT_MODEL_ARCHITECT",    ""),
    "coder":        os.getenv("AGENT_MODEL_CODER",        ""),
    "reviewer":     os.getenv("AGENT_MODEL_REVIEWER",     ""),
    "tester":       os.getenv("AGENT_MODEL_TESTER",       ""),
    "security":     os.getenv("AGENT_MODEL_SECURITY",     ""),
    "auditor":      os.getenv("AGENT_MODEL_AUDITOR",      ""),
    "planner":      os.getenv("AGENT_MODEL_PLANNER",      ""),
    "debugger":      os.getenv("AGENT_MODEL_DEBUGGER",      ""),
    "frontend_web":    os.getenv("AGENT_MODEL_FRONTEND_WEB",    ""),
    "frontend_mobile":   os.getenv("AGENT_MODEL_FRONTEND_MOBILE",   ""),
    "frontend_desktop":  os.getenv("AGENT_MODEL_FRONTEND_DESKTOP",  ""),
}


def get_llm_for_agent(agent_name: str, temperature=None, max_tokens=None):
    """Return an LLM instance for the given agent role, respecting per-agent model overrides."""
    model_override = AGENT_ROLE_DEFAULTS.get(agent_name, "") or None
    return get_llm(model_override=model_override, temperature=temperature, max_tokens=max_tokens)


def get_project_dir(override: str | None = None) -> str:
    """Get the project directory to work on."""
    return override or os.getenv(
        "DEFAULT_PROJECT_DIR", os.path.expanduser("~/Villaex/VoiceAgentAPI")
    )


def get_max_iterations() -> int:
    return int(os.getenv("MAX_ITERATIONS", "5"))
