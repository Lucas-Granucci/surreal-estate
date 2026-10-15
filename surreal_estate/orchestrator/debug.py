"""Run-local request/response inspection. Never part of the persisted RunReport."""

import copy
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from surreal_estate.errors import failure_reason


@dataclass
class DebugEvent:
    sequence: int
    stage: str
    started_seconds: float
    duration_seconds: float = 0
    status: str = "running"
    request: dict = field(default_factory=dict)
    response: Any = None
    parsed: Any = None
    http_status: int | None = None
    error: str | None = None


@dataclass
class DebugLog:
    events: list[DebugEvent] = field(default_factory=list)
    started: float = field(default_factory=time.monotonic)
    secrets: set[str] = field(default_factory=set, repr=False)

    def register_secret(self, value: str):
        if value:
            self.secrets.add(value)

    def clean(self, value):
        secrets = self.secrets | {
            os.getenv(name, "") for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "TAVILY_API_KEY")
        }
        if isinstance(value, str):
            for secret in sorted(filter(None, secrets), key=len, reverse=True):
                value = value.replace(secret, "[REDACTED]")
            return value
        if isinstance(value, dict):
            return {
                key: "[REDACTED]"
                if key.lower() in {"authorization", "x-goog-api-key", "api_key"}
                else self.clean(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.clean(item) for item in value]
        return copy.deepcopy(value)

    def begin(self, stage: str, request: dict) -> DebugEvent:
        event = DebugEvent(
            sequence=len(self.events) + 1,
            stage=stage,
            started_seconds=time.monotonic() - self.started,
            request=self.clean(request),
        )
        self.events.append(event)
        return event

    def finish(self, event: DebugEvent, *, parsed=None, error: BaseException | None = None):
        event.duration_seconds = time.monotonic() - self.started - event.started_seconds
        event.status = "error" if error else "complete"
        event.parsed = self.clean(parsed)
        event.error = failure_reason(error) if error else None

    async def post(
        self,
        event: DebugEvent,
        http: httpx.AsyncClient,
        url: str,
        *,
        json: dict,
        timeout: float,
        headers: dict | None = None,
    ) -> dict:
        response = await http.post(url, json=json, headers=headers, timeout=timeout)
        event.http_status = response.status_code
        try:
            body = response.json()
        except ValueError:
            # Avoid dumping HTML proxy pages and other non-JSON responses.
            event.response = {"diagnostic": "Provider returned a non-JSON response"}
            response.raise_for_status()
            raise ValueError("Provider response was not JSON") from None
        event.response = self.clean(body)
        response.raise_for_status()
        return body
