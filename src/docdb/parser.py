from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
import re
from typing import Iterable
from urllib.parse import urljoin, urlparse


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
BARE_MARKDOWN_URL_RE = re.compile(r"(?P<url>https?://[^\s)]+?\.md(?:[?#][^\s)]+)?)")


@dataclass(slots=True)
class ParsedDoc:
    platform_id: str
    title: str
    url: str
    rel_path: str
    section: str
    description: str
    content_type: str
    is_markdown: bool
    line_no: int
    source_url: str

    def to_record(self) -> dict[str, object]:
        return asdict(self)


def infer_title_from_url(url: str) -> str:
    path = PurePosixPath(urlparse(url).path)
    name = path.stem or path.name or url
    return name.replace("-", " ").replace("_", " ").strip().title()


def normalize_rel_path(url: str) -> str:
    path = urlparse(url).path.lstrip("/")
    return path or url


def infer_content_type(url: str) -> str:
    path = urlparse(url).path.lower()
    if path.endswith(".md") or path.endswith(".markdown"):
        return "markdown"
    if path.endswith("llms.txt") or path.endswith("llms-full.txt") or path.endswith(".txt"):
        return "index"
    if path.endswith(".json"):
        return "json"
    return "web"


def _clean_description(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith(":"):
        cleaned = cleaned[1:].strip()
    if cleaned.startswith("-"):
        cleaned = cleaned[1:].strip()
    return cleaned


def _build_doc(
    *,
    platform_id: str,
    title: str,
    raw_url: str,
    section: str,
    description: str,
    line_no: int,
    source_url: str,
) -> ParsedDoc:
    url = urljoin(source_url, raw_url.strip())
    content_type = infer_content_type(url)
    return ParsedDoc(
        platform_id=platform_id,
        title=title.strip() or infer_title_from_url(url),
        url=url,
        rel_path=normalize_rel_path(url),
        section=section.strip() or "General",
        description=description.strip(),
        content_type=content_type,
        is_markdown=content_type == "markdown",
        line_no=line_no,
        source_url=source_url,
    )


def parse_llms_text(text: str, source_url: str, platform_id: str) -> list[ParsedDoc]:
    current_section = "General"
    docs: list[ParsedDoc] = []
    seen_urls: set[str] = set()

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        heading = HEADING_RE.match(line)
        if heading:
            current_section = heading.group(2).strip()
            continue

        link_matches = list(MARKDOWN_LINK_RE.finditer(line))
        if link_matches:
            for match in link_matches:
                title = match.group(1).strip()
                raw_url = match.group(2).strip()
                description = _clean_description(line[match.end() :])
                doc = _build_doc(
                    platform_id=platform_id,
                    title=title,
                    raw_url=raw_url,
                    section=current_section,
                    description=description,
                    line_no=line_no,
                    source_url=source_url,
                )
                if doc.url not in seen_urls:
                    seen_urls.add(doc.url)
                    docs.append(doc)
            continue

        for match in BARE_MARKDOWN_URL_RE.finditer(line):
            raw_url = match.group("url")
            doc = _build_doc(
                platform_id=platform_id,
                title=infer_title_from_url(raw_url),
                raw_url=raw_url,
                section=current_section,
                description="",
                line_no=line_no,
                source_url=source_url,
            )
            if doc.url not in seen_urls:
                seen_urls.add(doc.url)
                docs.append(doc)

    return docs


def records_from_docs(docs: Iterable[ParsedDoc]) -> list[dict[str, object]]:
    return [doc.to_record() for doc in docs]
