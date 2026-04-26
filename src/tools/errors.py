from __future__ import annotations


class ToolError(RuntimeError):
    """Base exception for tool execution failures."""


class AuthError(ToolError):
    """Raised when a tool cannot authenticate with an external service."""


class RateLimitError(ToolError):
    """Raised when a tool action exceeds a configured rate limit."""


class PolicyError(ToolError):
    """Raised when a tool action violates a configured safety policy."""
