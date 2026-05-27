"""Boyer-Moore exact string search with paper-oriented instrumentation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class SearchResult:
    matches: List[int]
    comparisons: int
    alignments: int


@dataclass(frozen=True)
class FirstSearchResult:
    match: Optional[int]
    comparisons: int
    alignments: int
    characters_passed: int


@dataclass(frozen=True)
class BoyerMooreTables:
    bad_character: Dict[str, int]
    good_suffix: List[int]


def build_bad_character_table(pattern: str) -> Dict[str, int]:
    """Return rightmost occurrence positions for the bad-character rule."""
    return {ch: idx for idx, ch in enumerate(pattern)}


def build_good_suffix_shift(pattern: str) -> List[int]:
    """Build the strong good-suffix shift table.

    The paper defines delta2 through the rightmost plausible reoccurrence of a
    terminal substring. This is the standard strong good-suffix preprocessing
    used by later Boyer-Moore implementations for the same shift rule.
    """
    m = len(pattern)
    shift = [0] * (m + 1)
    border = [0] * (m + 1)
    i = m
    j = m + 1
    border[i] = j

    while i > 0:
        while j <= m and pattern[i - 1] != pattern[j - 1]:
            if shift[j] == 0:
                shift[j] = j - i
            j = border[j]
        i -= 1
        j -= 1
        border[i] = j

    j = border[0]
    for i in range(m + 1):
        if shift[i] == 0:
            shift[i] = j
        if i == j:
            j = border[j]
    return shift


def build_tables(pattern: str) -> BoyerMooreTables:
    return BoyerMooreTables(
        bad_character=build_bad_character_table(pattern),
        good_suffix=build_good_suffix_shift(pattern),
    )


def boyer_moore_search(text: str, pattern: str) -> SearchResult:
    """Find all exact matches with right-to-left comparisons and both shifts.

    ASSUMPTION: the 1977 paper specifies the first-occurrence algorithm using
    one-based indexing. For reproducible Python evaluation this wrapper returns
    all overlapping zero-based matches, repeatedly applying the same skip rules.
    [see ambiguity_audit.md]
    """
    if pattern == "":
        return SearchResult(list(range(len(text) + 1)), 0, 0)

    n = len(text)
    m = len(pattern)
    if m > n:
        return SearchResult([], 0, 0)

    tables = build_tables(pattern)
    matches: List[int] = []
    comparisons = 0
    alignments = 0
    s = 0

    while s <= n - m:
        alignments += 1
        j = m - 1
        while j >= 0:
            comparisons += 1
            if pattern[j] != text[s + j]:
                break
            j -= 1

        if j < 0:
            matches.append(s)
            s += tables.good_suffix[0]
        else:
            mismatched = text[s + j]
            bad_shift = j - tables.bad_character.get(mismatched, -1)
            good_shift = tables.good_suffix[j + 1]
            s += max(1, bad_shift, good_shift)

    return SearchResult(matches, comparisons, alignments)


def boyer_moore_first(text: str, pattern: str) -> FirstSearchResult:
    """Return the first match with counts matching the paper's search target."""
    if pattern == "":
        return FirstSearchResult(0, 0, 0, 0)

    n = len(text)
    m = len(pattern)
    if m > n:
        return FirstSearchResult(None, 0, 0, n)

    tables = build_tables(pattern)
    comparisons = 0
    alignments = 0
    s = 0

    while s <= n - m:
        alignments += 1
        j = m - 1
        while j >= 0:
            comparisons += 1
            if pattern[j] != text[s + j]:
                break
            j -= 1

        if j < 0:
            return FirstSearchResult(s, comparisons, alignments, s + m)

        mismatched = text[s + j]
        bad_shift = j - tables.bad_character.get(mismatched, -1)
        good_shift = tables.good_suffix[j + 1]
        s += max(1, bad_shift, good_shift)

    return FirstSearchResult(None, comparisons, alignments, n)


def naive_search(text: str, pattern: str) -> SearchResult:
    if pattern == "":
        return SearchResult(list(range(len(text) + 1)), 0, 0)

    matches: List[int] = []
    comparisons = 0
    alignments = 0
    for i in range(0, len(text) - len(pattern) + 1):
        alignments += 1
        matched = True
        for j, ch in enumerate(pattern):
            comparisons += 1
            if text[i + j] != ch:
                matched = False
                break
        if matched:
            matches.append(i)
    return SearchResult(matches, comparisons, alignments)


def reference_find_all(text: str, pattern: str) -> List[int]:
    if pattern == "":
        return list(range(len(text) + 1))
    out: List[int] = []
    start = 0
    while True:
        idx = text.find(pattern, start)
        if idx == -1:
            return out
        out.append(idx)
        start = idx + 1
