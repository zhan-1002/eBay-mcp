"""Deterministic mechanical validation for English eBay title candidates."""

from __future__ import annotations

import re
from typing import Iterable


_WORD_RE = re.compile(r"[a-z0-9&.-]+", re.IGNORECASE)
_UNSUPPORTED_PUNCTUATION_RE = re.compile(r"[^A-Za-z0-9\s&.-]")


def validate_titles(
    titles: Iterable[str],
    *,
    forbidden_terms: Iterable[str] = (),
    expected_count: int = 30,
    max_length: int = 80,
    recommended_min_length: int = 70,
) -> dict:
    expected_count = max(1, min(int(expected_count), 200))
    max_length = max(1, min(int(max_length), 200))
    recommended_min_length = max(
        0, min(int(recommended_min_length), max_length)
    )
    values = list(titles or [])
    forbidden = _normalize_forbidden(forbidden_terms)
    seen: set[str] = set()
    rows = []
    valid_titles = []

    for index, raw in enumerate(values, start=1):
        title = _normalize_title(raw)
        issues: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []
        if not title:
            issues.append({"code": "EMPTY_TITLE", "message": "Title is empty."})
        if title and len(title) > max_length:
            issues.append(
                {
                    "code": "TITLE_TOO_LONG",
                    "message": f"Title has {len(title)} characters; maximum is {max_length}.",
                }
            )
        if title and _UNSUPPORTED_PUNCTUATION_RE.search(title):
            issues.append(
                {
                    "code": "UNSUPPORTED_PUNCTUATION",
                    "message": "Only spaces, &, hyphen and period are allowed as separators.",
                }
            )
        if title and any(ord(char) > 127 for char in title):
            issues.append(
                {
                    "code": "NON_ASCII_TITLE",
                    "message": "The English-title workflow requires ASCII title text.",
                }
            )

        words = _WORD_RE.findall(title.casefold())
        duplicates = sorted({word for word in words if words.count(word) > 1})
        if duplicates:
            issues.append(
                {
                    "code": "REPEATED_WORD",
                    "message": "Repeated words: " + ", ".join(duplicates),
                }
            )

        key = title.casefold()
        if key and key in seen:
            issues.append(
                {
                    "code": "DUPLICATE_TITLE",
                    "message": "This title duplicates an earlier title.",
                }
            )
        if key:
            seen.add(key)

        matched_forbidden = [
            term for term, pattern in forbidden if title and pattern.search(title)
        ]
        if matched_forbidden:
            issues.append(
                {
                    "code": "FORBIDDEN_TERM",
                    "message": "Forbidden terms: " + ", ".join(matched_forbidden),
                }
            )
        if title and len(title) < recommended_min_length:
            warnings.append(
                {
                    "code": "SHORT_TITLE",
                    "message": (
                        f"Title has {len(title)} characters; "
                        f"{recommended_min_length}-{max_length} is preferred."
                    ),
                }
            )

        valid = not issues
        if valid:
            valid_titles.append(title)
        rows.append(
            {
                "index": index,
                "title": title,
                "character_count": len(title),
                "valid": valid,
                "issues": issues,
                "warnings": warnings,
            }
        )

    count_ok = len(values) == expected_count
    global_issues = []
    if not count_ok:
        global_issues.append(
            {
                "code": "TITLE_COUNT_MISMATCH",
                "message": (
                    f"Received {len(values)} titles; expected exactly {expected_count}."
                ),
            }
        )
    return {
        "valid_for_delivery": count_ok and len(valid_titles) == expected_count,
        "expected_count": expected_count,
        "received_count": len(values),
        "valid_count": len(valid_titles),
        "invalid_count": len(values) - len(valid_titles),
        "global_issues": global_issues,
        "titles": rows,
    }


def _normalize_title(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_forbidden(terms: Iterable[str]):
    normalized = []
    seen = set()
    for raw in terms or ():
        term = _normalize_title(raw).casefold()
        if not term or term in seen:
            continue
        seen.add(term)
        escaped = re.escape(term).replace(r"\ ", r"\s+")
        pattern = re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", re.IGNORECASE)
        normalized.append((term, pattern))
    return normalized

