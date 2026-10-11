"""Safe diagnostics: never include request headers, response bodies, or input values."""

import httpx


class ConfigurationError(ValueError):
    """Messages must be static developer-authored text, safe to show to the user."""


def failure_reason(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 404:
            try:
                message = exc.response.json().get("error", {}).get("message", "")
                if (
                    isinstance(message, str)
                    and "no longer available to new users" in message.lower()
                ):
                    return (
                        "HTTP 404: Google restricts this model to prior users. Choose an accessible "
                        "GEMINI_MODEL after checking grounding support and pricing; no automatic fallback."
                    )
            except (ValueError, AttributeError):
                pass
        hints = {
            400: "Request rejected; check model/tool compatibility and API key validity",
            401: "Authentication failed; check the provider API key",
            403: "Access denied; check API key restrictions and project access",
            404: "Endpoint or model unavailable; check the configured model ID",
            429: "Rate limit or quota exceeded; check project limits in the provider console",
        }
        return f"HTTP {status}: {hints.get(status, 'Provider request failed')}"
    if isinstance(exc, httpx.ConnectError):
        return "Connection failed; check the local Ollama server or provider network access"
    return type(exc).__name__
