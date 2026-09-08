"""Structured tool errors — agents receive these, never raw tracebacks."""


class ToolGatewayError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class PolicyDenied(ToolGatewayError):
    def __init__(self, message: str) -> None:
        super().__init__("policy_denied", message)


class ToolTimeout(ToolGatewayError):
    def __init__(self, tool: str, timeout_s: float) -> None:
        super().__init__("timeout", f"{tool} exceeded {timeout_s}s")


class ToolFailed(ToolGatewayError):
    def __init__(self, tool: str, message: str) -> None:
        super().__init__("tool_failed", f"{tool}: {message}")


class MissingIdempotencyKey(ToolGatewayError):
    def __init__(self, tool: str) -> None:
        super().__init__(
            "missing_idempotency_key",
            f"{tool} is a write tool and requires idempotency_key",
        )
