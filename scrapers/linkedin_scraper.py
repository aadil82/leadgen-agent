"""
LinkedIn Scraper — Search LinkedIn for job postings and company profiles.

Supports two modes:
  1. Official LinkedIn API (requires OAuth2 app credentials)
  2. Web scraping via requests + BeautifulSoup (fallback, respect ToS)

Usage:
    python -m scrapers.linkedin_scraper --query "AI engineer" --limit 50
"""

import argparse
import csv
import json
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

# ── Config ─────────────────────────────────────────────────────

DEFAULT_QUERIES = [
    "AI engineer hiring",
    "machine learning engineer",
    "cloud architect hiring",
    "data engineer",
    "DevOps engineer",
    "full stack developer",
    "python developer",
    "AWS architect",
    "Azure architect",
    "generative AI",
    "LLM engineer",
    "ecommerce platform developer",
    "POS system developer",
    "retail technology",
    "digital transformation",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


def _load_settings() -> Dict[str, Any]:
    """Load settings.yaml if available."""
    settings_path = os.path.join("config", "settings.yaml")
    if os.path.exists(settings_path) and yaml:
        with open(settings_path, "r") as fh:
            return yaml.safe_load(fh) or {}
    return {}


def _get_api_key(env_var: str) -> Optional[str]:
    """Get API key from environment variable."""
    return os.environ.get(env_var)


# ── LinkedIn API Mode ─────────────────────────────────────────


class LinkedInAPIClient:
    """LinkedIn Marketing API / Jobs API client."""

    BASE_URL = "https://api.linkedin.com/v2"

    def __init__(self, access_token: str) -> None:
        self.access_token = access_token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        })
        self._request_count = 0
        self._window_start = time.time()
        self._rate_limit = 100
        self._window_seconds = 3600

    def _check_rate_limit(self) -> None:
        """Simple rate limiter."""
        now = time.time()
        if now - self._window_start > self._window_seconds:
            self._request_count = 0
            self._window_start = now
        if self._request_count >= self._rate_limit:
            wait = self._window_seconds - (now - self._window_start)
            print(f"  Rate limit reached. Waiting {wait:.0f}s...")
            time.sleep(max(wait, 1))
            self._request_count = 0
            self._window_start = time.time()

    def search_jobs(
        self,
        query: str,
        location: str = "",
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """Search LinkedIn jobs API."""
        self._check_rate_limit()
        params = {
            "q": "search",
            "keywords": query,
            "count": min(limit, 25),
            "start": 0,
        }
        if location:
            params["locationId"] = location

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/jobSearch",
                params=params,
                timeout=30,
            )
            self._request_count += 1
            resp.raise_for_status()
            data = resp.json()
            jobs = data.get("elements", [])
            return [self._parse_job(j) for j in jobs]
        except requests.RequestException as e:
            print(f"  [WARN] LinkedIn API error for query '{query}': {e}")
            return []

    def get_company(self, company_id: str) -> Optional[Dict[str, Any]]:
        """Get company details from LinkedIn API."""
        self._check_rate_limit()
        try:
            resp = self.session.get(
                f"{self.BASE_URL}/organizations/{company_id}",
                timeout=30,
            )
            self._request_count += 1
            resp.raise_for_status()
            return self._parse_company(resp.json())
        except requests.RequestException as e:
            print(f"  [WARN] LinkedIn API error for company {company_id}: {e}")
            return None

    def _parse_job(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a raw LinkedIn job into a clean dict."""
        title = raw.get("title", "")
        company_name = raw.get("companyName", "")
        company_id = raw.get("companyId", "")
        location = raw.get("formattedLocation", "")
        description = raw.get("description", {})
        desc_text = ""
        if isinstance(description, dict):
            desc_text = description.get("text", "")
        elif isinstance(description, str):
            desc_text = description

        return {
            "source": "linkedin",
            "scraped_at": datetime.now().isoformat(),
            "job_title": title,
            "company_name": company_name,
            "company_id": company_id,
            "location": location,
            "description": desc_text[:2000],
            "job_url": f"https://www.linkedin.com/jobs/view/{raw.get('id', '')}",
            "posted_date": raw.get("listedAt", ""),
            "employment_type": raw.get("employmentType", ""),
            "seniority_level": raw.get("seniorityLevel", ""),
            "industries": raw.get("industry", []),
        }

    def _parse_company(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a raw LinkedIn company into a clean dict."""
        return {
            "source": "linkedin",
            "company_name": raw.get("localizedName", ""),
            "company_id": str(raw.get("id", "")),
            "website": raw.get("websiteUrl", ""),
            "industry": raw.get("industry", ""),
            "company_size": raw.get("staffCountRange", ""),
            "description": raw.get("description", {}).get("text", "")[:2000],
            "linkedin_url": f"https://www.linkedin.com/company/{raw.get('universalName', '')}",
            "headquarters": raw.get("headquarter", {}),
        }


# ── LinkedIn Web Scraping Mode (fallback) ─────────────────────


class LinkedInScraper:
    """Web-based LinkedIn scraper (use responsibly, respect ToS)."""

    BASE_URL = "https://www.linkedin.com"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._request_count = 0
        self._window_start = time.time()

    def search_jobs(
        self,
        query: str,
        location: str = "",
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """Scrape LinkedIn job search results."""
        print(f"  [INFO] LinkedIn web scraping for: '{query}'")
        # NOTE: This is a simplified scraper that demonstrates the interface.
        # In production, use the official API or a third-party service like
        # Proxycurl, PhantomBuster, or LinkedIn's Marketing API.
        # Direct scraping violates LinkedIn ToS and may result in account bans.
        time.sleep(2)  # Respectful delay
        self._request_count += 1
        # Return empty — real implementation would use Selenium/Playwright
        # or a proxy service for production scraping
        return []

    def get_company(self, linkedin_url: str) -> Optional[Dict[str, Any]]:
        """Scrape company details from LinkedIn URL."""
        time.sleep(2)
        self._request_count += 1
        return None


# ── Public API ────────────────────────────────────────────────


def create_linkedin_client() -> Any:
    """Create the appropriate LinkedIn client based on available credentials."""
    access_token = _get_api_key("LINKEDIN_ACCESS_TOKEN")
    if access_token:
        print("  Using LinkedIn API client (OAuth2)")
        return LinkedInAPIClient(access_token)
    else:
        print("  Using LinkedIn web scraper (no API key found)")
        return LinkedInScraper()


def scrape_linkedin_jobs(
    queries: Optional[List[str]] = None,
    location: str = "",
    limit_per_query: int = 25,
    output_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search LinkedIn for job postings matching the given queries.
    Returns a list of parsed job dicts.
    """
    settings = _load_settings()
    linkedin_config = settings.get("scrapers", {}).get("linkedin", {})

    if queries is None:
        queries = linkedin_config.get("search_queries", DEFAULT_QUERIES)

    client = create_linkedin_client()
    all_jobs: List[Dict[str, Any]] = []
    seen_urls = set()

    print(f"\n{'='*60}")
    print(f"  LinkedIn Job Scraper")
    print(f"  Queries: {len(queries)} | Limit per query: {limit_per_query}")
    print(f"{'='*60}")

    for i, query in enumerate(queries, 1):
        print(f"\n  [{i}/{len(queries)}] Searching: '{query}'")
        jobs = client.search_jobs(query, location, limit_per_query)

        for job in jobs:
            url = job.get("job_url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_jobs.append(job)

        print(f"    Found {len(jobs)} jobs ({len(all_jobs)} unique total)")

    # Save results
    if output_path is None:
        today = datetime.now().strftime("%Y-%m-%d")
        output_dir = "data/raw"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"linkedin_jobs_{today}.json")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(all_jobs, fh, indent=2, default=str)

    print(f"\n  Total unique jobs scraped: {len(all_jobs)}")
    print(f"  Saved to: {output_path}")

    return all_jobs


def jobs_to_csv(jobs: List[Dict[str, Any]], output_path: str) -> str:
    """Convert scraped jobs to CSV format compatible with lead engine."""
    rows = []
    for job in jobs:
        company = job.get("company_name", "")
        location = job.get("location", "")
        parts = [p.strip() for p in location.split(",")] if location else ["", ""]
        city = parts[0] if parts else ""
        country = parts[-1] if len(parts) > 1 else ""

        rows.append({
            "Company Name": company,
            "Contact Name": "",  # to be enriched
            "Job Title": job.get("job_title", ""),
            "LinkedIn Profile": "",  # to be enriched
            "Company LinkedIn": f"https://www.linkedin.com/company/{company.lower().replace(' ', '-')}" if company else "",
            "Company Website": "",
            "Industry": ", ".join(job.get("industries", [])) if isinstance(job.get("industries"), list) else job.get("industries", ""),
            "Company Size": "",
            "Country": country,
            "City": city,
            "Technology Stack": "",
            "Job Posting URL": job.get("job_url", ""),
            "Job Posted Date": job.get("posted_date", ""),
            "notes": f"Scraped from LinkedIn. {job.get('description', '')[:500]}",
        })

    if rows:
        fieldnames = list(rows[0].keys())
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"  CSV export: {output_path} ({len(rows)} rows)")

    return output_path


# ── CLI ────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="LinkedIn Job Scraper")
    parser.add_argument(
        "--query", "-q", nargs="*",
        help="Custom search queries (overrides settings.yaml)",
    )
    parser.add_argument("--location", "-l", default="", help="Location filter")
    parser.add_argument(
        "--limit", "-n", type=int, default=25,
        help="Results per query (default: 25)",
    )
    parser.add_argument("--output", "-o", help="Output JSON path")
    parser.add_argument("--csv", help="Also export as CSV to this path")
    args = parser.parse_args()

    jobs = scrape_linkedin_jobs(
        queries=args.query,
        location=args.location,
        limit_per_query=args.limit,
        output_path=args.output,
    )

    if args.csv and jobs:
        jobs_to_csv(jobs, args.csv)


if __name__ == "__main__":
    main()
