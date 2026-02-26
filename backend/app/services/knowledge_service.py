"""Service for importing and managing knowledge documents.

Supports both plain-text and HTML content (e.g. Confluence pages).
HTML is parsed into clean text, split by heading sections, then chunked.
"""

import hashlib
import logging
import re
import uuid
from html import unescape
from html.parser import HTMLParser

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.services.embedding_service import embed_text

logger = logging.getLogger(__name__)

# Chunking parameters (word-based, matching reference impl)
MAX_CHUNK_WORDS = 450
OVERLAP_WORDS = 80

# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

_LOOKS_LIKE_HTML = re.compile(r"<[a-zA-Z][^>]*>", re.DOTALL)


class _HTMLTextParser(HTMLParser):
    """Converts HTML to clean plain text, respecting block boundaries."""

    _BLOCK_TAGS = {
        "address", "article", "aside", "blockquote", "div", "dl",
        "fieldset", "figcaption", "figure", "footer", "form",
        "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr",
        "li", "main", "nav", "ol", "p", "pre", "section",
        "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
    }
    _SKIP_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return
        if tag == "br":
            self._parts.append("\n")
        if tag == "li":
            self._parts.append("- ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if self._skip_depth > 0:
            return
        if tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        cleaned = unescape(data)
        if cleaned:
            self._parts.append(cleaned)

    def text(self) -> str:
        raw = "".join(self._parts)
        lines = []
        for line in raw.splitlines():
            compact = re.sub(r"\s+", " ", line).strip()
            if compact:
                lines.append(compact)
        return "\n".join(lines)


def _extract_main_content(html: str) -> str:
    """Try to extract the main content area, stripping chrome/nav."""
    # Prefer <main> or <article> if present
    for tag in ("main", "article"):
        match = re.search(
            rf"(?is)<{tag}[^>]*>(.*)</{tag}>", html
        )
        if match:
            return match.group(1)
    # Fallback: common content divs (Wikipedia, Confluence, etc.)
    for pattern in (
        r'(?is)<div[^>]+id=["\']mw-content-text["\'][^>]*>(.*)</div>',
        r'(?is)<div[^>]+id=["\']main-content["\'][^>]*>(.*)</div>',
        r'(?is)<div[^>]+class=["\'][^"\']*content[^"\']*["\'][^>]*>(.*)</div>',
    ):
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return html


def _clean_html(html: str) -> str:
    """Strip boilerplate elements and extract main content from HTML."""
    # Strip comments
    cleaned = re.sub(r"(?is)<!--.*?-->", "", html)
    # Strip script/style/noscript/svg blocks
    cleaned = re.sub(
        r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", "", cleaned
    )
    # Strip navigation chrome (nav, header, footer, aside)
    cleaned = re.sub(
        r"(?is)<(nav|header|footer|aside)[^>]*>.*?</\1>", "", cleaned
    )
    # Try to narrow to main content area
    cleaned = _extract_main_content(cleaned)
    return cleaned


def _html_to_text(html_fragment: str) -> str:
    parser = _HTMLTextParser()
    parser.feed(html_fragment)
    parser.close()
    return parser.text()


def _split_sections(
    html: str,
) -> tuple[str | None, list[tuple[str | None, str]]]:
    """Split HTML by headings, returning (auto_title, [(section_path, text)])."""
    heading_re = re.compile(r"(?is)<h([1-6])[^>]*>(.*?)</h\1>")
    sections: list[tuple[str | None, str]] = []
    heading_stack: list[str] = []
    title: str | None = None

    cursor = 0
    for match in heading_re.finditer(html):
        before = html[cursor : match.start()]
        before_text = _html_to_text(before)
        if before_text:
            path = " > ".join(heading_stack) or None
            sections.append((path, before_text))

        level = int(match.group(1))
        heading_text = (
            _html_to_text(match.group(2)) or "Untitled Section"
        )
        if title is None:
            title = heading_text

        while len(heading_stack) >= level:
            heading_stack.pop()
        heading_stack.append(heading_text)

        cursor = match.end()

    tail_text = _html_to_text(html[cursor:])
    if tail_text:
        path = " > ".join(heading_stack) or None
        sections.append((path, tail_text))

    if not sections:
        whole = _html_to_text(html)
        if whole:
            sections.append((None, whole))

    return title, sections


# ---------------------------------------------------------------------------
# Chunking (word-based with overlap)
# ---------------------------------------------------------------------------


def _chunk_words(
    text: str,
    max_words: int = MAX_CHUNK_WORDS,
    overlap_words: int = OVERLAP_WORDS,
) -> list[str]:
    words = text.split()
    if not words:
        return []
    if len(words) <= max_words:
        return [" ".join(words)]

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = max(0, end - overlap_words)
    return chunks


def _clean_text(text: str) -> str:
    """Normalize whitespace while preserving paragraph boundaries."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[^\S\n]+", " ", text)
    return text.strip()


def _content_hash(
    connection_id: uuid.UUID,
    source_url: str | None,
    content: str,
) -> str:
    key = f"{connection_id}:{source_url or ''}:{content}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Import logic
# ---------------------------------------------------------------------------


async def import_document(
    db: AsyncSession,
    connection_id: uuid.UUID,
    title: str,
    content: str,
    source_url: str | None = None,
) -> KnowledgeDocument:
    """Import text or HTML content as a knowledge document with embedded chunks.

    If content looks like HTML (contains tags), it is parsed into clean text
    with section-aware chunking.  Plain text is chunked directly.

    Re-importing the same source_url replaces the old document's chunks.
    """
    is_html = bool(_LOOKS_LIKE_HTML.search(content))

    if is_html:
        cleaned_html = _clean_html(content)
        auto_title, sections = _split_sections(cleaned_html)
        document_title = title or auto_title or "Imported Document"
        # Build chunk texts with section paths
        chunk_texts: list[str] = []
        for section_path, section_text in sections:
            prefixed = section_text
            if section_path:
                prefixed = f"{section_path}\n{section_text}"
            chunk_texts.extend(_chunk_words(prefixed))
    else:
        document_title = title
        cleaned = _clean_text(content)
        chunk_texts = _chunk_words(cleaned)

    # Dedup: if same source_url, delete existing document for this connection
    if source_url:
        existing_result = await db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.connection_id == connection_id,
                KnowledgeDocument.source_url == source_url,
            )
        )
        for old_doc in existing_result.scalars().all():
            await db.delete(old_doc)  # cascades to chunks
        await db.flush()

    doc = KnowledgeDocument(
        connection_id=connection_id,
        title=document_title,
        source_url=source_url,
        content=content,
        chunk_count=len(chunk_texts),
    )
    db.add(doc)
    await db.flush()

    for idx, chunk_text in enumerate(chunk_texts):
        chunk = KnowledgeChunk(
            document_id=doc.id,
            chunk_index=idx,
            content=chunk_text,
            content_hash=_content_hash(connection_id, source_url, chunk_text),
        )
        db.add(chunk)
        await db.flush()

        try:
            chunk.chunk_embedding = await embed_text(chunk_text)
        except Exception:
            logger.warning(
                "Failed to embed knowledge chunk %d of '%s'",
                idx,
                document_title,
                exc_info=True,
            )

    return doc
