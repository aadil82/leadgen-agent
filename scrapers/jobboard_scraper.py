"""
Job Board Scraper — Search Indeed, Glassdoor, and Monster for job postings.

Usage:
    python -m scrapers.jobboard_scraper --query "AI engineer" --limit 50
"""

import argparse
import json
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _load_settings() -> Dict[str, Any]:
    settings_path = os.path.join("config", "settings.yaml")
    if os.path.exists(settings_path) and yaml:
        with open(settings_path, "r") as fh:
            return yaml.safe_load(fh) or {}
    return {}


# ── Indeed Scraper ─────────────────────────────────────────────


class IndeedScraper:
    """Search Indeed for job postings."""

    BASE_URL = "https://www.indeed.com"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._request_count = 0

    def search(
        self,
        query: str,
        location: str = "",
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """Search Indeed for jobs."""
        self._request_count += 1
        time.sleep(2)  # respectful delay

        params = {
            "q": query,
            "l": location,
            "start": 0,
            "sort": "date",
        }
        url = f"{self.BASE_URL}/jobs?{urlencode(params)}"

        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return self._parse_search_page(resp.text, url)
        except requests.RequestException as e:
            print(f"    [WARN] Indeed error for '{query}': {e}")
            return []

    def _parse_search_page(self, html: str, search_url: str) -> List[Dict[str, Any]]:
        """Parse Indeed search results page."""
        jobs: List[Dict[str, Any]] = []

        # Extract job cards using regex patterns
        # Indeed uses data attributes and specific HTML structures
        title_pattern = r'data-jk="([^"]*)"[^>]*>.*?<h2[^>]*>(.*?)</h2>'
        company_pattern = r'class="companyName[^"]*"[^>]*>(.*?)</span>'
        location_pattern = r'class="companyLocation[^"]*"[^>]*>(.*?)</div>'
        summary_pattern = r'class="job-snippet[^"]*"[^>]*>(.*?)</div>'

        titles = re.findall(title_pattern, html, re.DOTALL)
        companies = re.findall(company_pattern, html, re.DOTALL)
        locations = re.findall(location_pattern, html, re.DOTALL)
        summaries = re.findall(summary_pattern, html, re.DOTALL)

        for i in range(min(len(titles), limit)):
            job_key = titles[i][0] if i < len(titles) else ""
            job_title = _clean_html(titles[i][1] if i < len(titles) else "")
            company = _clean_html(companies[i]) if i < len(companies) else ""
            location = _clean_html(locations[i]) if i < len(locations) else ""
            summary = _clean_html(summaries[i]) if i < len(summaries) else ""

            job_url = f"{self.BASE_URL}/viewjob?jk={job_key}" if job_key else search_url

            jobs.append({
                "source": "indeed",
                "scraped_at": datetime.now().isoformat(),
                "job_title": job_title,
                "company_name": company,
                "location": location,
                "description": summary,
                "job_url": job_url,
                "posted_date": "",
            })

        return jobs


# ── Glassdoor Scraper ─────────────────────────────────────────


class GlassdoorScraper:
    """Search Glassdoor for job postings."""

    BASE_URL = "https://www.glassdoor.com"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._request_count = 0

    def search(
        self,
        query: str,
        location: str = "",
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """Search Glassdoor for jobs."""
        self._request_count += 1
        time.sleep(3)  # respectful delay (Glassdoor is aggressive with blocking)

        params = {
            "sc.keyword": query,
            "locT": "",
            "locId": "",
            "locKeyword": location,
            "jobType": "",
            "fromAge": 14,  # last 14 days
        }

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/Job/jobs.htm",
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            return self._parse_search_page(resp.text)
        except requests.RequestException as e:
            print(f"    [WARN] Glassdoor error for '{query}': {e}")
            return []

    def _parse_search_page(self, html: str) -> List[Dict[str, Any]]:
        """Parse Glassdoor search results."""
        jobs: List[Dict[str, Any]] = []

        title_pattern = r'class="jobInfoItem[^"]*"[^>]*>.*?<a[^>]*>(.*?)</a>'
        company_pattern = r'class="jobInfoItem[^"]*".*?data-company-name="([^"]*)"'
        location_pattern = r'class="jobLocation[^"]*"[^>]*>(.*?)</div>'

        titles = re.findall(title_pattern, html, re.DOTALL)
        companies = re.findall(company_pattern, html, re.DOTALL)
        locations = re.findall(location_pattern, html, re.DOTALL)

        for i in range(min(len(titles), len(companies))):
            jobs.append({
                "source": "glassdoor",
                "scraped_at": datetime.now().isoformat(),
                "job_title": _clean_html(titles[i]) if i < len(titles) else "",
                "company_name": companies[i] if i < len(companies) else "",
                "location": _clean_html(locations[i]) if i < len(locations) else "",
                "description": "",
                "job_url": f"{self.BASE_URL}/Job/jobs.htm",
                "posted_date": "",
            })

        return jobs


# ── Monster Scraper ───────────────────────────────────────────


class MonsterScraper:
    """Search Monster for job postings."""

    BASE_URL = "https://www.monster.com"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._request_count = 0

    def search(
        self,
        query: str,
        location: str = "",
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """Search Monster for jobs."""
        self._request_count += 1
        time.sleep(2)

        params = {
            "q": query,
            "where": location,
        }

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/jobs/search",
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            return self._parse_search_page(resp.text)
        except requests.RequestException as e:
            print(f"    [WARN] Monster error for '{query}': {e}")
            return []

    def _parse_search_page(self, html: str) -> List[Dict[str, Any]]:
        """Parse Monster search results."""
        jobs: List[Dict[str, Any]] = []

        title_pattern = r'class="job-title[^"]*"[^>]*>.*?<a[^>]*>(.*?)</a>'
        company_pattern = r'class="company[^"]*"[^>]*>(.*?)</span>'
        location_pattern = r'class="location[^"]*"[^>]*>(.*?)</span>'

        titles = re.findall(title_pattern, html, re.DOTALL)
        companies = re.findall(company_pattern, html, re.DOTALL)
        locations = re.findall(location_pattern, html, re.DOTALL)

        for i in range(min(len(titles), len(companies))):
            jobs.append({
                "source": "monster",
                "scraped_at": datetime.now().isoformat(),
                "job_title": _clean_html(titles[i]) if i < len(titles) else "",
                "company_name": _clean_html(companies[i]) if i < len(companies) else "",
                "location": _clean_html(locations[i]) if i < len(locations) else "",
                "description": "",
                "job_url": f"{self.BASE_URL}/jobs/search?q={query}",
                "posted_date": "",
            })

        return jobs


# ── Helpers ────────────────────────────────────────────────────


def _clean_html(text: str) -> str:
    """Remove HTML tags and extra whitespace from text."""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ── Public API ────────────────────────────────────────────────


def scrape_job_boards(
    queries: Optional[List[str]] = None,
    sources: Optional[List[str]] = None,
    location: str = "",
    limit_per_query: int = 25,
    output_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search multiple job boards for job postings.
    Returns a combined list of parsed job dicts.
    """
    settings = _load_settings()
    jb_config = settings.get("scrapers", {}).get("jobboards", {})

    if queries is None:
        queries = jb_config.get("search_queries", [
            "AI engineer", "machine learning engineer",
            "cloud architect", "data engineer", "DevOps engineer",
            "ecommerce developer", "POS system developer",
        ])

    if sources is None:
        sources = [s["name"] for s in jb_config.get("sources", [])]
        if not sources:
            sources = ["indeed", "glassdoor", "monster"]

    scrapers: Dict[str, Any] = {}
    if "indeed" in sources:
        scrapers["indeed"] = IndeedScraper()
    if "glassdoor" in sources:
        scrapers["glassdoor"] = GlassdoorScraper()
    if "monster" in sources:
        scrapers["monster"] = MonsterScraper()

    all_jobs: List[Dict[str, Any]] = []
    seen = set()

    print(f"\n{'='*60}")
    print(f"  Job Board Scraper")
    print(f"  Sources: {list(scrapers.keys())}")
    print(f"  Queries: {len(queries)}")
    print(f"{'='*60}")

    for source_name, scraper in scrapers.items():
        print(f"\n  --- {source_name.upper()} ---")
        for i, query in enumerate(queries, 1):
            print(f"  [{i}/{len(queries)}] Searching: '{query}'")
            jobs = scraper.search(query, location, limit_per_query)
            for job in jobs:
                key = (job.get("company_name", ""), job.get("job_title", ""))
                if key not in seen:
                    seen.add(key)
                    all_jobs.append(job)
            print(f"    Found {len(jobs)} jobs ({len(all_jobs)} unique total)")

    # Save results
    if output_path is None:
        today = datetime.now().strftime("%Y-%m-%d")
        output_dir = "data/raw"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"jobboard_results_{today}.json")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(all_jobs, fh, indent=2, default=str)

    print(f"\n  Total unique jobs: {len(all_jobs)}")
    print(f"  Saved to: {output_path}")

    return all_jobs


def jobs_to_csv(jobs: List[Dict[str, Any]], output_path: str) -> str:
    """Convert scraped jobs to CSV format compatible with lead engine."""
    import csv

    rows = []
    for job in jobs:
        location = job.get("location", "")
        parts = [p.strip() for p in location.split(",")] if location else ["", ""]
        city = parts[0] if parts else ""
        country = parts[-1] if len(parts) > 1 else ""

        rows.append({
            "Company Name": job.get("company_name", ""),
            "Contact Name": "",
            "Job Title": job.get("job_title", ""),
            "LinkedIn Profile": "",
            "Company LinkedIn": "",
            "Company Website": "",
            "Industry": "",
            "Company Size": "",
            "Country": country,
            "City": city,
            "Technology Stack": "",
            "Job Posting URL": job.get("job_url", ""),
            "Job Posted Date": job.get("posted_date", ""),
            "notes": f"Scraped from {job.get('source', 'unknown')}. {job.get('description', '')[:500]}",
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
    parser = argparse.ArgumentParser(description="Job Board Scraper")
    parser.add_argument("--query", "-q", nargs="*", help="Custom search queries")
    parser.add_argument("--source", "-s", nargs="*", help="Sources to search (indeed, glassdoor, monster)")
    parser.add_argument("--location", "-l", default="", help="Location filter")
    parser.add_argument("--limit", "-n", type=int, default=25, help="Results per query")
    parser.add_argument("--output", "-o", help="Output JSON path")
    parser.add_argument("--csv", help="Also export as CSV")
    args = parser.parse_args()

    jobs = scrape_job_boards(
        queries=args.query,
        sources=args.source,
        location=args.location,
        limit_per_query=args.limit,
        output_path=args.output,
    )

    if args.csv and jobs:
        jobs_to_csv(jobs, args.csv)


if __name__ == "__main__":
    main()
