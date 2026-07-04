"""
MCP Server — Expose lead generation tools via Model Context Protocol.

This MCP server makes the lead generation agent's capabilities available
to any MCP-compatible AI client (Claude Desktop, Cursor, etc.).

Usage:
    # Run directly (stdio transport)
    python -m mcp_server

    # Or via the MCP config in Claude Desktop:
    # Add to claude_desktop_config.json:
    # {
    #   "mcpServers": {
    #     "leadgen": {
    #       "command": "python",
    #       "args": ["-m", "mcp_server"],
    #       "cwd": "/path/to/leadgen-agent"
    #     }
    #   }
    # }
"""

import json
import os
import sys
from datetime import datetime
from typing import Optional

from mcp.server.fastmcp import FastMCP

# ── Initialize MCP Server ──────────────────────────────────────

mcp = FastMCP(
    "LeadGen Agent",
    instructions=(
        "AI-powered B2B lead generation agent. "
        "Use these tools to scrape job boards, qualify leads with GPT-4o, "
        "score them with ML, generate outreach emails, and manage the pipeline."
    ),
)


# ── Tools ──────────────────────────────────────────────────────


@mcp.tool()
def score_lead(
    company_name: str,
    job_title: str,
    industry: str = "",
    company_size: str = "",
    country: str = "",
    city: str = "",
    technology_stack: str = "",
    job_posting_url: str = "",
) -> str:
    """
    Score a single lead using the rule-based scoring engine.

    Returns a score (0-100) with a breakdown of technology match, hiring activity,
    company size, industry relevance, and decision-maker seniority.

    Args:
        company_name: Name of the target company
        job_title: Job title or role being hired for
        industry: Company industry (e.g., "Information Technology", "E-Commerce")
        company_size: Employee count range (e.g., "201-500", "1000+")
        country: Country location
        city: City location
        technology_stack: Technologies mentioned in the job posting
        job_posting_url: URL of the job posting
    """
    sys.path.insert(0, os.getcwd())
    from src.lead_engine import score_lead as _score_lead

    lead = {
        "Company Name": company_name,
        "Job Title": job_title,
        "Industry": industry,
        "Company Size": company_size,
        "Country": country,
        "City": city,
        "Technology Stack": technology_stack,
        "Job Posting URL": job_posting_url,
    }

    total_score, breakdown = _score_lead(lead)

    result = {
        "score": total_score,
        "priority": "HOT" if total_score >= 85 else "WARM" if total_score >= 75 else "QUALIFIED",
        "breakdown": breakdown,
    }
    return json.dumps(result, indent=2)


@mcp.tool()
def generate_outreach_email(
    company_name: str,
    contact_name: str,
    job_title: str,
    technology_stack: str = "",
    industry: str = "",
) -> str:
    """
    Generate a personalized outreach email draft for a lead.

    Creates a professional email tailored to the company and role,
    referencing relevant technologies and services.

    Args:
        company_name: Target company name
        contact_name: Decision-maker's name
        job_title: Their job title or role
        technology_stack: Technologies they use (e.g., "Python, AWS, Docker")
        industry: Their industry
    """
    sys.path.insert(0, os.getcwd())
    from src.lead_engine import generate_email

    lead = {
        "Company Name": company_name,
        "Contact Name": contact_name,
        "Job Title": job_title,
        "Technology Stack": technology_stack,
        "Industry": industry,
    }

    email = generate_email(lead)
    return email


@mcp.tool()
def scrape_linkedin_jobs(
    queries: str = "AI engineer hiring,machine learning engineer,cloud architect",
    limit_per_query: int = 10,
) -> str:
    """
    Search LinkedIn for job postings matching the given queries.

    Scrapes LinkedIn for job listings and returns structured data
    with company names, titles, locations, and job URLs.

    Args:
        queries: Comma-separated search queries (e.g., "AI engineer,data engineer")
        limit_per_query: Max results per query (default: 10)
    """
    sys.path.insert(0, os.getcwd())
    from scrapers.linkedin_scraper import scrape_linkedin_jobs as _scrape

    query_list = [q.strip() for q in queries.split(",") if q.strip()]
    jobs = _scrape(queries=query_list, limit_per_query=limit_per_query)

    return json.dumps({
        "total_jobs": len(jobs),
        "jobs": jobs[:50],  # limit output
    }, indent=2, default=str)


@mcp.tool()
def scrape_job_boards(
    queries: str = "AI engineer,machine learning,cloud architect",
    sources: str = "indeed,glassdoor,monster",
    limit_per_query: int = 10,
) -> str:
    """
    Search multiple job boards (Indeed, Glassdoor, Monster) for job postings.

    Args:
        queries: Comma-separated search queries
        sources: Comma-separated job board names
        limit_per_query: Max results per query
    """
    sys.path.insert(0, os.getcwd())
    from scrapers.jobboard_scraper import scrape_job_boards as _scrape

    query_list = [q.strip() for q in queries.split(",") if q.strip()]
    source_list = [s.strip() for s in sources.split(",") if s.strip()]
    jobs = _scrape(queries=query_list, sources=source_list, limit_per_query=limit_per_query)

    return json.dumps({
        "total_jobs": len(jobs),
        "jobs": jobs[:50],
    }, indent=2, default=str)


