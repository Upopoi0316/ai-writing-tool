"""Markdown の記号を取り除き、メールや SNS にそのまま貼れるテキストにする。"""

from __future__ import annotations

import re

_FENCE = re.compile(r"^\s*(```|~~~)")
_RULE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
# 「#」の直後に空白を求めるので、SNS のハッシュタグ(#在宅勤務)は見出しとして扱わない
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)(\s+#+)?\s*$")
_QUOTE = re.compile(r"^(\s{0,3}>\s?)+")
_BULLET = re.compile(r"^(\s*)[*+]\s+")
_CODE_SPAN = re.compile(r"(`[^`\n]+`)")
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)[^)]*\)")
# Markdown の仕様に合わせ、語の途中の「_」は強調にしない(日本語も語の一部として扱う)。「*」は語の途中でも強調になる
_EMPHASIS = (
    re.compile(r"(?<!\\)\*\*(?=\S)(.+?)(?<=\S)\*\*"),
    re.compile(r"(?<![\\\w])__(?=\S)(.+?)(?<=\S)__(?!\w)"),
    re.compile(r"(?<![\\*])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?!\*)"),
    re.compile(r"(?<![\\\w])_(?=\S)(.+?)(?<=\S)_(?!\w)"),
    re.compile(r"(?<!\\)~~(?=\S)(.+?)(?<=\S)~~"),
)
_ESCAPE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!>~|])")


def _link_text(match: re.Match[str]) -> str:
    # リンク先が消えると情報が失われるので、文字列として残す
    text, url = match.group(1), match.group(2)
    return text if text == url else f"{text} ({url})"


def _strip_inline(text: str) -> str:
    # `...` の中は記号も内容の一部なので変換しない
    parts = _CODE_SPAN.split(text)
    for index, part in enumerate(parts):
        if index % 2:
            parts[index] = part[1:-1]
            continue
        part = _IMAGE.sub(r"\1", part)
        part = _LINK.sub(_link_text, part)
        for pattern in _EMPHASIS:
            part = pattern.sub(r"\1", part)
        parts[index] = _ESCAPE.sub(r"\1", part)
    return "".join(parts)


def to_plain_text(markdown: str) -> str:
    lines: list[str] = []
    in_code_block = False
    for line in markdown.splitlines():
        if _FENCE.match(line):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            lines.append(line)
            continue
        if _RULE.match(line):
            lines.append("")
            continue
        line = _QUOTE.sub("", line)
        line = _HEADING.sub(r"\1", line)
        line = _BULLET.sub(r"\1- ", line)
        lines.append(_strip_inline(line).rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
