import sys

import httpx
import pytest

from surreal_estate.cli import main
from surreal_estate.errors import ConfigurationError, failure_reason
from surreal_estate.llm.brief import GeminiBriefWriter


@pytest.mark.parametrize("key", [None, "", "   "])
def test_missing_key_cli_diagnosis_without_network(monkeypatch, capsys, key, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    if key is not None:
        monkeypatch.setenv("TAVILY_API_KEY", key)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "surreal-estate",
            "research",
            "--address",
            "414 Grant Street, Pittsburgh, PA 15219",
            "--web",
        ],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    output = capsys.readouterr().err
    assert "TAVILY_API_KEY is missing" in output
    assert ".env" in output


async def test_invalid_model_does_not_expose_value(monkeypatch):
    monkeypatch.setenv("GEMINI_SYNTHESIS_MODEL", "https://secret.example/key=SECRET")
    async with httpx.AsyncClient() as http:
        with pytest.raises(ConfigurationError) as error:
            GeminiBriefWriter(http, api_key="SECRET")
    assert "GEMINI_SYNTHESIS_MODEL" in str(error.value)
    assert "SECRET" not in str(error.value)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500])
def test_http_diagnostic_excludes_secrets(status):
    request = httpx.Request(
        "POST", "https://example.org/?key=SECRET", headers={"x-goog-api-key": "SECRET"}
    )
    response = httpx.Response(status, request=request, text="SECRET")
    with pytest.raises(httpx.HTTPStatusError) as error:
        response.raise_for_status()
    message = failure_reason(error.value)
    assert f"HTTP {status}" in message
    assert "SECRET" not in message
    if status == 429:
        assert "quota" in message


async def test_model_discovery_pagination_and_method_filtering():
    from surreal_estate.llm.diagnostics import inspect_models

    def handler(request):
        assert request.headers["x-goog-api-key"] == "test-key"
        assert "test-key" not in str(request.url)
        if request.url.params.get("pageToken") == "next":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "models/gemini-2.5-flash",
                            "supportedGenerationMethods": ["generateContent"],
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "models/embedding", "supportedGenerationMethods": ["embedContent"]}
                ],
                "nextPageToken": "next",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        present, models = await inspect_models(
            GeminiBriefWriter(http, api_key="test-key", model="gemini-2.5-flash")
        )
    assert present
    assert models == ["gemini-2.5-flash"]


async def test_failed_run_viewer_and_html_escaping():
    from surreal_estate.evals.fixtures import fixture_case
    from surreal_estate.models import ChannelResult, Coverage, RunReport
    from surreal_estate.orchestrator.runner import RunOutcome
    from surreal_estate.synthesis.viewer import render_html

    outcome = RunOutcome(
        RunReport(
            case=fixture_case(),
            result=ChannelResult(
                coverage=[
                    Coverage(
                        channel="web",
                        topic="research",
                        status="error",
                        reason="<script>secret()</script>",
                    )
                ]
            ),
        ),
        [],
    )
    html = render_html(outcome)
    assert "Pipeline coverage" in html
    assert "No validated plan" in html
    assert "&lt;script&gt;" in html
    assert "<script>" not in html


def test_restricted_model_error_is_actionable_and_redacted():
    request = httpx.Request("POST", "https://example.org")
    response = httpx.Response(
        404,
        request=request,
        json={"error": {"message": "Model SECRET is no longer available to new users."}},
    )
    with pytest.raises(httpx.HTTPStatusError) as error:
        response.raise_for_status()
    message = failure_reason(error.value)
    assert "prior users" in message
    assert "SECRET" not in message
