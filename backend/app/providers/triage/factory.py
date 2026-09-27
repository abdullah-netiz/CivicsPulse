from app.config import Settings
from app.providers.cache import CacheProvider
from app.providers.triage.base import TriageProvider
from app.providers.triage.gemini import GeminiTriage
from app.providers.triage.llm import GroqLLMTriage
from app.providers.triage.ollama import OllamaTriage
from app.providers.triage.rules import RuleBasedTriage
from app.providers.triage.simulated import SimulatedTriage


def build_triage_provider(settings: Settings, cache: CacheProvider | None = None) -> TriageProvider:
    """Build the active triage provider selected by TRIAGE_PROVIDER.

    PDF 2.5: four implementations -- LLMTriage (hosted, production path),
    OllamaTriage (offline container), RuleBasedTriage (deterministic
    fallback), SimulatedTriage (seeded CI fake with failure injection).
    The content-hash cache is wired into every non-deterministic provider.
    """
    if settings.triage_provider == "llm":
        return GroqLLMTriage(
            api_key=settings.groq_api_key or "",
            model=settings.groq_model,
            timeout_seconds=settings.triage_timeout_seconds,
            cache=cache,
        )
    if settings.triage_provider == "ollama":
        return OllamaTriage(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            timeout_seconds=settings.triage_timeout_seconds,
            cache=cache,
        )
    if settings.triage_provider == "gemini":
        return GeminiTriage(
            api_key=settings.gemini_api_key or "",
            model=settings.gemini_model,
            timeout_seconds=settings.gemini_timeout_seconds,
            cache=cache,
        )
    if settings.triage_provider == "simulated":
        return SimulatedTriage()
    return RuleBasedTriage()
