#!/usr/bin/env python3
"""Daily Saudi public-web lead discovery.

The pipeline is intentionally read-only:
1. DDGS discovers fresh indexed pages and public X/LinkedIn post URLs.
2. Crawl4AI renders/extracts public pages with Playwright.
3. DDGS extraction is a fallback when browser extraction is unavailable.
4. Saudi keyword/location rules score and deduplicate leads.
5. Results are written to an Arabic-safe CSV plus a JSON evidence file.

No paid API, login bypass, CAPTCHA bypass, outbound messaging, or application
submission is performed by this module.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ddgs import DDGS

try:
    from crawl4ai import AsyncWebCrawler
except Exception:  # Crawl4AI can fail to import before browser setup is complete.
    AsyncWebCrawler = None  # type: ignore[assignment]


CORE_KEYWORDS = [
    "looking for",
    "need urgently",
    "seeking vendor",
    "renting office",
]

ARABIC_KEYWORDS = [
    "أبحث عن",
    "نبحث عن",
    "أحتاج بشكل عاجل",
    "احتاج بشكل عاجل",
    "مطلوب بشكل عاجل",
    "أبحث عن مورد",
    "نبحث عن مورد",
    "مطلوب مورد",
    "استئجار مكتب",
    "مكتب للإيجار",
    "أبحث عن مكتب للإيجار",
]

# Extra equivalents improve recall without changing the four requested intent lanes.
SEARCH_PHRASES = CORE_KEYWORDS + ARABIC_KEYWORDS + [
    "looking for vendor",
    "office for rent",
]

LOCATION_ALIASES: dict[str, list[str]] = {
    "Saudi Arabia": [
        "saudi arabia",
        "ksa",
        "saudi",
        "السعودية",
        "المملكة العربية السعودية",
    ],
    "Riyadh": ["riyadh", "الرياض"],
    "Jeddah": ["jeddah", "jedda", "جدة"],
    "Dammam": ["dammam", "الدمام"],
}

SOCIAL_HOSTS = ("x.com", "twitter.com", "linkedin.com")
TRACKING_QUERY_PREFIXES = ("utm_", "fbclid", "gclid", "mc_")


@dataclass
class Candidate:
    title: str
    url: str
    snippet: str
    query: str
    query_phrase: str
    source_hint: str


@dataclass
class Lead:
    name: str
    post_content: str
    date: str
    link: str
    source: str
    matched_keyword: str
    matched_location: str
    score: int
    discovered_at: str
    query: str


@dataclass
class Extraction:
    text: str
    date: str = ""
    extraction_method: str = "snippet"


def normalize_text(value: str) -> str:
    value = value or ""
    value = value.replace("\u200f", " ").replace("\u200e", " ")
    value = re.sub(r"[\t\r ]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def lower_text(value: str) -> str:
    return normalize_text(value).casefold()


def first_keyword(text: str) -> str:
    haystack = lower_text(text)
    for keyword in SEARCH_PHRASES:
        if keyword.casefold() in haystack:
            return keyword
    return ""


def first_location(text: str) -> str:
    haystack = lower_text(text)
    # Prefer cities over the country-wide match.
    for location in ("Riyadh", "Jeddah", "Dammam", "Saudi Arabia"):
        for alias in LOCATION_ALIASES[location]:
            if alias.casefold() in haystack:
                return location
    return ""


def location_query_group() -> str:
    return '("Saudi Arabia" OR السعودية OR Riyadh OR الرياض OR Jeddah OR جدة OR Dammam OR الدمام)'


def build_queries(phrases: Iterable[str] = SEARCH_PHRASES) -> list[tuple[str, str, str]]:
    """Return (query, phrase, source_hint) tuples.

    Each phrase gets a broad-web search plus focused X and LinkedIn searches.
    Search-engine indexing provides a useful fallback for social pages that refuse
    anonymous browser rendering.
    """
    locations = location_query_group()
    queries: list[tuple[str, str, str]] = []
    for phrase in phrases:
        quoted = f'"{phrase}"'
        queries.extend(
            [
                (f"{quoted} {locations}", phrase, "web"),
                (f"site:x.com {quoted} {locations}", phrase, "x"),
                (f"site:linkedin.com/posts {quoted} {locations}", phrase, "linkedin"),
            ]
        )
    return queries


def canonicalize_url(url: str) -> str:
    try:
        parts = urlsplit(url.strip())
    except Exception:
        return ""
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""

    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host == "twitter.com":
        host = "x.com"

    query_items = []
    if host not in SOCIAL_HOSTS and not host.endswith(".linkedin.com"):
        for key, value in parse_qsl(parts.query, keep_blank_values=False):
            key_lower = key.lower()
            if any(key_lower.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES):
                continue
            query_items.append((key, value))

    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), host, path, urlencode(query_items), ""))


def domain_for(url: str) -> str:
    try:
        return urlsplit(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def is_social(url: str) -> bool:
    host = domain_for(url)
    return host in SOCIAL_HOSTS or host.endswith(".linkedin.com")


def source_for(url: str) -> str:
    host = domain_for(url)
    if host in {"x.com", "twitter.com"}:
        return "X"
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        return "LinkedIn"
    return host or "Web"


def discover(max_per_query: int = 6, timelimit: str = "d") -> list[Candidate]:
    seen: set[str] = set()
    candidates: list[Candidate] = []
    ddgs = DDGS(timeout=12)

    for query, phrase, source_hint in build_queries():
        try:
            rows = ddgs.text(
                query,
                region="wt-wt",
                safesearch="moderate",
                timelimit=timelimit,
                max_results=max_per_query,
                backend="auto",
            )
        except Exception as exc:
            print(f"SEARCH_WARN source={source_hint} phrase={phrase!r} error={exc}", file=sys.stderr)
            continue

        for row in rows or []:
            url = canonicalize_url(str(row.get("href") or row.get("url") or ""))
            if not url or url in seen:
                continue
            seen.add(url)
            candidates.append(
                Candidate(
                    title=normalize_text(str(row.get("title") or "")),
                    url=url,
                    snippet=normalize_text(str(row.get("body") or row.get("snippet") or "")),
                    query=query,
                    query_phrase=phrase,
                    source_hint=source_hint,
                )
            )
    return candidates


def _markdown_to_text(markdown: Any) -> str:
    if markdown is None:
        return ""
    if isinstance(markdown, str):
        return normalize_text(markdown)
    for attr in ("raw_markdown", "fit_markdown", "markdown_with_citations"):
        value = getattr(markdown, attr, None)
        if isinstance(value, str) and value.strip():
            return normalize_text(value)
    return normalize_text(str(markdown))


def _metadata_date(metadata: Any) -> str:
    if not isinstance(metadata, dict):
        return ""
    for key in (
        "published_time",
        "article:published_time",
        "datePublished",
        "date",
        "published",
        "created_at",
    ):
        value = metadata.get(key)
        if value:
            return normalize_text(str(value))[:100]
    return ""


async def crawl_one(crawler: Any, candidate: Candidate, timeout_seconds: int = 25) -> Extraction:
    if crawler is None:
        return Extraction(text="", extraction_method="crawl4ai-unavailable")
    try:
        result = await asyncio.wait_for(crawler.arun(url=candidate.url), timeout=timeout_seconds)
        success = bool(getattr(result, "success", False))
        if not success:
            return Extraction(text="", extraction_method="crawl4ai-failed")
        text = _markdown_to_text(getattr(result, "markdown", ""))
        date = _metadata_date(getattr(result, "metadata", {}))
        return Extraction(text=text, date=date, extraction_method="crawl4ai")
    except Exception as exc:
        print(f"CRAWL_WARN url={candidate.url} error={exc}", file=sys.stderr)
        return Extraction(text="", extraction_method="crawl4ai-error")


async def ddgs_extract_one(candidate: Candidate, timeout_seconds: int = 15) -> Extraction:
    def _extract() -> Extraction:
        try:
            result = DDGS(timeout=timeout_seconds).extract(candidate.url, fmt="text_plain")
            if isinstance(result, dict):
                return Extraction(
                    text=normalize_text(str(result.get("content") or "")),
                    extraction_method="ddgs-extract",
                )
        except Exception as exc:
            print(f"EXTRACT_WARN url={candidate.url} error={exc}", file=sys.stderr)
        return Extraction(text="", extraction_method="snippet")

    return await asyncio.to_thread(_extract)


def candidate_priority(candidate: Candidate) -> tuple[int, int]:
    combined = f"{candidate.title}\n{candidate.snippet}"
    score = 0
    if first_keyword(combined):
        score += 4
    if first_location(combined):
        score += 4
    if candidate.source_hint in {"x", "linkedin"} or is_social(candidate.url):
        score += 2
    return (-score, len(candidate.url))


async def enrich_candidates(candidates: list[Candidate], max_crawl_urls: int) -> dict[str, Extraction]:
    ordered = sorted(candidates, key=candidate_priority)
    selected = ordered[:max_crawl_urls]
    output: dict[str, Extraction] = {}

    crawler: Any = None
    if AsyncWebCrawler is not None:
        try:
            crawler = AsyncWebCrawler()
            await crawler.start()
        except Exception as exc:
            print(f"CRAWLER_START_WARN error={exc}", file=sys.stderr)
            crawler = None

    try:
        # Keep browser work paced and predictable. This also avoids hammering sites.
        for candidate in selected:
            extraction = await crawl_one(crawler, candidate)
            if not extraction.text:
                extraction = await ddgs_extract_one(candidate)
            output[candidate.url] = extraction
    finally:
        if crawler is not None:
            try:
                await crawler.close()
            except Exception:
                pass

    return output


def relevant_excerpt(candidate: Candidate, extracted_text: str, max_chars: int = 1400) -> str:
    snippet = normalize_text(candidate.snippet)
    extracted = normalize_text(extracted_text)

    # Search snippets are usually the cleanest representation of a social post.
    if snippet and first_keyword(snippet) and first_location(snippet):
        return snippet[:max_chars]

    combined = extracted or snippet or candidate.title
    if not combined:
        return ""

    folded = combined.casefold()
    positions = []
    for keyword in SEARCH_PHRASES:
        pos = folded.find(keyword.casefold())
        if pos >= 0:
            positions.append(pos)
    anchor = min(positions) if positions else 0
    start = max(0, anchor - 280)
    end = min(len(combined), anchor + max_chars - 280)
    excerpt = combined[start:end]
    excerpt = re.sub(r"[#>*_`]+", " ", excerpt)
    excerpt = re.sub(r"\s+", " ", excerpt).strip()
    return excerpt[:max_chars]


def score_lead(candidate: Candidate, extraction: Extraction) -> tuple[int, str, str, str]:
    excerpt = relevant_excerpt(candidate, extraction.text)
    evidence = "\n".join([candidate.title, candidate.snippet, excerpt])
    keyword = first_keyword(evidence) or candidate.query_phrase
    location = first_location(evidence)

    score = 0
    if first_keyword(evidence):
        score += 4
    elif candidate.query_phrase:
        score += 1
    if location:
        score += 4
    if is_social(candidate.url):
        score += 2
    if extraction.extraction_method in {"crawl4ai", "ddgs-extract"} and extraction.text:
        score += 1

    # Location is mandatory. Search engines can return false positives even when
    # the location term is present only in query syntax.
    if not location:
        score = 0
    return score, keyword, location, excerpt


def derive_name(candidate: Candidate) -> str:
    title = normalize_text(candidate.title)
    source = source_for(candidate.url)
    if not title:
        return source

    if source == "X":
        for marker in (" on X:", " on Twitter:"):
            if marker in title:
                return title.split(marker, 1)[0].strip()[:160]
        if ":" in title:
            prefix = title.split(":", 1)[0].strip()
            if 1 < len(prefix) < 160:
                return prefix

    if source == "LinkedIn":
        cleaned = re.sub(r"\s*[|·-]\s*LinkedIn\s*$", "", title, flags=re.I).strip()
        if cleaned:
            return cleaned[:160]

    return title[:160]


def build_leads(
    candidates: list[Candidate],
    extractions: dict[str, Extraction],
    minimum_score: int = 6,
) -> list[Lead]:
    discovered_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    leads: list[Lead] = []
    content_seen: set[str] = set()

    for candidate in candidates:
        extraction = extractions.get(candidate.url, Extraction(text=""))
        score, keyword, location, excerpt = score_lead(candidate, extraction)
        if score < minimum_score or not excerpt:
            continue

        fingerprint = hashlib.sha256(lower_text(excerpt).encode("utf-8")).hexdigest()[:24]
        if fingerprint in content_seen:
            continue
        content_seen.add(fingerprint)

        leads.append(
            Lead(
                name=derive_name(candidate),
                post_content=excerpt,
                date=extraction.date,
                link=candidate.url,
                source=source_for(candidate.url),
                matched_keyword=keyword,
                matched_location=location,
                score=score,
                discovered_at=discovered_at,
                query=candidate.query,
            )
        )

    leads.sort(key=lambda item: (-item.score, item.source, item.matched_location, item.name.casefold()))
    return leads


def write_outputs(leads: list[Lead], output_csv: Path, output_json: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)

    # Keep the user-requested CSV contract exact.
    with output_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Name", "Post Content", "Date", "Link"])
        writer.writeheader()
        for lead in leads:
            writer.writerow(
                {
                    "Name": lead.name,
                    "Post Content": lead.post_content,
                    "Date": lead.date,
                    "Link": lead.link,
                }
            )

    evidence = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lead_count": len(leads),
        "leads": [asdict(lead) for lead in leads],
    }
    output_json.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover Saudi public-web buying-intent leads")
    parser.add_argument("--output", default="lead_results/latest.csv")
    parser.add_argument("--json-output", default="lead_results/latest.json")
    parser.add_argument("--max-results", type=int, default=120)
    parser.add_argument("--max-per-query", type=int, default=6)
    parser.add_argument("--max-crawl-urls", type=int, default=50)
    parser.add_argument("--minimum-score", type=int, default=6)
    parser.add_argument("--timelimit", choices=["d", "w", "m"], default="d")
    parser.add_argument("--discovery-only", action="store_true")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    candidates = discover(max_per_query=max(1, args.max_per_query), timelimit=args.timelimit)
    print(f"DISCOVERED candidates={len(candidates)}")

    if args.discovery_only:
        extractions: dict[str, Extraction] = {}
    else:
        extractions = await enrich_candidates(candidates, max_crawl_urls=max(0, args.max_crawl_urls))

    leads = build_leads(candidates, extractions, minimum_score=max(1, args.minimum_score))
    leads = leads[: max(0, args.max_results)]

    output_csv = Path(args.output)
    output_json = Path(args.json_output)
    write_outputs(leads, output_csv, output_json)

    by_source: dict[str, int] = {}
    by_location: dict[str, int] = {}
    for lead in leads:
        by_source[lead.source] = by_source.get(lead.source, 0) + 1
        by_location[lead.matched_location] = by_location.get(lead.matched_location, 0) + 1

    print(f"LEADS count={len(leads)}")
    print("SOURCES " + json.dumps(by_source, ensure_ascii=False, sort_keys=True))
    print("LOCATIONS " + json.dumps(by_location, ensure_ascii=False, sort_keys=True))
    print(f"CSV {output_csv}")
    print(f"JSON {output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
