"""Split markdown documents into section-level chunks with stable ids."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Chunk:
    id: str
    doc: str
    heading: str
    text: str


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def split_markdown(stem: str, markdown: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    heading, buffer = "overview", []

    def flush() -> None:
        body = " ".join(line.strip() for line in buffer if line.strip())
        if body:
            chunks.append(Chunk(f"{stem}::{slugify(heading)}", stem, heading, body))

    for line in markdown.splitlines():
        if line.startswith("## "):
            flush()
            heading, buffer = line[3:].strip(), []
        elif line.startswith("# "):
            continue
        else:
            buffer.append(line)
    flush()
    return chunks


def load_chunks(docs_dir: str | Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(Path(docs_dir).glob("*.md")):
        chunks.extend(split_markdown(path.stem, path.read_text(encoding="utf-8")))
    return chunks
