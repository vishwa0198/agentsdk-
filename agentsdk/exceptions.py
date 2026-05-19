"""agentsdk/exceptions.py

SDK-level exception hierarchy.  Provider-specific errors (groq, anthropic, …)
are always wrapped into one of these types so the agent loop never needs to
import anything from a provider library directly.
"""


class AgentSDKError(Exception):
    """Base class for all agentsdk errors."""


# ---------------------------------------------------------------------------
# LLM provider errors
# ---------------------------------------------------------------------------


class LLMProviderError(AgentSDKError):
    """Catch-all for provider errors that don't fit a more specific type.

    Also serves as the base class for the more specific variants below,
    so callers can ``except LLMProviderError`` to handle all LLM failures
    in one place.
    """


class LLMRateLimitError(LLMProviderError):
    """The LLM provider returned HTTP 429 — request was rate-limited."""


class LLMAuthError(LLMProviderError):
    """The LLM provider returned HTTP 401 — invalid or missing API key."""


# ---------------------------------------------------------------------------
# Graph execution errors
# ---------------------------------------------------------------------------


class GraphExecutionError(AgentSDKError):
    """A node inside an AgentGraph failed during execution.

    Attributes
    ----------
    node_id:
        The ``node_id`` of the node that failed.
    reason:
        The error message from the failing node.
    """

    def __init__(self, node_id: str, reason: str) -> None:
        self.node_id = node_id
        self.reason = reason
        super().__init__(f"Node '{node_id}' failed: {reason}")
