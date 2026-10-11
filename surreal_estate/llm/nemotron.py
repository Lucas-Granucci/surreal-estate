import asyncio
import os
from typing import TypeVar
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ValidationError

from surreal_estate.errors import ConfigurationError
from surreal_estate.orchestrator.context import RunContext

T = TypeVar("T", bound=BaseModel)


class NemotronClient:
    """Local Ollama JSON-schema generation; no agent framework or arbitrary tools."""

    def __init__(
        self, http: httpx.AsyncClient, model: str | None = None, base_url: str | None = None
    ):
        self.http = http
        self.model = model or os.getenv("OLLAMA_MODEL", "nemotron-3-nano:4b")
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip(
            "/"
        )
        parsed = urlsplit(self.base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ConfigurationError(
                "OLLAMA_BASE_URL must use a local loopback HTTP endpoint, such as http://127.0.0.1:11434."
            )

    async def generate(self, schema: type[T], system: str, payload: str, ctx: RunContext) -> T:
        timeout = ctx.reserve("llm")
        if len(payload) > 40_000:
            raise ValueError("Model input exceeds character cap")
        request = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": payload},
            ],
            "format": schema.model_json_schema(),
            "stream": False,
            "options": {"temperature": 0, "num_predict": ctx.budget.output_tokens_per_call},
        }
        url = f"{self.base_url}/api/chat"
        event = ctx.debug.begin(f"Nemotron · {schema.__name__}", {"endpoint": url, "body": request})
        try:
            async with asyncio.timeout(timeout):
                body = await ctx.debug.post(event, self.http, url, json=request, timeout=timeout)
                if not body.get("done") or body.get("done_reason") == "length":
                    raise ValueError("Incomplete Ollama response")
                result = schema.model_validate_json(body["message"]["content"])
            ctx.debug.finish(event, parsed=result.model_dump(mode="json"))
            return result
        except BaseException as exc:
            ctx.debug.finish(
                event,
                error=exc,
                parsed={
                    "validation_errors": exc.errors(
                        include_input=False, include_context=False, include_url=False
                    )
                }
                if isinstance(exc, ValidationError)
                else None,
            )
            raise
