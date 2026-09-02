"""
Markdown preprocessing utilities for clean PDF conversion.

Addresses common formatting quirks when rendering Markdown via python-markdown:
1. NBSP (\\xa0) -> standard space (preserves list/indent parsing)
2. Normalized list indentation: converts 2-space CommonMark nesting to 4-space indent
3. Enforces blank lines around tables, fenced code blocks, quotes, and lists
4. Extracts or normalizes the document title
"""
from __future__ import annotations
import re
from pathlib import Path

# Citations like [cite: 123], [cite_start], 【cite ...】
_CITE_RE = re.compile(r'(?i)[\[【]\s*cite\s*[:\s]*[^\]】]*[\]】]')

# Block patterns
_FENCE_RE = re.compile(r'^\s*(`{3,}|~{3,})')
_TABLE_SEP_RE = re.compile(r'^\s*\|?\s*:?-{1,}:?\s*(?:\|\s*:?-{1,}:?\s*)+\|?\s*$')
_HEADING_RE = re.compile(r'^#{1,6}\s')
_LIST_RE = re.compile(r'^([-*+]|\d+\.)\s')
_ANYLIST_RE = re.compile(r'^(\s*)([-*+]|\d+\.)\s')
_HR_RE = re.compile(r'^-{3,}\s*$')


def normalize_list_indent(text: str) -> str:
    """Normalize list items so each nested level has a 4-space indent.

    CommonMark often uses 2 spaces for list continuation/nesting ('-' -> 2 spaces),
    whereas python-markdown expects tab_length=4. This recalculates nesting depth
    based on relative original indentation without altering contents.
    """
    out: list[str] = []
    stack: list[int] = []
    for line in text.split("\n"):
        m = _ANYLIST_RE.match(line)
        if m:
            si = len(m.group(1))
            while stack and si < stack[-1]:
                stack.pop()
            if not stack or si > stack[-1]:
                stack.append(si)
            out.append("    " * (len(stack) - 1) + line.lstrip())
        elif line.strip() == "":
            out.append(line)
        elif line[:1] not in (" ", "\t"):
            stack = []
            out.append(line)
        else:
            out.append(line)
    return "\n".join(out)


def _classify(line: str) -> str:
    s = line.strip()
    if not s:
        return "blank"
    if _FENCE_RE.match(line):
        return "fence"
    if _HEADING_RE.match(line):
        return "heading"
    if line[:1] in (" ", "\t"):
        return "indent"
    if _LIST_RE.match(line):
        return "list"
    if s[0] == ">":
        return "quote"
    if s[0] == "|":
        return "table"
    if _HR_RE.match(line):
        return "hr"
    return "para"


def pad_blocks(text: str) -> str:
    """Ensure blank lines around tables, code blocks, lists, quotes, and hr.

    python-markdown requires preceding empty lines to reliably recognize block elements
    when they immediately follow paragraphs or captions.
    """
    lines = text.split("\n")
    out: list[str] = []
    prev: str | None = None
    i, n = 0, len(lines)

    def _ensure_blank_before():
        if out and out[-1].strip() != "":
            out.append("")

    while i < n:
        line = lines[i]

        # Table: header + separator + body rows
        if "|" in line and i + 1 < n and _TABLE_SEP_RE.match(lines[i + 1]):
            _ensure_blank_before()
            out.append(line)
            out.append(lines[i + 1])
            i += 2
            while i < n and lines[i].strip() and "|" in lines[i]:
                out.append(lines[i])
                i += 1
            prev = "table"
            if i < n and lines[i].strip() != "":
                out.append("")
            continue

        # Code fences
        fm = _FENCE_RE.match(line)
        if fm:
            marker = fm.group(1)[0]
            close_re = re.compile(r"^\s*" + re.escape(marker) + r"{3,}\s*$")
            _ensure_blank_before()
            out.append(line)
            i += 1
            while i < n:
                out.append(lines[i])
                closed = close_re.match(lines[i])
                i += 1
                if closed:
                    break
            prev = "fence"
            if i < n and lines[i].strip() != "":
                out.append("")
            continue

        t = _classify(line)
        if t == "blank":
            out.append(line)
            i += 1
            continue

        if prev is not None and (
            (t in ("list", "quote", "hr") and prev == "para")
            or (t == "para" and prev in ("list", "indent", "quote"))
        ):
            _ensure_blank_before()

        out.append(line)
        prev = t
        i += 1

    return "\n".join(out)


def extract_title(markdown_text: str, fallback: str = "Document") -> str:
    """Extract document title from the first level-1 heading (# Title), if present."""
    for line in markdown_text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def preprocess_markdown(text: str) -> str:
    """Apply standard clean-ups to markdown text before HTML conversion."""
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = _CITE_RE.sub("", text)
    text = normalize_list_indent(text)
    text = pad_blocks(text)
    return text.strip("\n") + "\n"
