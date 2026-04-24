from __future__ import annotations

import re
import httpx
from bs4 import BeautifulSoup

try:
    from readability import Document
except Exception:
    Document = None  # type: ignore[assignment]


MAX_TEXT_CHARS = 12000


async def fetch_url(url: str, timeout: float = 15.0) -> str:
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, headers={
        "User-Agent": "Mozilla/5.0 (CrowdmSim/0.1)",
        "Accept": "text/html,application/xhtml+xml",
    }) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


def html_to_readable_text(html: str) -> str:
    if Document is not None:
        try:
            doc = Document(html)
            summary_html = doc.summary(html_partial=True)
            title = (doc.short_title() or "").strip()
            body_text = _soup_text(summary_html)
            combined = f"{title}\n\n{body_text}".strip() if title else body_text
            if combined:
                return _truncate(combined)
        except Exception:
            pass
    return _truncate(_soup_text(html))


def _soup_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines))


def _truncate(text: str) -> str:
    if len(text) <= MAX_TEXT_CHARS:
        return text
    return text[:MAX_TEXT_CHARS] + "\n\n[...truncated...]"


async def resolve_stage_text(*, url: str | None, html: str | None, text: str | None) -> str | None:
    """Return a readable text representation from whichever input is provided."""
    if text:
        return _truncate(text)
    if html:
        return html_to_readable_text(html)
    if url:
        try:
            fetched = await fetch_url(url)
            return html_to_readable_text(fetched)
        except Exception as exc:
            return f"(Failed to fetch {url}: {exc})"
    return None
