"""Bounded Tavily discovery. Source passages, never provider-generated answers."""
import asyncio
import ipaddress
import os
from urllib.parse import urlsplit

from surreal_estate.errors import ConfigurationError
from surreal_estate.models import Evidence


def public_url(value):
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if parsed.scheme not in {"https", "http"} or not host or parsed.username or parsed.password:
            return False
        if "." not in host or host.endswith((".local", ".localhost", ".internal")):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return True
    except (ValueError, TypeError):
        return False


class TavilyClient:
    provider = "tavily_search"

    def __init__(self, http, api_key=None):
        self.http = http
        self.api_key = (api_key if api_key is not None else os.getenv("TAVILY_API_KEY", "")).strip()
        if not self.api_key:
            raise ConfigurationError("TAVILY_API_KEY is missing. Add it to this project's .env.")
        self.depth = os.getenv("TAVILY_SEARCH_DEPTH", "basic").strip()
        if self.depth not in {"basic", "advanced"}:
            raise ConfigurationError("TAVILY_SEARCH_DEPTH must be basic or advanced.")

    async def search_sources(self, query, spec, ctx, *, review=False):
        ctx.policy.require(self.provider, extraction=True)
        timeout = ctx.reserve("web_search")
        ctx.debug.register_secret(self.api_key)
        body = {
            "query": query, "search_depth": self.depth, "max_results": 5,
            "include_answer": False, "include_raw_content": "markdown",
            "include_published_date": True, "include_usage": True,
        }
        # Do not hard-filter undated discussion/review pages out of useful evidence.
        # Publication dates and the requested window are assessed by the local agent.
        event = ctx.debug.begin("Tavily · source search", {"topic": spec.topic, "body": body})
        try:
            async with asyncio.timeout(timeout):
                data = await ctx.debug.post(
                    event, self.http, "https://api.tavily.com/search", json=body,
                    headers={"Authorization": "Bearer " + self.api_key}, timeout=timeout,
                )
            sources = []
            for item in data.get("results", [])[:5]:
                if not isinstance(item, dict) or not public_url(item.get("url")):
                    continue
                snippet = item.get("content") or ""
                full = item.get("raw_content") or ""
                if not isinstance(snippet, str) or not isinstance(full, str):
                    continue
                content = ((snippet + "\n\n" + full) if full and snippet not in full else (full or snippet)).strip()[:4500]
                if not content:
                    continue
                sources.append(Evidence(
                    provider=self.provider, uri=item["url"], title=str(item.get("title") or "Web source")[:300],
                    excerpt=snippet[:1000] or content[:1000], retention="persistent", kind="reported",
                    source_updated_at=str(item["published_date"]) if item.get("published_date") else None,
                    attribution=urlsplit(item["url"]).hostname,
                    details={"content": content, "content_kind": ("mixed" if full and snippet not in full else "page_content") if full else "search_passage",
                             "topic": spec.topic, "query": query, "review_search": review},
                ))
            usage = data.get("usage") or {}
            credits = usage.get("credits", 2 if self.depth == "advanced" else 1)
            if not isinstance(credits, (int, float)) or credits < 0:
                credits = 2 if self.depth == "advanced" else 1
            ctx.debug.finish(event, parsed={"source_count": len(sources), "usage_credits": credits})
            return sources, credits
        except BaseException as exc:
            ctx.debug.finish(event, error=exc)
            raise
