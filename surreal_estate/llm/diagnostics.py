"""Read-only Gemini model discovery. No generation or grounded-content logging."""

import re

from surreal_estate.llm.gemini import GroundedSearchClient


async def inspect_models(client: GroundedSearchClient) -> tuple[bool, list[str]]:
    available = set()
    page_token = None
    seen = set()
    for _ in range(20):
        params = {"pageSize": 1000}
        if page_token:
            params["pageToken"] = page_token
        response = await client.http.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": client.api_key},
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()
        for item in body.get("models", []):
            name = item.get("name", "").removeprefix("models/")
            if "generateContent" in item.get("supportedGenerationMethods", []) and re.fullmatch(
                r"[a-zA-Z0-9._-]+", name
            ):
                available.add(name)
        page_token = body.get("nextPageToken")
        if not page_token:
            return client.model in available, sorted(available)
        if page_token in seen:
            break
        seen.add(page_token)
    raise ValueError("Incomplete model discovery")
