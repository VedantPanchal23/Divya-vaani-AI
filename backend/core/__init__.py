"""
Divya Vaani AI - Core Module

Lazy imports — modules are loaded only when accessed, so a single
failing dependency (e.g. faiss, groq) doesn't crash the whole app.
"""

__all__ = ['transcriber', 'llm_engine', 'rag_engine', 'tts_engine']


def __getattr__(name: str):
    """Lazy-load core sub-modules on first access."""
    if name in __all__:
        import importlib
        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