@mcp.tool()
def run_full_pipeline(
    input_csv: str = "",
    min_score: float = 70.0,
    skip_scraping: bool = False,
    use_llm: bool = True,
) -> str:
    """
    Run the complete lead generation pipeline end-to-end.

    Steps: Scrape → ETL → Qualify (LLM) → Score (ML) → Reports → DB → Email

    Args:
        input_csv: Path to input CSV (leave empty to scrape fresh data)
        min_score: Minimum lead score threshold (default: 70)
        skip_scraping: Skip the scraping step if True
        use_llm: Use GPT-4o for qualification if True
    """
    sys.path.insert(0, os.getcwd())
    from pipeline.daily_run import run_pipeline

    summary = run_pipeline(
        skip_scraping=skip_scraping,
        input_path=input_csv if input_csv else None,
        min_score=min_score,
        use_llm=use_llm,
        skip_embeddings=True,
    )

    return json.dumps(summary, indent=2, default=str)


@mcp.tool()
def get_lead_history_stats() -> str:
    """
    Get statistics about tracked leads and companies.

    Returns total unique contacts and companies tracked in the CRM history.
    """
    sys.path.insert(0, os.getcwd())
    from src.lead_engine import LeadHistory

    history = LeadHistory()
    stats = history.get_stats()
    return json.dumps(stats, indent=2)


@mcp.tool()
def search_similar_leads(query: str, top_k: int = 5) -> str:
    """
    Search the embeddings index for leads similar to a natural language query.

    Uses vector similarity search to find leads matching a description
    like "AWS cloud migration company in healthcare".

    Args:
        query: Natural language description of the type of lead to find
        top_k: Number of results to return (default: 5)
    """
    sys.path.insert(0, os.getcwd())
    from etl.embeddings import search_similar_leads as _search

    results = _search(query, top_k=top_k)
    return json.dumps(results, indent=2, default=str)


@mcp.tool()
def qualify_leads_llm(
    leads_json: str,
    min_score: float = 70.0,
) -> str:
    """
    Qualify a batch of leads using GPT-4o LLM analysis.

    Each lead is evaluated against target criteria (industry, tech, region,
    hiring signals, company size) with detailed reasoning.

    Args:
        leads_json: JSON array of lead objects with Company Name, Job Title, etc.
        min_score: Minimum qualification score threshold
    """
    sys.path.insert(0, os.getcwd())
    from agents.qualification_agent import qualify_leads

    leads = json.loads(leads_json)
    qualified, rejected = qualify_leads(leads, min_score=min_score)

    return json.dumps({
        "qualified_count": len(qualified),
        "rejected_count": len(rejected),
        "qualified_leads": [
            {
                "company": l.get("Company Name", ""),
                "score": l.get("llm_score", 0),
                "reasoning": l.get("llm_reasoning", "")[:200],
            }
            for l in qualified[:20]
        ],
    }, indent=2, default=str)


@mcp.tool()
def give_feedback(
    company_name: str,
    contact_name: str = "",
    job_title: str = "",
    accepted: bool = True,
    score: float = 0.0,
) -> str:
    """
    Submit feedback on a lead (accept or reject) to train the scoring model.

    Feedback is stored and used to retrain the ML scoring agent,
    improving future lead qualification accuracy.

    Args:
        company_name: Company name of the lead
        contact_name: Contact person's name
        job_title: Job title or role
        accepted: True to accept, False to reject
        score: The lead's score
    """
    sys.path.insert(0, os.getcwd())
    from agents.scoring_agent import add_feedback

    lead = {
        "Company Name": company_name,
        "Contact Name": contact_name,
        "Job Title": job_title,
        "score": score,
    }

    add_feedback(lead, accepted=accepted)

    return json.dumps({
        "status": "recorded",
        "action": "accepted" if accepted else "rejected",
        "company": company_name,
        "message": f"Feedback {'accepted' if accepted else 'rejected'} for {company_name}. "
                   "Run --retrain on scoring_agent to update the model.",
    }, indent=2)


@mcp.tool()
def retrain_scoring_model() -> str:
    """
    Retrain the ML scoring model on accumulated feedback data.

    Should be called periodically after collecting enough accept/reject
    feedback to improve scoring accuracy.
    """
    sys.path.insert(0, os.getcwd())
    from agents.scoring_agent import retrain_model

    model = retrain_model()
    importance = model.get_feature_importance()

    return json.dumps({
        "status": "retrained",
        "samples": model.n_samples,
        "features": len(model.weights),
        "top_features": [
            {"name": name, "weight": round(weight, 4)}
            for name, weight in importance[:5]
        ],
    }, indent=2)


@mcp.tool()
def get_today_report() -> str:
    """
    Get today's lead generation summary report.

    Returns the text summary of today's processed leads, including
    qualified leads, rejected leads, top technologies, and industries.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    txt_path = f"data/output/daily_summary_{today}.txt"

    if os.path.exists(txt_path):
        with open(txt_path, "r", encoding="utf-8") as fh:
            return fh.read()
    else:
        return f"No report found for today ({today}). Run the pipeline first."


# ── Run Server ─────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
