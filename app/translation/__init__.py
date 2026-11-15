"""Load provider dependencies only when that provider is requested."""
from importlib import import_module

__all__ = [
    "BaseTranslator",
    "OpenAITranslator",
    "GroqTranslator",
    "MockTranslator",
    "GoogleTranslator",
    "LocalTranslator",
    "ModelManager"
]

_PROVIDER_MODULES = {
    "BaseTranslator": "translator",
    "OpenAITranslator": "openai_translator",
    "MockTranslator": "openai_translator",
    "GroqTranslator": "groq_translator",
    "GoogleTranslator": "google_translator",
    "LocalTranslator": "local_translator",
    "ModelManager": "model_manager",
}


def __getattr__(name):
    if name not in _PROVIDER_MODULES:
        raise AttributeError(name)
    value = getattr(import_module(f"{__name__}.{_PROVIDER_MODULES[name]}"), name)
    globals()[name] = value
    return value
