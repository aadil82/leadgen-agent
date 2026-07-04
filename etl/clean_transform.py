"""
ETL — Clean & Transform raw scraped data into lead-engine-compatible CSV format.

Pipeline:
    1. Load raw JSON from scrapers (LinkedIn, Google, job boards)
    2. Deduplicate across sources
    3. Normalize fields (company names, locations, tech stacks)
    4. Enrich with additional context
    5. Export clean CSV for lead engine consumption

Usage:
    python -m etl.clean_transform --input data/raw/ --output data/input/
"""

import argparse
import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd


# ── Tech Stack Normalizer ─────────────────────────────────────

TECH_ALIASES: Dict[str, str] = {
    "python": "Python",
    "java": "Java",
    "c#": "C#",
    "csharp": "C#",
    ".net": ".NET",
    "dotnet": ".NET",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    "go": "Go",
    "golang": "Go",
    "rust": "Rust",
    "aws": "AWS",
    "amazon web services": "AWS",
    "microsoft azure": "Azure",
    "azure": "Azure",
    "google cloud": "GCP",
    "gcp": "GCP",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "docker": "Docker",
    "terraform": "Terraform",
    "ansible": "Ansible",
    "linux": "Linux",
    "sql": "SQL",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "snowflake": "Snowflake",
    "oracle": "Oracle",
    "mongodb": "MongoDB",
    "mongo": "MongoDB",
    "databricks": "Databricks",
    "spark": "Spark",
    "apache spark": "Spark",
    "etl": "ETL",
    "airflow": "Airflow",
    "ai": "AI",
    "artificial intelligence": "AI",
    "machine learning": "Machine Learning",
    "ml": "Machine Learning",
    "generative ai": "Generative AI",
    "genai": "Generative AI",
    "llm": "LLM",
    "large language model": "LLM",
    "openai": "OpenAI",
    "react": "React",
    "angular": "Angular",
    "vue.js": "Vue.js",
    "vue": "Vue.js",
    "django": "Django",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "spring boot": "Spring Boot",
    "springboot": "Spring Boot",
    "microservices": "Microservices",
    "salesforce": "Salesforce",
    "sap": "SAP",
    "power bi": "Power BI",
    "tableau": "Tableau",
    "cyber security": "Cyber Security",
    "cloud migration": "Cloud Migration",
    "data engineering": "Data Engineering",
    "data science": "Data Science",
    "ecommerce": "E-Commerce",
    "e-commerce": "E-Commerce",
    "pos": "POS",
    "point of sale": "POS",
    "shopify": "Shopify",
    "wordpress": "WordPress",
    "cms": "CMS",
}


def normalize_tech_stack(raw_techs: Any) -> str:
    """Normalize a list or string of technologies into a semicolon-separated string."""
    if isinstance(raw_techs, list):
        items = raw_techs
    elif isinstance(raw_techs, str):
        items = [t.strip() for t in re.split(r"[;,/|]", raw_techs) if t.strip()]
    else:
        return ""

    normalized = set()
    for item in items:
        key = item.lower().strip()
        if key in TECH_ALIASES:
            normalized.add(TECH_ALIASES[key])
        elif len(item) > 1:
            # Keep original casing if no alias found, but capitalize properly
            normalized.add(item.strip().title())

    return "; ".join(sorted(normalized))


# ── Location Normalizer ───────────────────────────────────────

COUNTRY_ALIASES: Dict[str, str] = {
    "us": "United States",
    "usa": "United States",
    "united states": "United States",
    "uk": "United Kingdom",
    "united kingdom": "United Kingdom",
    "england": "United Kingdom",
    "great britain": "United Kingdom",
    "ca": "Canada",
    "de": "Germany",
    "deutschland": "Germany",
    "in": "India",
    "au": "Australia",
    "australia": "Australia",
    "nl": "Netherlands",
    "sg": "Singapore",
    "uae": "United Arab Emirates",
    "dubai": "United Arab Emirates",
}

US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming", "dc",
}


def normalize_location(raw_location: str) -> Dict[str, str]:
    """Parse a raw location string into city and country components."""
    if not raw_location or not isinstance(raw_location, str):
        return {"city": "", "country": ""}

    parts = [p.strip() for p in raw_location.split(",")]
    city = parts[0] if parts else ""
    country = ""

    if len(parts) >= 2:
        last_part = parts[-1].strip().lower()
        if last_part in COUNTRY_ALIASES:
            country = COUNTRY_ALIASES[last_part]
        elif last_part in US_STATES or len(last_part) == 2:
            country = "United States"
        else:
            country = parts[-1].strip()

    # If no country found, check if city is in US states
    if not country and city.lower() in US_STATES:
        country = "United States"

    return {"city": city, "country": country}


