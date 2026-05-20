"""agentsdk/memory/embedder.py

Embedder abstraction for converting text into dense float vectors.

Concrete implementations:
- :class:`LocalEmbedder`  — sentence-transformers (all-MiniLM-L6-v2 default)
- :class:`GroqEmbedder`   — stub; raises ``NotImplementedError`` until Groq ships
                             a dedicated embedding endpoint.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Embedder(Protocol):
    """Interface for text-embedding backends.

    Any object with an ``embed(texts)`` method returning a list of float
    vectors satisfies this protocol — no inheritance required.
    """

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed *texts* and return one float vector per input string."""
        ...


# ---------------------------------------------------------------------------
# LocalEmbedder — sentence-transformers
# ---------------------------------------------------------------------------


class LocalEmbedder:
    """CPU/GPU text embedder backed by ``sentence-transformers``.

    The underlying model is loaded lazily on the first :meth:`embed` call so
    importing this module has zero cost when RAG is not used.

    Args:
        model_name: Any ``sentence-transformers`` model identifier.
            Defaults to ``"all-MiniLM-L6-v2"`` (22 MB, fast, good quality).
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model: Any = None  # loaded lazily

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is required for LocalEmbedder. "
                "Install it with: pip install agentsdk-py[rag]"
            ) from exc
        self._model = SentenceTransformer(self._model_name)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return a float vector for each string in *texts*.

        Args:
            texts: Non-empty list of strings to embed.

        Returns:
            One ``list[float]`` per input string (same order, same length).
        """
        self._load()
        vectors = self._model.encode(texts, convert_to_numpy=True)
        return [v.tolist() for v in vectors]


# ---------------------------------------------------------------------------
# GroqEmbedder — placeholder for future Groq embedding endpoint
# ---------------------------------------------------------------------------


class GroqEmbedder:
    """Stub embedder for a future Groq dedicated embedding model.

    Raises :exc:`NotImplementedError` on every call.  Replace this
    implementation once Groq ships an embeddings API endpoint.

    Args:
        model: Reserved for future use.
    """

    def __init__(self, model: str = "groq-embed-v1") -> None:
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(
            "Switch to dedicated embedding model. "
            "Use LocalEmbedder or another provider until Groq ships "
            "a native embedding endpoint."
        )
