"""Readable model Markdown with active HTML and unsafe URL schemes disabled."""

from html import escape

from markdown_it import MarkdownIt


def render_model_markdown(text: str) -> str:
    parser = MarkdownIt("commonmark", {"html": False, "breaks": True}).enable(
        ["table", "strikethrough"]
    )

    def link_open(tokens, index, options, env):
        tokens[index].attrSet("rel", "noreferrer noopener")
        return parser.renderer.renderToken(tokens, index, options, env)

    def image(tokens, index, options, env):
        # Model output must not silently fetch remote images or tracking URLs.
        alt = parser.renderer.renderInlineAsText(tokens[index].children or [], options, env)
        return escape(alt)

    parser.renderer.rules["link_open"] = link_open
    parser.renderer.rules["image"] = image
    return parser.render(text)
