"""Safe diagnostics: never include request headers, response bodies, or input values."""

import httpx


class ConfigurationError(ValueError):
    """Messages must be static developer-authored text, safe to show to the user."""


class BriefResponseError(ValueError):
    """Static, safe explanation of a rejected final-writing response."""


def failure_reason(exc: Exception, *, provider: str | None = None) -> str:
    if isinstance(exc, BriefResponseError):
        return str(exc)
    if provider:
        source = {
            "census": "Census Geocoder",
            "openstreetmap": "OpenStreetMap / Overpass",
            "wprdc_assessments": "WPRDC assessments",
            "wprdc_permits": "WPRDC permits",
            "wprdc_closures": "WPRDC street closures",
        }.get(provider, "Public data provider")
        if isinstance(exc, httpx.ConnectError):
            return f"Connection to {source} failed before an HTTP response. The provider or network connection is unavailable; retry later. No findings were inferred"
        if isinstance(exc, httpx.TimeoutException):
            return f"{source} did not respond within the request deadline; retry later"
        if isinstance(exc, httpx.HTTPStatusError):
            return f"{source} returned HTTP {exc.response.status_code}; no findings were inferred"
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
                        "GEMINI_SYNTHESIS_MODEL after checking generation access and pricing; no automatic fallback."
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
