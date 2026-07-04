"""
Daily Pipeline — Automated daily lead generation run.

Orchestrates the full pipeline:
1. Scrape LinkedIn, Google, job boards
2. Clean & transform raw data
3. Qualify leads with LLM agent
4. Score leads with feedback model
5. Generate reports and dashboard JSON
6. Sync to database and CRM

Usage:
    python -m pipeline.daily_run
    python -m pipeline.daily_run --skip-scraping --input data/input/leads.csv
"""

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Config ─────────────────────────────────────────────────────

def _load_settings() -> Dict[str, Any]:
    """Load settings.yaml."""
    try:
        import yaml
        settings_path = os.path.join("config", "settings.yaml")
        if os.path.exists(settings_path):
            with open(settings_path, "r") as fh:
                return yaml.safe_load(fh) or {}
    except ImportError:
        pass
    return {}


# ── Pipeline Steps ─────────────────────────────────────────────


def step_scrape(
    settings: Dict[str, Any],
    output_dir: str = "data/raw",
) -> str:
    """Step 1: Scrape all data sources."""
    print(f"\n{'='*60}")
    print("  STEP 1: SCRAPING")
    print(f"{'='*60}")

    all_jobs: List[Dict[str, Any]] = []
    scrapers_config = settings.get("scrapers", {})

    # LinkedIn
    if scrapers_config.get("linkedin", {}).get("enabled", True):
        try:
            from scrapers.linkedin_scraper import scrape_linkedin_jobs
            linkedin_jobs = scrape_linkedin_jobs(
                output_path=os.path.join(output_dir, "linkedin_raw.json")
            )
            all_jobs.extend(linkedin_jobs)
            print(f"  LinkedIn: {len(linkedin_jobs)} jobs")
        except Exception as e:
            print(f"  [WARN] LinkedIn scraping failed: {e}")
            traceback.print_exc()

    # Google
    if scrapers_config.get("google", {}).get("enabled", True):
        try:
            from scrapers.google_search import scrape_google
            google_results = scrape_google(
                output_path=os.path.join(output_dir, "google_raw.json")
            )
            all_jobs.extend(google_results)
            print(f"  Google: {len(google_results)} results")
        except Exception as e:
            print(f"  [WARN] Google search failed: {e}")
            traceback.print_exc()

    # Job boards
    if scrapers_config.get("jobboards", {}).get("enabled", True):
        try:
            from scrapers.jobboard_scraper import scrape_job_boards
            board_jobs = scrape_job_boards(
                output_path=os.path.join(output_dir, "jobboards_raw.json")
            )
            all_jobs.extend(board_jobs)
            print(f"  Job boards: {len(board_jobs)} jobs")
        except Exception as e:
            print(f"  [WARN] Job board scraping failed: {e}")
            traceback.print_exc()

    print(f"\n  Total scraped: {len(all_jobs)} records")
    return output_dir


def step_etl(
    raw_dir: str = "data/raw",
    output_path: Optional[str] = None,
) -> str:
    """Step 2: Clean and transform raw data."""
    print(f"\n{'='*60}")
    print("  STEP 2: ETL — CLEAN & TRANSFORM")
    print(f"{'='*60}")

    from etl.clean_transform import clean_and_transform
    return clean_and_transform(raw_dir=raw_dir, output_path=output_path)


