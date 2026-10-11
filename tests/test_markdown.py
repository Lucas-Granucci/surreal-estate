from test_frontend import outcome_fixture

from surreal_estate.synthesis.markdown import render_model_markdown
from surreal_estate.synthesis.viewer import render_html


def test_model_response_readable_markdown_and_original_text_preserved():
    outcome = outcome_fixture()
    text = "## Review themes\n\n**Opinion:** friendly service\n\n- Fast lunch\n- Busy at noon\n\n[Source](https://example.org/review)\n\n| Fact | Status |\n| --- | --- |\n| Address | Reported |"
    outcome.displays[0].response.text = text
    html = render_html(outcome)
    assert "<h2>Review themes</h2>" in html
    assert "<strong>Opinion:</strong>" in html
    assert "<li>Fast lunch</li>" in html
    assert "<th>Fact</th>" in html
    assert 'href="https://example.org/review" rel="noreferrer noopener"' in html
    assert outcome.displays[0].response.text == text


def test_model_markdown_cannot_activate_html_unsafe_links_or_remote_images():
    html = render_model_markdown(
        "<script>alert(1)</script>\n\n<img src=x onerror=bad()>\n\n"
        "[bad](javascript:alert(1))\n\n![remote](https://example.org/tracker.png)"
    )
    assert "<script>" not in html and "<img" not in html
    assert "&lt;script&gt;" in html
    assert 'href="javascript:' not in html
    assert "remote" in html and "tracker.png" not in html
