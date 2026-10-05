from __future__ import annotations

import re
from collections.abc import Sequence
from functools import lru_cache

from intern_radar.config import FilterConfig
from intern_radar.models import Posting


@lru_cache(maxsize=256)
def _keyword_re(keyword: str) -> re.Pattern[str]:
    """
    Match a keyword as a whole word while tolerating plural and
    -ship endings.

    The boundary is on letters rather than \\b so that titles such as
    EHS Intern_Shenzhen are not accidentally rejected.
    """
    return re.compile(
        r"(?<![a-z])"
        + re.escape(keyword)
        + r"(?:s|ship|ships)?"
        + r"(?![a-z])",
        re.IGNORECASE,
    )


def _matches_keyword(
    text: str,
    keywords: Sequence[str],
) -> bool:
    return any(
        _keyword_re(k).search(text)
        for k in keywords
        if k
    )


def _matches_allowlist(
    values: Sequence[str],
    allowlist: Sequence[str],
) -> bool:
    """
    Return True when at least one value matches at least one
    allowlist entry.

    Matching is case-insensitive substring matching.
    """
    if not allowlist:
        return True

    if not values:
        return False

    normalized_allowlist = [
        item.lower()
        for item in allowlist
        if item
    ]

    return any(
        any(
            allowed in value.lower()
            for allowed in normalized_allowlist
        )
        for value in values
    )


def matches(
    posting: Posting,
    filters: FilterConfig,
) -> bool:
    title_lower = posting.title.lower()
    company_lower = posting.company.lower()

    # ---------------------------------------------------------
    # 1. COMPANY ALLOWLIST
    # ---------------------------------------------------------
    # If configured, ONLY companies in the allowlist are accepted.
    if filters.company_allowlist:
        if not any(
            allowed.lower() in company_lower
            for allowed in filters.company_allowlist
            if allowed
        ):
            return False

    # ---------------------------------------------------------
    # 2. COMPANY EXCLUSION
    # ---------------------------------------------------------
    if any(
        kw.lower() in company_lower
        for kw in filters.company_exclude
    ):
        return False

    # ---------------------------------------------------------
    # 3. TITLE EXCLUSION
    # ---------------------------------------------------------
    if any(
        kw.lower() in title_lower
        for kw in filters.title_exclude
    ):
        return False

    # ---------------------------------------------------------
    # 4. LOCATION ALLOWLIST
    # ---------------------------------------------------------
    # If locations are available, at least one must be allowed.
    #
    # This intentionally permits multi-location postings such as:
    # "Bengaluru / Hyderabad / Remote - India"
    #
    # A posting with no location metadata is NOT rejected here.
    # This avoids accidentally losing otherwise valid ATS postings.
    if filters.location_allowlist and posting.locations:
        if not _matches_allowlist(
            posting.locations,
            filters.location_allowlist,
        ):
            return False

    # ---------------------------------------------------------
    # 5. LOCATION EXCLUSION
    # ---------------------------------------------------------
    if filters.location_exclude and posting.locations:

        def excluded(loc: str) -> bool:
            loc_lower = loc.lower()

            return any(
                kw.lower() in loc_lower
                for kw in filters.location_exclude
            )

        # A multi-location posting with at least one acceptable
        # location remains valid.
        if all(
            excluded(loc)
            for loc in posting.locations
        ):
            return False

    # ---------------------------------------------------------
    # 6. TERM / CATEGORY / DEGREE FILTERS
    # ---------------------------------------------------------
    if posting.terms:
        # Aggregator listing with term metadata.
        if (
            filters.terms
            and not set(posting.terms)
            & set(filters.terms)
        ):
            return False

        if (
            filters.categories
            and posting.category
            and posting.category not in filters.categories
        ):
            return False

        if (
            filters.degrees_any
            and posting.degrees
            and not (
                set(posting.degrees)
                & set(filters.degrees_any)
            )
        ):
            return False

        return True

    # ---------------------------------------------------------
    # 7. DIRECT ATS TITLE EXCLUSIONS
    # ---------------------------------------------------------
    if any(
        kw.lower() in title_lower
        for kw in filters.untermed_title_exclude
    ):
        return False

    # ---------------------------------------------------------
    # 8. INTERNSHIP GATE
    # ---------------------------------------------------------
    # The source's employment type takes priority.
    if _keyword_re("intern").search(
        posting.employment_type
    ):
        return True

    return (
        not filters.title_require_any
        or _matches_keyword(
            posting.title,
            filters.title_require_any,
        )
    )


def apply_filters(
    postings: list[Posting],
    filters: FilterConfig,
) -> list[Posting]:
    return [
        posting
        for posting in postings
        if matches(posting, filters)
    ]


def passes_discovered_gate(
    posting: Posting,
    filters: FilterConfig,
) -> bool:
    """
    Additional technology-role gate for postings from
    auto-discovered/unpinned boards.
    """
    title_lower = posting.title.lower()

    if any(
        kw.lower() in title_lower
        for kw in filters.discovered_title_exclude
    ):
        return False

    return (
        not filters.discovered_title_require_any
        or _matches_keyword(
            posting.title,
            filters.discovered_title_require_any,
        )
    )