def step_qualify(
    input_path: str,
    min_score: float = 70.0,
    use_llm: bool = True,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Step 3: Qualify leads."""
    print(f"\n{'='*60}")
    print("  STEP 3: LEAD QUALIFICATION")
    print(f"{'='*60}")

    import pandas as pd
    if input_path.endswith(".csv"):
        df = pd.read_csv(input_path)
    elif input_path.endswith(".xlsx"):
        df = pd.read_excel(input_path)
    else:
        with open(input_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            df = pd.DataFrame(data)

    leads = df.to_dict(orient="records")
    print(f"  Loaded {len(leads)} leads from {input_path}")

    if use_llm and os.environ.get("OPENAI_API_KEY"):
        try:
            from agents.qualification_agent import qualify_leads
            qualified, rejected = qualify_leads(leads, min_score=min_score)
            return qualified, rejected
        except Exception as e:
            print(f"  [WARN] LLM qualification failed: {e}. Falling back to rule-based.")
            traceback.print_exc(file=sys.stderr)
            return _rule_based_qualify(leads, min_score)
    else:
        print("  Using rule-based qualification (no LLM)")
        return _rule_based_qualify(leads, min_score)


def _rule_based_qualify(
    leads: List[Dict[str, Any]],
    min_score: float = 70.0,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Rule-based qualification fallback."""
    from src.lead_engine import score_lead

    qualified: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for lead in leads:
        score, breakdown = score_lead(lead)
        lead["score"] = score
        lead["score_breakdown"] = breakdown
        lead["qualification_method"] = "rule_based"

        if score >= min_score:
            qualified.append(lead)
        else:
            lead["rejection_reason"] = f"Score {score} below threshold {min_score}"
            rejected.append(lead)

    print(f"  Qualified: {len(qualified)} | Rejected: {len(rejected)}")
    return qualified, rejected


def step_enhance_scores(
    leads: List[Dict[str, Any]],
    feedback_available: bool = True,
) -> List[Dict[str, Any]]:
    """Step 4: Enhance scores with feedback model."""
    print(f"\n{'='*60}")
    print("  STEP 4: FEEDBACK-ENHANCED SCORING")
    print(f"{'='*60}")

    if not feedback_available:
        print("  Skipping feedback scoring (no feedback data)")
        return leads

    try:
        from agents.scoring_agent import FeedbackScorer
        model = FeedbackScorer()
        if model.load():
            for lead in leads:
                fb_score, features = model.score_lead(lead)
                lead["feedback_score"] = fb_score
                # Blend scores: 60% original + 40% feedback model
                orig_score = lead.get("score", 0)
                blended = 0.6 * orig_score + 0.4 * fb_score
                lead["score"] = round(blended, 1)
            print(f"  Enhanced {len(leads)} leads with feedback model")
        else:
            print("  No trained feedback model found. Using original scores.")
    except Exception as e:
        print(f"  [WARN] Feedback scoring failed: {e}")
        traceback.print_exc(file=sys.stderr)

    return leads


def step_generate_reports(
    qualified: List[Dict[str, Any]],
    rejected: List[Dict[str, Any]],
) -> Dict[str, str]:
    """Step 5: Generate all reports."""
    print(f"\n{'='*60}")
    print("  STEP 5: GENERATE REPORTS")
    print(f"{'='*60}")

    from src.lead_engine import (
        generate_excel_report,
        generate_pdf_report,
        generate_daily_summary,
        generate_approval_digest,
        export_dashboard_json,
    )

    today = datetime.now().strftime("%Y-%m-%d")
    output_dir = "data/output"
    os.makedirs(output_dir, exist_ok=True)

    paths = {}

    # Excel
    xlsx = os.path.join(output_dir, f"leads_{today}.xlsx")
    generate_excel_report(qualified, xlsx)
    paths["excel"] = xlsx

    # PDF
    pdf = os.path.join(output_dir, f"leads_{today}.pdf")
    generate_pdf_report(qualified, rejected, pdf)
    paths["pdf"] = pdf

    # Text summary
    txt = os.path.join(output_dir, f"daily_summary_{today}.txt")
    generate_daily_summary(qualified, rejected, txt)
    paths["summary"] = txt

    # Dashboard JSON
    json_path = export_dashboard_json(qualified, rejected)
    paths["dashboard_json"] = json_path

    # Approval digest
    digest = generate_approval_digest(qualified, rejected, output_dir)
    paths["digest"] = digest

    print(f"  Reports generated: {list(paths.keys())}")
    return paths


def step_store_database(
    qualified: List[Dict[str, Any]],
    rejected: List[Dict[str, Any]],
    duration: float,
) -> None:
    """Step 6: Store results in database."""
    print(f"\n{'='*60}")
    print("  STEP 6: DATABASE STORAGE")
    print(f"{'='*60}")

    try:
        from db.postgres_connector import LeadDatabase
        db = LeadDatabase()

        # Store qualified leads
        q_count = db.insert_batch(qualified)
        r_count = db.insert_batch(rejected)

        # Log pipeline run
        db.log_pipeline_run(
            total=len(qualified) + len(rejected),
            qualified=len(qualified),
            rejected=len(rejected),
            duration=duration,
            status="success",
        )

        stats = db.get_stats()
        print(f"  Stored: {q_count} qualified, {r_count} rejected")
        print(f"  Database stats: {stats}")

        db.close()
    except Exception as e:
        print(f"  [WARN] Database storage failed: {e}")
        traceback.print_exc()


def step_build_embeddings(leads: List[Dict[str, Any]]) -> None:
    """Step 7: Build embeddings index (optional)."""
    print(f"\n{'='*60}")
    print("  STEP 7: BUILD EMBEDDINGS INDEX")
    print(f"{'='*60}")

    if not os.environ.get("OPENAI_API_KEY"):
        print("  Skipping embeddings (no OPENAI_API_KEY)")
        return

    try:
        from etl.embeddings import build_embeddings_index
        build_embeddings_index(leads, output_path="data/embeddings")
    except Exception as e:
        print(f"  [WARN] Embeddings build failed: {e}")
        traceback.print_exc()


def step_send_notification(summary_dict: Dict[str, Any]) -> None:
    """Step 8: Send email notification on pipeline completion."""
    print(f"\n{'='*60}")
    print("  STEP 8: EMAIL NOTIFICATION")
    print(f"{'='*60}")

    try:
        from pipeline.email_notifier import notify_success
        sent = notify_success(summary_dict)
        if sent:
            print("  Notification sent.")
        else:
            print("  Skipped (not configured or no recipient).")
    except Exception as e:
        print(f"  [WARN] Email notification failed: {e}")
        traceback.print_exc(file=sys.stderr)


# ── Main Pipeline ──────────────────────────────────────────────


def run_pipeline(
    skip_scraping: bool = False,
    input_path: Optional[str] = None,
    min_score: float = 70.0,
    use_llm: bool = True,
    skip_embeddings: bool = False,
) -> Dict[str, Any]:
    """
    Run the complete daily pipeline.
    Returns a summary dict.
    """
    start_time = time.time()

    print(f"\n{'#'*60}")
    print(f"  DAILY LEAD GENERATION PIPELINE")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*60}")

    settings = _load_settings()

    # Step 1: Scrape (unless skipped or input provided)
    raw_dir = "data/raw"
    if not skip_scraping and not input_path:
        step_scrape(settings, raw_dir)

    # Step 2: ETL
    if input_path:
        csv_path = input_path
    else:
        csv_path = step_etl(raw_dir)

    # Step 3: Qualify
    qualified, rejected = step_qualify(csv_path, min_score, use_llm)

    # Step 4: Feedback-enhanced scoring
    from agents.scoring_agent import load_feedback
    feedback = load_feedback()
    feedback_available = bool(feedback.get("accepted") or feedback.get("rejected"))
    all_leads = qualified + rejected
    all_leads = step_enhance_scores(all_leads, feedback_available)

    # Re-split after score enhancement
    qualified = [l for l in all_leads if l.get("score", 0) >= min_score]
    rejected = [l for l in all_leads if l.get("score", 0) < min_score]

    # Step 5: Generate reports
    report_paths = step_generate_reports(qualified, rejected)

    # Step 6: Store in database
    duration = time.time() - start_time
    step_store_database(qualified, rejected, duration)

    # Step 7: Build embeddings (optional)
    if not skip_embeddings:
        step_build_embeddings(qualified)

    # Step 8: Send email notification
    hot_count = len([l for l in qualified if l.get("score", 0) >= 85])
    warm_count = len([l for l in qualified if 75 <= l.get("score", 0) < 85])
    step_send_notification(summary_dict={
        "date": datetime.now().isoformat(),
        "duration_seconds": round(time.time() - start_time, 2),
        "total_leads": len(qualified) + len(rejected),
        "qualified": len(qualified),
        "rejected": len(rejected),
        "hot": hot_count,
        "warm": warm_count,
        "reports": report_paths,
    })

    # Summary
    duration = time.time() - start_time
    summary = {
        "date": datetime.now().isoformat(),
        "duration_seconds": round(duration, 2),
        "total_leads": len(qualified) + len(rejected),
        "qualified": len(qualified),
        "rejected": len(rejected),
        "reports": report_paths,
        "min_score": min_score,
        "use_llm": use_llm,
    }

    print(f"\n{'#'*60}")
    print(f"  PIPELINE COMPLETE")
    print(f"  Duration: {duration:.1f}s")
    print(f"  Total leads: {summary['total_leads']}")
    print(f"  Qualified: {summary['qualified']}")
    print(f"  Rejected: {summary['rejected']}")
    print(f"  Reports: {list(report_paths.keys())}")
    print(f"{'#'*60}\n")

    # Save run summary
    summary_path = f"data/output/pipeline_summary_{datetime.now().strftime('%Y-%m-%d')}.json"
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)

    return summary


# ── CLI ────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily Lead Generation Pipeline")
    parser.add_argument(
        "--skip-scraping", action="store_true",
        help="Skip the scraping step",
    )
    parser.add_argument(
        "--input", "-i",
        help="Use a specific input CSV file instead of scraped data",
    )
    parser.add_argument(
        "--min-score", "-m", type=float, default=70.0,
        help="Minimum lead score threshold (default: 70)",
    )
    parser.add_argument(
        "--no-llm", action="store_true",
        help="Disable LLM qualification (use rule-based only)",
    )
    parser.add_argument(
        "--skip-embeddings", action="store_true",
        help="Skip building embeddings index",
    )
    args = parser.parse_args()

    try:
        start_time = time.time()
        run_pipeline(
            skip_scraping=args.skip_scraping,
            input_path=args.input,
            min_score=args.min_score,
            use_llm=not args.no_llm,
            skip_embeddings=args.skip_embeddings,
        )
    except Exception as e:
        duration = time.time() - start_time
        print(f"\n  ❌ Pipeline failed: {e}")
        traceback.print_exc()
        try:
            from pipeline.email_notifier import notify_failure
            notify_failure(
                error_message=str(e),
                error_traceback=traceback.format_exc(),
                duration=duration,
            )
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
