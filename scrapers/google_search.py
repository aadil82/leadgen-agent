"""
Google Search Connector — Find company websites, press releases,
and hiring pages via Google Custom Search API.

Usage:
    python -m scrapers.google_search --query "AI engineer hiring" --limit 50
"""

import argparse
import json
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

# ── Config ─────────────────────────────────────────────────────

DEFAULT_QUERIES = [
    "site:linkedin.com/jobs AI engineer",
    "site:linkedin.com/jobs machine learning",
    "site:linkedin.com/jobs cloud architect",
    "site:linkedin.com/jobs data engineer",
    "hiring AI ML engineer company",
    "ecommerce platform hiring developers",
    "retail POS system implementation",
    "digital transformation hiring",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def _load_settings() -> Dict[str, Any]:
    settings_path = os.path.join("config", "settings.yaml")
    if os.path.exists(settings_path) and yaml:
        with open(settings_path, "r") as fh:
            return yaml.safe_load(fh) or {}
    return {}


# ── Google Custom Search API ───────────────────────────────────


class GoogleSearchClient:
    """Google Custom Search JSON API client."""

    BASE_URL = "https://www.googleapis.com/customsearch/v1"

    def __init__(self, api_key: str, search_engine_id: str) -> None:
        self.api_key = api_key
        self.cx = search_engine_id
        self.session = requests.Session()
        self._request_count = 0
        self._window_start = time.time()
        self._rate_limit = 100
        self._window_seconds = 86400  # daily limit

    def _check_rate_limit(self) -> None:
        now = time.time()
        if now - self._window_start > self._window_seconds:
            self._request_count = 0
            self._window_start = now
        if self._request_count >= self._rate_limit:
            print("  [WARN] Google API daily rate limit reached.")
            raise RuntimeError("Google API rate limit exceeded")

    def search(
        self,
        query: str,
        num_results: int = 10,
        start_index: int = 1,
        date_restrict: str = "",
        site_search: str = "",
    ) -> Dict[str, Any]:
        """Execute a Google Custom Search query."""
        self._check_rate_limit()

        params = {
            "key": self.api_key,
            "cx": self.cx,
            "q": query,
            "num": min(num_results, 10),
            "start": start_index,
        }
        if date_restrict:
            params["dateRestrict"] = date_restrict
        if site_search:
            params["siteSearch"] = site_search

        try:
            resp = self.session.get(self.BASE_URL, params=params, timeout=30)
            self._request_count += 1
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            print(f"  [WARN] Google API error: {e}")
            return {}

    def search_all(
        self,
        query: str,
        max_results: int = 30,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Search with pagination to get more than 10 results."""
        all_items: List[Dict[str, Any]] = []
        for start in range(1, max_results + 1, 10):
            data = self.search(query, num_results=10, start_index=start, **kwargs)
            items = data.get("items", [])
            if not items:
                break
            all_items.extend(items)
            time.sleep(0.5)  # respectful delay
        return all_items


# ── Result Parser ──────────────────────────────────────────────


def parse_search_result(item: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a Google search result into a structured lead dict."""
    title = item.get("title", "")
    snippet = item.get("snippet", "")
    link = item.get("link", "")
    display_link = item.get("displayLink", "")
    page_map = item.get("pagemap", {})

    # Extract company name from title or domain
    company_name = _extract_company_name(title, display_link)

    # Extract location hints from snippet
    location = _extract_location(snippet)

    # Detect if this is a job posting
    is_job = _is_job_posting(title, snippet, link)

    # Detect technologies mentioned
    tech_keywords = [
        "Python", "Java", "C#", ".NET", "Node.js", "TypeScript", "Go", "Rust",
        "AWS", "Azure", "GCP", "Kubernetes", "Docker", "Terraform",
        "AI", "Machine Learning", "ML", "GenAI", "LLM", "OpenAI",
        "React", "Angular", "Vue.js", "Django", "FastAPI", "Spring Boot",
        "PostgreSQL", "MySQL", "MongoDB", "Snowflake", "Databricks",
        "Salesforce", "SAP", "E-Commerce", "POS", "Shopify",
    ]
    combined_text = f"{title} {snippet}".lower()
    detected_techs = [t for t in tech_keywords if t.lower() in combined_text]

    return {
        "source": "google",
        "scraped_at": datetime.now().isoformat(),
        "company_name": company_name,
        "website": f"https://{display_link}" if display_link else link,
        "linkedin_url": _extract_linkedin_url(snippet + " " + title),
        "job_title": title if is_job else "",
        "job_url": link if is_job else "",
        "is_job_posting": is_job,
        "snippet": snippet,
        "detected_technologies": detected_techs,
        "location": location,
        "page_map": {k: v for k, v in page_map.items() if k in ("cse_thumbnail", "metatags")},
    }


def _extract_company_name(title: str, domain: str) -> str:
    """Try to extract a company name from the search result title."""
    # Common patterns: "Company Name - Job Title | LinkedIn"
    # or "Job Title at Company Name"
    patterns = [
        r"^(.+?)\s*[-–|]\s*(?:Job|Hiring|Career|Engineer|Developer|Architect)",
        r"(?:at|@)\s+(.+?)(?:\s*[-–|]|$)",
        r"^(.+?)\s*[-–]\s*",
    ]
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            if len(name) > 3 and name.lower() not in ("www", "http", "https"):
                return name

    # Fallback: use domain name
    if domain:
        parts = domain.replace("www.", "").split(".")
        if parts:
            return parts[0].capitalize()
    return ""


def _extract_location(text: str) -> str:
    """Try to extract a location from the text."""
    location_patterns = [
        r"(?:in|at|from)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s*[A-Z]{2,})",
        r"([A-Z][a-z]+,\s*(?:United States|USA|UK|Canada|Germany|India|Australia))",
        r"(?:Remote|Hybrid|On-site)",
    ]
    for pattern in location_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return ""


def _is_job_posting(title: str, snippet: str, link: str) -> bool:
    """Determine if the result is likely a job posting."""
    combined = f"{title} {snippet} {link}".lower()
    job_signals = [
        "hiring", "job", "career", "position", "opening", "apply",
        "indeed.com", "glassdoor.com", "linkedin.com/jobs", "monster.com",
        "salary", "benefits", "full-time", "part-time", "contract",
    ]
    return any(signal in combined for signal in job_signals)


def _extract_linkedin_url(text: str) -> str:
    """Extract LinkedIn company URL from text."""
    match = re.search(
        r"https?://(?:www\.)?linkedin\.com/company/[a-zA-Z0-9_-]+",
        text,
    )
    return match.group(0) if match else ""


# ── Public API ────────────────────────────────────────────────


def create_google_client() -> Optional[GoogleSearchClient]:
    """Create a Google Search client if credentials are available."""
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    cx_id = os.environ.get("GOOGLE_CSE_ID", "")
    if api_key and cx_id:
        print("  Using Google Custom Search API")
        return GoogleSearchClient(api_key, cx_id)
    print("  [WARN] Google API credentials not found. Set GOOGLE_API_KEY and GOOGLE_CSE_ID.")
    return None


def scrape_google(
    queries: Optional[List[str]] = None,
    max_results_per_query: int = 20,
    output_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search Google for leads and job postings.
    Returns a list of parsed result dicts.
    """
    settings = _load_settings()
    google_config = settings.get("scrapers", {}).get("google", {})

    if queries is None:
        queries = google_config.get("queries", DEFAULT_QUERIES)

    client = create_google_client()
    if client is None:
        return []

    all_results: List[Dict[str, Any]] = []
    seen_urls: set = set()

    print(f"\n{'='*60}")
    print(f"  Google Search Connector")
    print(f"  Queries: {len(queries)} | Max per query: {max_results_per_query}")
    print(f"{'='*60}")

    for i, query in enumerate(queries, 1):
        print(f"\n  [{i}/{len(queries)}] Searching: '{query}'")
        try:
            raw_items = client.search_all(query, max_results=max_results_per_query)
        except RuntimeError:
            print("  Rate limit hit. Stopping.")
            break

        for item in raw_items:
            parsed = parse_search_result(item)
            url = parsed.get("website", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(parsed)

        print(f"    Found {len(raw_items)} results ({len(all_results)} unique total)")
        time.sleep(1)  # respectful delay between queries

    # Save results
    if output_path is None:
        today = datetime.now().strftime("%Y-%m-%d")
        output_dir = "data/raw"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"google_results_{today}.json")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(all_results, fh, indent=2, default=str)

    print(f"\n  Total unique results: {len(all_results)}")
    print(f"  Saved to: {output_path}")

    return all_results


# ── CLI ────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Google Search Lead Connector")
    parser.add_argument("--query", "-q", nargs="*", help="Custom search queries")
    parser.add_argument("--limit", "-n", type=int, default=20, help="Max results per query")
    parser.add_argument("--output", "-o", help="Output JSON path")
    args = parser.parse_args()

    scrape_google(
        queries=args.query,
        max_results_per_query=args.limit,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