# ── Company Name Cleaner ──────────────────────────────────────


def clean_company_name(name: str) -> str:
    """Clean and normalize a company name."""
    if not name:
        return ""

    # Remove common suffixes
    suffixes = [
        " Inc.", " Inc", " LLC", " Ltd.", " Ltd", " Ltd.", " Limited",
        " Corp.", " Corp", " Corporation", " Co.", " Co", " Company",
        " Pvt.", " Pvt", " Pvt. Ltd", " S.A.S.", " S.A.", " GmbH",
        " B.V.", " Pte. Ltd", " Pvt. Ltd.",
    ]
    cleaned = name.strip()
    for suffix in suffixes:
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
            break

    # Remove extra whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


# ── Email Pattern Extractor ───────────────────────────────────


def extract_contact_hint(text: str) -> Dict[str, str]:
    """Try to extract contact name hints from text."""
    result = {"name": "", "title": ""}

    # Look for common patterns
    patterns = [
        r"(?:contact|hire|recruiter|manager|director|vp|cto|ceo):\s*([A-Z][a-z]+\s+[A-Z][a-z]+)",
        r"(?:reached?\s+out|posted\s+by|hiring\s+manager)\s*:?\s*([A-Z][a-z]+\s+[A-Z][a-z]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            result["name"] = match.group(1)
            break

    return result


# ── Deduplication ──────────────────────────────────────────────


def deduplicate_leads(leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate leads based on company name + job title."""
    seen = set()
    unique: List[Dict[str, Any]] = []

    for lead in leads:
        company = clean_company_name(lead.get("Company Name", "")).lower()
        title = lead.get("Job Title", "").lower().strip()
        key = f"{company}|{title}"

        if key not in seen:
            seen.add(key)
            unique.append(lead)

    removed = len(leads) - len(unique)
    if removed > 0:
        print(f"  Deduplication: removed {removed} duplicates ({len(unique)} unique)")

    return unique


# ── Main ETL Pipeline ─────────────────────────────────────────


def clean_and_transform(
    raw_dir: str = "data/raw",
    output_path: Optional[str] = None,
) -> str:
    """
    Main ETL pipeline:
    1. Load all raw JSON files from the raw directory
    2. Normalize and clean fields
    3. Deduplicate
    4. Export as lead-engine-compatible CSV
    """
    if output_path is None:
        today = datetime.now().strftime("%Y-%m-%d")
        os.makedirs("data/input", exist_ok=True)
        output_path = f"data/input/leads_{today}.csv"

    print(f"\n{'='*60}")
    print(f"  ETL Pipeline — Clean & Transform")
    print(f"  Source: {raw_dir}")
    print(f"  Output: {output_path}")
    print(f"{'='*60}")

    # Step 1: Load all raw data
    all_leads: List[Dict[str, Any]] = []
    if not os.path.isdir(raw_dir):
        print(f"  [WARN] Raw directory not found: {raw_dir}")
        return output_path

    for filename in sorted(os.listdir(raw_dir)):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(raw_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                all_leads.extend(data)
                print(f"  Loaded {len(data)} records from {filename}")
            elif isinstance(data, dict):
                all_leads.append(data)
                print(f"  Loaded 1 record from {filename}")
        except Exception as e:
            print(f"  [WARN] Failed to load {filename}: {e}")

    if not all_leads:
        print("  No raw data found. Creating empty output.")
        return output_path

    print(f"\n  Total raw records: {len(all_leads)}")

    # Step 2: Transform each lead into lead-engine format
    transformed: List[Dict[str, Any]] = []
    for raw in all_leads:
        lead = _transform_lead(raw)
        if lead:
            transformed.append(lead)

    print(f"  Transformed records: {len(transformed)}")

    # Step 3: Deduplicate
    unique_leads = deduplicate_leads(transformed)

    # Step 4: Export as CSV
    if unique_leads:
        df = pd.DataFrame(unique_leads)
        # Ensure all required columns exist
        required_cols = [
            "Company Name", "Contact Name", "Job Title", "LinkedIn Profile",
            "Industry", "Company Size", "Country", "City",
        ]
        for col in required_cols:
            if col not in df.columns:
                df[col] = ""

        # Reorder columns
        output_cols = [
            "Company Name", "Contact Name", "Job Title", "LinkedIn Profile",
            "Company LinkedIn", "Company Website", "Industry", "Company Size",
            "Country", "City", "Technology Stack", "Job Posting URL",
            "Job Posted Date", "notes",
        ]
        available = [c for c in output_cols if c in df.columns]
        df = df[available]

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df.to_csv(output_path, index=False, encoding="utf-8")
        print(f"\n  Exported {len(unique_leads)} leads to: {output_path}")
    else:
        print("\n  No leads to export.")

    return output_path


def _transform_lead(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Transform a raw lead from any source into lead-engine CSV format."""
    # Extract company name (try multiple field names)
    company = (
        raw.get("company_name", "")
        or raw.get("Company Name", "")
        or raw.get("organization", "")
        or ""
    )
    company = clean_company_name(company)
    if not company:
        return None

    # Extract job title
    title = (
        raw.get("job_title", "")
        or raw.get("Job Title", "")
        or raw.get("title", "")
        or ""
    )

    # Extract contact info
    contact_name = (
        raw.get("contact_name", "")
        or raw.get("Contact Name", "")
        or raw.get("contact", "")
        or ""
    )

    # If no contact name, try to extract from description
    if not contact_name:
        desc = raw.get("description", "") or raw.get("snippet", "") or ""
        hint = extract_contact_hint(desc)
        contact_name = hint.get("name", "")

    # Extract LinkedIn profile
    linkedin = (
        raw.get("linkedin_url", "")
        or raw.get("LinkedIn Profile", "")
        or raw.get("linkedin", "")
        or ""
    )
    company_linkedin = (
        raw.get("company_linkedin", "")
        or raw.get("Company LinkedIn", "")
        or ""
    )

    # Extract website
    website = (
        raw.get("website", "")
        or raw.get("Company Website", "")
        or ""
    )

    # Extract industry
    industry = (
        raw.get("industry", "")
        or raw.get("Industry", "")
        or ""
    )
    if isinstance(industry, list):
        industry = ", ".join(industry)

    # Extract company size
    size = (
        raw.get("company_size", "")
        or raw.get("Company Size", "")
        or ""
    )
    if isinstance(size, dict):
        size = size.get("text", str(size))

    # Normalize location
    raw_location = (
        raw.get("location", "")
        or raw.get("Country", "")
        or ""
    )
    loc = normalize_location(raw_location)

    # Get country and city from raw if available, else use normalized
    country = raw.get("Country", "") or loc["country"]
    city = raw.get("City", "") or loc["city"]

    # Normalize tech stack
    raw_techs = (
        raw.get("detected_technologies", [])
        or raw.get("Technology Stack", "")
        or raw.get("tech_stack", "")
        or ""
    )
    tech_stack = normalize_tech_stack(raw_techs)

    # Extract job posting URL
    job_url = (
        raw.get("job_url", "")
        or raw.get("Job Posting URL", "")
        or ""
    )

    # Extract posted date
    posted_date = (
        raw.get("posted_date", "")
        or raw.get("Job Posted Date", "")
        or ""
    )

    # Build notes
    notes = raw.get("notes", "") or raw.get("snippet", "") or raw.get("description", "")
    if isinstance(notes, str):
        notes = notes[:1000]
    else:
        notes = str(notes)[:1000]

    return {
        "Company Name": company,
        "Contact Name": contact_name,
        "Job Title": title,
        "LinkedIn Profile": linkedin,
        "Company LinkedIn": company_linkedin,
        "Company Website": website,
        "Industry": industry,
        "Company Size": size,
        "Country": country,
        "City": city,
        "Technology Stack": tech_stack,
        "Job Posting URL": job_url,
        "Job Posted Date": posted_date,
        "notes": notes,
    }


# ── CLI ────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="ETL Clean & Transform Pipeline")
    parser.add_argument("--input", "-i", default="data/raw", help="Raw data directory")
    parser.add_argument("--output", "-o", help="Output CSV path")
    args = parser.parse_args()

    clean_and_transform(raw_dir=args.input, output_path=args.output)


if __name__ == "__main__":
    main()
