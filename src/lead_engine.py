"""
Lead Engine — scoring, email generation, report generation, and CRM-like history tracking.

Usage:
    python -m src.lead_engine --input data/input/leads_2026-06-27.csv --min-score 70
    python -m src.lead_engine --summary                    # generate today's summary
    python -m src.lead_engine --report data/output/leads_2026-06-27.xlsx   # print report
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from src.config import (
    APPROVAL_EMAIL,
    COMPANY_NAME,
    COMPANY_DESCRIPTION,
    DATA_DIR,
    DEFAULT_WEIGHTS,
    DUPLICATE_COOLDOWN_DAYS,
    HIRING_SIGNALS,
    HISTORY_DIR,
    INPUT_DIR,
    OUTPUT_DIR,
    RELEVANT_EXPERIENCE,
    SENDER_EMAIL,
    SENDER_NAME,
    SENDER_TITLE,
    SERVICES_OFFERED,
    TECHNOLOGY_KEYWORDS,
    TEMPLATES_DIR,
)

# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════


def _ensure_dirs() -> None:
    for d in (INPUT_DIR, OUTPUT_DIR, HISTORY_DIR):
        Path(d).mkdir(parents=True, exist_ok=True)


def _today_str() -> str:
    return date.today().isoformat()


def _detect_technologies(text: str) -> List[str]:
    """Return list of known technology keywords found in *text* (case-insensitive)."""
    lower = text.lower()
    matched = []
    for kw in TECHNOLOGY_KEYWORDS:
        if kw.lower() in lower:
            matched.append(kw)
    return list(set(matched))


def _detect_hiring_signals(text: str) -> List[str]:
    """Return list of hiring-signal phrases found in *text*."""
    lower = text.lower()
    matched = []
    for phrase in HIRING_SIGNALS:
        if phrase.lower() in lower:
            matched.append(phrase)
    return list(set(matched))


def _seniority_score(job_title: str) -> float:
    """Score based on how senior / decision-maker the role is (0-15)."""
    title_lower = job_title.lower()
    senior_roles = {
        "cto": 15,
        "chief technology officer": 15,
        "vp of engineering": 15,
        "vice president of engineering": 15,
        "director of technology": 14,
        "director of engineering": 14,
        "engineering manager": 13,
        "technical manager": 12,
        "delivery manager": 12,
        "talent acquisition": 10,
        "recruiter": 8,
        "hr manager": 8,
        "hiring manager": 10,
        "head of engineering": 14,
        "head of technology": 14,
        "chief architect": 13,
        "solution architect": 11,
    }
    for role, score in senior_roles.items():
        if role in title_lower:
            return score
    return 3  # default junior


def _industry_relevance(industry: str) -> float:
    """Score industry relevance (0-10)."""
    high = [
        "information technology", "it", "software", "technology",
        "computer software", "internet", "telecommunications",
        "financial services", "banking", "insurance",
        "healthcare", "pharmaceutical", "biotech",
        "consulting", "professional services",
        "e-commerce", "retail technology",
        "manufacturing", "automotive",
    ]
    medium = [
        "education", "government", "non-profit",
        "media", "entertainment", "logistics",
    ]
    ind_lower = industry.lower().strip()
    for keyword in high:
        if keyword in ind_lower:
            return 10.0
    for keyword in medium:
        if keyword in ind_lower:
            return 6.0
    return 3.0


def _company_size_score(size_str: str) -> float:
    """
    Parse a company-size string (e.g. '201-500', '1000+', '10000+')
    and return a score (0-10). Mid-to-large enterprises score higher.
    """
    if not size_str or size_str.strip() == "":
        return 5.0
    # Try to extract numbers
    numbers = re.findall(r"\d+", size_str.replace(",", ""))
    if not numbers:
        return 5.0
    max_val = max(int(n) for n in numbers)
    if max_val >= 10000:
        return 10.0
    if max_val >= 1000:
        return 9.0
    if max_val >= 500:
        return 8.0
    if max_val >= 200:
        return 7.0
    if max_val >= 50:
        return 5.0
    if max_val >= 10:
        return 3.0
    return 1.0


# ═══════════════════════════════════════════════════════════════
#  HISTORY (lightweight CRM)
# ═══════════════════════════════════════════════════════════════


class LeadHistory:
    """JSON-based history to track contacted leads and avoid duplicates."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or os.path.join(HISTORY_DIR, "leads_history.json")
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        _ensure_dirs()
        if os.path.exists(self.path):
            with open(self.path, "r") as fh:
                return json.load(fh)
        return {"contacts": {}, "companies": {}}

    def save(self) -> None:
        _ensure_dirs()
        with open(self.path, "w") as fh:
            json.dump(self._data, fh, indent=2, default=str)

    def is_duplicate_person(self, name: str, company: str, days: int = DUPLICATE_COOLDOWN_DAYS) -> bool:
        key = f"{name.strip().lower()}|{company.strip().lower()}"
        entry = self._data["contacts"].get(key)
        if entry is None:
            return False
        last = datetime.fromisoformat(entry["last_contacted"])
        return (datetime.now() - last).days < days

    def is_duplicate_company(self, company: str, days: int = 30) -> bool:
        key = company.strip().lower()
        entry = self._data["companies"].get(key)
        if entry is None:
            return False
        last = datetime.fromisoformat(entry["last_contacted"])
        return (datetime.now() - last).days < days

    def mark_contacted(self, name: str, company: str, email_draft: str = "") -> None:
        now = datetime.now().isoformat()
        person_key = f"{name.strip().lower()}|{company.strip().lower()}"
        company_key = company.strip().lower()
        self._data["contacts"][person_key] = {
            "name": name.strip(),
            "company": company.strip(),
            "last_contacted": now,
            "email_draft": email_draft,
        }
        self._data["companies"][company_key] = {
            "company": company.strip(),
            "last_contacted": now,
        }
        self.save()

    def get_stats(self) -> Dict[str, int]:
        return {
            "total_contacts": len(self._data["contacts"]),
            "total_companies": len(self._data["companies"]),
        }


# ═══════════════════════════════════════════════════════════════
#  LEAD SCORING
# ═══════════════════════════════════════════════════════════════


def score_lead(lead: Dict[str, str], weights: Optional[ScoringWeights] = None) -> Tuple[float, Dict[str, float]]:
    """
    Compute a lead score (0-100) and return both the total and the breakdown.
    """
    from src.config import ScoringWeights
    w = weights or DEFAULT_WEIGHTS

    # Technology match (0-30)
    tech_found = _detect_technologies(
        f"{lead.get('Job Title', '')} {lead.get('Technology Stack', '')} {lead.get('Job Posting URL', '')}"
    )
    tech_score = min(30.0, len(tech_found) * 6.0)

    # Hiring activity (0-20)
    signals = _detect_hiring_signals(
        f"{lead.get('Job Posting URL', '')} {lead.get('notes', '')} {lead.get('Job Title', '')}"
    )
    hiring_score = min(20.0, len(signals) * 5.0)

    # Company size (0-10)
    size_score = _company_size_score(lead.get("Company Size", ""))

    # Industry relevance (0-10)
    industry_score = _industry_relevance(lead.get("Industry", ""))

    # Decision-maker seniority (0-15)
    seniority_score = _seniority_score(lead.get("Job Title", ""))

    # Growth indicators (0-10) — estimate from hiring frequency if available
    growth_score = 5.0  # neutral default

    # Consulting likelihood (0-5)
    consulting_likelihood = 3.0  # neutral default

    breakdown = {
        "technology_match": tech_score,
        "hiring_activity": hiring_score,
        "company_size": size_score,
        "industry_relevance": industry_score,
        "decision_maker_seniority": seniority_score,
        "growth_indicators": growth_score,
        "consulting_likelihood": consulting_likelihood,
    }

    total = sum(breakdown.values())
    return round(min(total, 100), 1), breakdown


# ═══════════════════════════════════════════════════════════════
#  EMAIL GENERATION
# ═══════════════════════════════════════════════════════════════


def generate_email(lead: Dict[str, str]) -> str:
    """
    Generate a personalised outreach email draft for a qualified lead.
    Never fabricate facts — only use information provided in the lead dict.
    """
    contact_name = lead.get("Contact Name", "there")
    company = lead.get("Company Name", "your company")
    job_title = lead.get("Job Title", "")
    tech_stack = lead.get("Technology Stack", "")
    industry = lead.get("Industry", "")
    hiring_info = lead.get("Hiring Status", "")

    # Build personalisation tokens
    first_name = contact_name.split()[0] if contact_name != "there" else "there"
    tech_mention = f" regarding your work with {tech_stack}" if tech_stack else ""
    hiring_mention = (
        f" I noticed that {company} is actively hiring for {job_title} roles{tech_mention}."
        if hiring_info and job_title
        else f" I noticed that {company} appears to be expanding its team{tech_mention}."
    )

    services_bullets = "\n".join(f"  • {s}" for s in SERVICES_OFFERED)

    email = f"""Subject: Potential collaboration — {COMPANY_NAME} x {company}

Dear {first_name},

I hope this message finds you well.{hiring_mention}

{COMPANY_NAME} is {COMPANY_DESCRIPTION}. We have {RELEVANT_EXPERIENCE}.

Our services include:
{services_bullets}

I believe we could add significant value to {company}'s current initiatives, particularly
given your focus on {tech_stack or industry or "technology-driven solutions"}.

Would you be open to a brief 15-minute call next week to discuss how we might support
your team's goals?

Looking forward to hearing from you.

Best regards,
{SENDER_NAME}
{SENDER_TITLE} | {COMPANY_NAME}
Email: {SENDER_EMAIL}
"""
    return email


# ═══════════════════════════════════════════════════════════════
#  EML FILE GENERATION  (Outlook-compatible email files)
# ═══════════════════════════════════════════════════════════════


def generate_lead_eml(lead: Dict[str, Any], output_dir: str) -> str:
    """
    Create a .eml file for a single qualified lead — ready to open in Outlook and send.
    Returns the path to the generated .eml file.
    """
    _ensure_dirs()
    contact_name = lead.get("Contact Name", "there")
    company = lead.get("Company Name", "your company")
    email_body = lead.get("email_draft", "")

    # Build proper MIME message
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    msg["To"] = f"{contact_name} <{contact_name}@example.com>"  # placeholder — real email needed
    msg["Subject"] = f"Potential collaboration — {COMPANY_NAME} x {company}"
    msg["X-Mailer"] = "LinkedIn SDR Agent v1.0"

    # Plain text version
    text_part = MIMEText(email_body, "plain", "utf-8")
    msg.attach(text_part)

    # HTML version (with minimal formatting)
    html_body = email_body.replace("\n", "<br>\n")
    html = f"""<html><body style="font-family: Calibri, Arial, sans-serif; font-size: 11pt;">
{html_body}
</body></html>"""
    html_part = MIMEText(html, "html", "utf-8")
    msg.attach(html_part)

    # Sanitise filename
    safe_company = re.sub(r"[^\w\s-]", "", company).strip().replace(" ", "_")[:30]
    safe_contact = re.sub(r"[^\w\s-]", "", contact_name).strip().replace(" ", "_")[:20]
    filename = f"lead_{safe_company}_{safe_contact}.eml"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "wb") as fh:
        fh.write(msg.as_bytes())

    return filepath


def generate_approval_digest(
    qualified: List[Dict[str, Any]],
    rejected: List[Dict[str, Any]],
    output_dir: str,
) -> str:
    """
    Create a single .eml approval digest sent to the user's approval email address.
    Contains a summary of all qualified leads with their email drafts.
    Returns the path to the generated .eml file.
    """
    _ensure_dirs()
    today = _today_str()

    # Build the digest body
    lines = []
    lines.append(f"DAILY LINKEDIN LEAD APPROVAL — {today}")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Total qualified leads: {len(qualified)}")
    lines.append(f"Total rejected leads: {len(rejected)}")
    lines.append("")
    lines.append(f"Please review each lead below. Reply with 'APPROVE' to approve all,")
    lines.append(f"or specify lead numbers to approve individually.")
    lines.append("")
    lines.append("—" * 60)

    for i, lead in enumerate(qualified, 1):
        company = lead.get("Company Name", "?")
        contact = lead.get("Contact Name", "?")
        role = lead.get("Job Title", "?")
        score = lead.get("score", 0)
        reason = lead.get("qualification_reason", "")
        industry = lead.get("Industry", "?")
        country = lead.get("Country", "?")
        tech = lead.get("Technology Stack", "?")

        lines.append("")
        lines.append(f"LEAD #{i}")
        lines.append(f"  Company:     {company}")
        lines.append(f"  Contact:     {contact}")
        lines.append(f"  Role:        {role}")
        lines.append(f"  Score:       {score}/100")
        lines.append(f"  Industry:    {industry}")
        lines.append(f"  Country:     {country}")
        lines.append(f"  Tech Stack:  {tech}")
        lines.append(f"  Reason:      {reason}")
        lines.append("")
        lines.append("  EMAIL DRAFT:")
        lines.append("  " + "-" * 56)
        email_lines = lead.get("email_draft", "").split("\n")
        for el in email_lines:
            lines.append(f"  {el}")
        lines.append("  " + "-" * 56)
        lines.append(f"  APPROVE LEAD #{i} by replying with: APPROVE {i}")
        lines.append("")
        lines.append("—" * 60)

    if rejected:
        lines.append("")
        lines.append("REJECTED LEADS (for reference):")
        for r in rejected:
            lines.append(f"  • {r.get('Company Name', '?')} — {r.get('rejection_reason', 'No reason')}")

    lines.append("")
    lines.append("=" * 60)
    lines.append("END OF APPROVAL DIGEST")

    body_text = "\n".join(lines)

    # Build MIME message
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    msg["To"] = f"<{APPROVAL_EMAIL}>"
    msg["Subject"] = f"Daily LinkedIn Lead Approval — {today}"
    msg["X-Mailer"] = "LinkedIn SDR Agent v1.0"
    msg["X-Approval-Digest"] = today

    text_part = MIMEText(body_text, "plain", "utf-8")
    msg.attach(text_part)

    html_body = body_text.replace("\n", "<br>\n")
    html = f"""<html><body style="font-family: Consolas, monospace; font-size: 10pt;">
{html_body}
</body></html>"""
    html_part = MIMEText(html, "html", "utf-8")
    msg.attach(html_part)

    filename = f"approval_digest_{today}.eml"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "wb") as fh:
        fh.write(msg.as_bytes())

    print(f"  Approval digest: {filepath}")
    return filepath


# ═══════════════════════════════════════════════════════════════
#  REPORT GENERATION
# ═══════════════════════════════════════════════════════════════


def _format_score_class(score: float) -> str:
    if score >= 85:
        return "HOT"
    if score >= 75:
        return "WARM"
    return "QUALIFIED"


def generate_excel_report(
    leads: List[Dict[str, Any]],
    output_path: str,
    history: Optional[LeadHistory] = None,
) -> str:
    """Generate a formatted Excel report with all qualified leads."""
    _ensure_dirs()

    records = []
    for lead in leads:
        techs = "; ".join(_detect_technologies(
            f"{lead.get('Job Title', '')} {lead.get('Technology Stack', '')} "
            f"{lead.get('Job Posting URL', '')}"
        ))
        signals = "; ".join(_detect_hiring_signals(
            f"{lead.get('Job Title', '')} {lead.get('Job Posting URL', '')}"
        ))
        is_dup_person = history.is_duplicate_person(
            lead.get("Contact Name", ""), lead.get("Company Name", "")
        ) if history else False
        is_dup_company = history.is_duplicate_company(
            lead.get("Company Name", "")
        ) if history else False

        records.append({
            "Lead Score": lead.get("score", 0),
            "Priority": _format_score_class(lead.get("score", 0)),
            "Company Name": lead.get("Company Name", ""),
            "Contact Name": lead.get("Contact Name", ""),
            "Job Title": lead.get("Job Title", ""),
            "LinkedIn Profile": lead.get("LinkedIn Profile", ""),
            "Company LinkedIn": lead.get("Company LinkedIn", ""),
            "Company Website": lead.get("Company Website", ""),
            "Industry": lead.get("Industry", ""),
            "Company Size": lead.get("Company Size", ""),
            "Country": lead.get("Country", ""),
            "City": lead.get("City", ""),
            "Technology Stack": techs,
            "Hiring Signals": signals,
            "Job Posting URL": lead.get("Job Posting URL", ""),
            "Job Posted Date": lead.get("Job Posted Date", ""),
            "Customer Status": lead.get("customer_status", "Unknown"),
            "Email Draft Status": lead.get("email_status", "Drafted"),
            "Approval Status": lead.get("approval_status", "Pending"),
            "Email Draft": lead.get("email_draft", ""),
            "Qualification Reason": lead.get("qualification_reason", ""),
            "Duplicate Person": "YES" if is_dup_person else "",
            "Duplicate Company": "YES" if is_dup_company else "",
            "Next Action": lead.get("next_action", "Awaiting Approval"),
        })

    df = pd.DataFrame(records)
    df.to_excel(output_path, index=False, sheet_name="Qualified Leads")
    return output_path


def generate_pdf_report(
    leads: List[Dict[str, Any]],
    rejected: List[Dict[str, Any]],
    output_path: str,
) -> str:
    """Generate a formatted PDF report with summary, qualified leads, and stats."""
    _ensure_dirs()
    today = _today_str()
    qualified = [l for l in leads if l.get("score", 0) >= 70]

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "LinkedIn SDR Agent - Daily Lead Report", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 8, f"Date: {today}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(8)

    # Summary box
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 10, "Summary", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, f"Total leads processed: {len(leads)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 7, f"Qualified (score >= 70): {len(qualified)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 7, f"Rejected: {len(rejected)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(6)

    # Aggregate stats
    tech_counter: Dict[str, int] = {}
    industry_counter: Dict[str, int] = {}
    location_counter: Dict[str, int] = {}
    for l in leads:
        techs = _detect_technologies(
            f"{l.get('Job Title', '')} {l.get('Technology Stack', '')} {l.get('Job Posting URL', '')}"
        )
        for t in techs:
            tech_counter[t] = tech_counter.get(t, 0) + 1
        ind = l.get("Industry", "Unknown").strip()
        if ind:
            industry_counter[ind] = industry_counter.get(ind, 0) + 1
        loc = f"{l.get('City', '')}, {l.get('Country', '')}".strip(", ")
        if loc and loc != ",":
            location_counter[loc] = location_counter.get(loc, 0) + 1

    top_techs = sorted(tech_counter.items(), key=lambda x: -x[1])[:5]
    top_industries = sorted(industry_counter.items(), key=lambda x: -x[1])[:5]
    top_locations = sorted(location_counter.items(), key=lambda x: -x[1])[:5]

    if top_techs:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 9, "Top Technologies", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 10)
        for t, c in top_techs:
            pdf.cell(0, 6, f"  {t}: {c}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(4)

    if top_industries:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 9, "Top Industries", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 10)
        for ind, c in top_industries:
            pdf.cell(0, 6, f"  {ind}: {c}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(4)

    if top_locations:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 9, "Top Locations", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 10)
        for loc, c in top_locations:
            pdf.cell(0, 6, f"  {loc}: {c}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(6)

    # Qualified leads table
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 10, "Qualified Leads", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    if qualified:
        # Table header
        col_widths = [12, 45, 40, 50]
        pdf.set_font("Helvetica", "B", 9)
        headers = ["Score", "Company", "Contact", "Role"]
        for i, h in enumerate(headers):
            pdf.cell(col_widths[i], 7, h, border=1, align="C")
        pdf.ln()

        # Table rows
        pdf.set_font("Helvetica", "", 8)
        for q in sorted(qualified, key=lambda x: -x["score"]):
            sc = str(q.get("score", 0))
            co = q.get("Company Name", "")[:22]
            cn = q.get("Contact Name", "")[:20]
            rl = q.get("Job Title", "")[:25]
            pdf.cell(col_widths[0], 6, sc, border=1, align="C")
            pdf.cell(col_widths[1], 6, co, border=1)
            pdf.cell(col_widths[2], 6, cn, border=1)
            pdf.cell(col_widths[3], 6, rl, border=1)
            pdf.ln()

    pdf.output(output_path)
    return output_path


def generate_daily_summary(
    leads: List[Dict[str, Any]],
    rejected: List[Dict[str, Any]],
    output_path: str,
) -> str:
    """Generate a human-readable daily summary text file."""
    _ensure_dirs()

    today = _today_str()
    qualified = [l for l in leads if l.get("score", 0) >= 70]
    scored_below = [l for l in leads if l.get("score", 0) < 70]

    # Aggregate tech and industry stats
    tech_counter: Dict[str, int] = {}
    industry_counter: Dict[str, int] = {}
    location_counter: Dict[str, int] = {}

    for l in leads:
        techs = _detect_technologies(
            f"{l.get('Job Title', '')} {l.get('Technology Stack', '')} {l.get('Job Posting URL', '')}"
        )
        for t in techs:
            tech_counter[t] = tech_counter.get(t, 0) + 1
        ind = l.get("Industry", "Unknown").strip()
        if ind:
            industry_counter[ind] = industry_counter.get(ind, 0) + 1
        loc = f"{l.get('City', '')}, {l.get('Country', '')}".strip(", ")
        if loc and loc != ",":
            location_counter[loc] = location_counter.get(loc, 0) + 1

    top_techs = sorted(tech_counter.items(), key=lambda x: -x[1])[:5]
    top_industries = sorted(industry_counter.items(), key=lambda x: -x[1])[:5]
    top_locations = sorted(location_counter.items(), key=lambda x: -x[1])[:5]

    lines = [
        f"{'='*60}",
        f"  DAILY SDR LEAD REPORT — {today}",
        f"{'='*60}",
        "",
        f"  Generated:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"  Total Leads Processed:  {len(leads)}",
        f"  Qualified (score >= 70): {len(qualified)}",
        f"  Below Threshold:        {len(scored_below)}",
        f"  Rejected:               {len(rejected)}",
        "",
        f"{'─'*60}",
        "  QUALIFIED LEADS",
        f"{'─'*60}",
    ]

    for i, lead in enumerate(qualified, 1):
        cname = lead.get('Company Name', '?')
        contact = lead.get('Contact Name', '?')
        score = lead.get('score', 0)
        role = lead.get('Job Title', '?')
        tech_text = f"{lead.get('Job Title', '')} {lead.get('Technology Stack', '')}"
        techs_found = _detect_technologies(tech_text)
        lines.append(f"\n  {i}. {cname} — {contact}")
        lines.append(f"     Score: {score} | Role: {role}")
        lines.append(f"     Tech: {techs_found}")

    lines.extend([
        "",
        f"{'─'*60}",
        "  TOP HIRING TECHNOLOGIES",
        f"{'─'*60}",
    ])
    for tech, count in top_techs:
        lines.append(f"  {tech}: {count}")

    lines.extend([
        "",
        f"{'─'*60}",
        "  TOP INDUSTRIES",
        f"{'─'*60}",
    ])
    for ind, count in top_industries:
        lines.append(f"  {ind}: {count}")

    lines.extend([
        "",
        f"{'─'*60}",
        "  TOP LOCATIONS",
        f"{'─'*60}",
    ])
    for loc, count in top_locations:
        lines.append(f"  {loc}: {count}")

    if rejected:
        lines.extend([
            "",
            f"{'─'*60}",
            "  REJECTED LEADS",
            f"{'─'*60}",
        ])
        for r in rejected:
            lines.append(f"  • {r.get('Company Name', '?')} — {r.get('rejection_reason', 'No reason')}")

    lines.append(f"\n{'='*60}")
    lines.append(f"  END OF REPORT")
    lines.append(f"{'='*60}")

    text = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return output_path


# ═══════════════════════════════════════════════════════════════
#  DASHBOARD JSON EXPORT
# ═══════════════════════════════════════════════════════════════


def export_dashboard_json(
    qualified: List[Dict[str, Any]],
    rejected: List[Dict[str, Any]],
    output_dir: str = OUTPUT_DIR,
) -> str:
    """Export all leads data as JSON for the live dashboard to consume."""
    _ensure_dirs()
    today = _today_str()

    # Aggregate stats
    tech_counter: Dict[str, int] = {}
    industry_counter: Dict[str, int] = {}
    location_counter: Dict[str, int] = {}
    score_ranges = {"hot": 0, "warm": 0, "qualified": 0}

    all_leads = qualified + rejected

    for l in all_leads:
        techs = _detect_technologies(
            f"{l.get('Job Title', '')} {l.get('Technology Stack', '')} {l.get('Job Posting URL', '')}"
        )
        for t in techs:
            tech_counter[t] = tech_counter.get(t, 0) + 1
        ind = l.get("Industry", "Unknown").strip()
        if ind:
            industry_counter[ind] = industry_counter.get(ind, 0) + 1
        loc = f"{l.get('City', '')}, {l.get('Country', '')}".strip(", ")
        if loc and loc != ",":
            location_counter[loc] = location_counter.get(loc, 0) + 1

        sc = l.get("score", 0)
        if sc >= 85:
            score_ranges["hot"] += 1
        elif sc >= 75:
            score_ranges["warm"] += 1
        else:
            score_ranges["qualified"] += 1

    # Build clean lead records (no HTML, no giant email bodies)
    leads_clean = []
    for q in sorted(qualified, key=lambda x: -x["score"]):
        leads_clean.append({
            "score": q.get("score", 0),
            "priority": _format_score_class(q.get("score", 0)),
            "company": q.get("Company Name", ""),
            "contact": q.get("Contact Name", ""),
            "title": q.get("Job Title", ""),
            "linkedin_profile": q.get("LinkedIn Profile", ""),
            "company_linkedin": q.get("Company LinkedIn", ""),
            "website": q.get("Company Website", ""),
            "industry": q.get("Industry", ""),
            "company_size": q.get("Company Size", ""),
            "country": q.get("Country", ""),
            "city": q.get("City", ""),
            "tech_stack": _detect_technologies(
                f"{q.get('Job Title', '')} {q.get('Technology Stack', '')} {q.get('Job Posting URL', '')}"
            ),
            "hiring_signals": _detect_hiring_signals(
                f"{q.get('Job Title', '')} {q.get('Job Posting URL', '')}"
            ),
            "job_url": q.get("Job Posting URL", ""),
            "job_date": q.get("Job Posted Date", ""),
            "customer_status": q.get("customer_status", "Unknown"),
            "email_status": q.get("email_status", "Drafted"),
            "approval_status": q.get("approval_status", "Pending"),
            "reason": q.get("qualification_reason", ""),
            "score_breakdown": q.get("score_breakdown", {}),
        })

    rejected_clean = []
    for r in rejected:
        rejected_clean.append({
            "score": r.get("score", 0),
            "company": r.get("Company Name", ""),
            "contact": r.get("Contact Name", ""),
            "title": r.get("Job Title", ""),
            "reason": r.get("rejection_reason", ""),
        })

    dashboard_data = {
        "generated_at": datetime.now().isoformat(),
        "date": today,
        "summary": {
            "total_leads": len(all_leads),
            "qualified": len(qualified),
            "rejected": len(rejected),
            "score_ranges": score_ranges,
            "top_technologies": [
                {"name": t, "count": c}
                for t, c in sorted(tech_counter.items(), key=lambda x: -x[1])[:10]
            ],
            "top_industries": [
                {"name": ind, "count": c}
                for ind, c in sorted(industry_counter.items(), key=lambda x: -x[1])[:10]
            ],
            "top_locations": [
                {"name": loc, "count": c}
                for loc, c in sorted(location_counter.items(), key=lambda x: -x[1])[:10]
            ],
        },
        "qualified_leads": leads_clean,
        "rejected_leads": rejected_clean,
    }

    json_path = os.path.join(output_dir, f"dashboard_data_{today}.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(dashboard_data, fh, indent=2, default=str)

    print(f"  Dashboard data:    {json_path}")
    return json_path


# ═══════════════════════════════════════════════════════════════
#  MAIN PROCESSING PIPELINE
# ═══════════════════════════════════════════════════════════════


def process_input_csv(
    input_path: str,
    min_score: float = 70.0,
    history: Optional[LeadHistory] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], LeadHistory]:
    """
    Read a CSV file of raw leads, score each one, generate emails for qualified leads,
    and return (qualified_leads, rejected_leads, history).
    """
    _ensure_dirs()
    history = history or LeadHistory()

    if not os.path.exists(input_path):
        print(f"[ERROR] Input file not found: {input_path}")
        print(f"        Create a CSV at this path with columns matching the template.")
        sys.exit(1)

    df = pd.read_csv(input_path)
    required = ["Company Name", "Contact Name", "Job Title", "LinkedIn Profile",
                 "Industry", "Company Size", "Country", "City"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"[ERROR] Missing required columns: {missing}")
        print(f"        Use the template at {TEMPLATES_DIR}/leads_input_template.csv")
        sys.exit(1)

    leads = df.to_dict(orient="records")
    qualified = []
    rejected = []

    for lead in leads:
        # Fill defaults
        for col in required + ["Company LinkedIn", "Company Website", "Technology Stack",
                                 "Job Posting URL", "Job Posted Date"]:
            if col not in lead or pd.isna(lead.get(col)):
                lead[col] = ""

        # Score
        total_score, breakdown = score_lead(lead)
        lead["score"] = total_score
        lead["score_breakdown"] = breakdown

        # Duplicate check
        is_dup_person = history.is_duplicate_person(
            lead.get("Contact Name", ""), lead.get("Company Name", "")
        )
        is_dup_company = history.is_duplicate_company(
            lead.get("Company Name", "")
        )

        # Customer classification (stub — replace with real CRM integration)
        lead["customer_status"] = "New Prospect"

        if is_dup_person:
            lead["rejection_reason"] = f"Duplicate person (contacted within {DUPLICATE_COOLDOWN_DAYS} days)"
            rejected.append(lead)
            continue

        if total_score < min_score:
            lead["rejection_reason"] = f"Score {total_score} below threshold {min_score}"
            rejected.append(lead)
            continue

        # Generate email draft
        email = generate_email(lead)
        lead["email_draft"] = email
        lead["email_status"] = "Drafted"
        lead["approval_status"] = "Pending"
        lead["next_action"] = "Awaiting Approval"

        # Qualification reason
        techs = _detect_technologies(
            f"{lead.get('Job Title', '')} {lead.get('Technology Stack', '')} {lead.get('Job Posting URL', '')}"
        )
        signals = _detect_hiring_signals(
            f"{lead.get('Job Title', '')} {lead.get('Job Posting URL', '')}"
        )
        reason_parts = []
        if techs:
            reason_parts.append(f"Tech match: {', '.join(techs[:3])}")
        if signals:
            reason_parts.append(f"Hiring signal: {', '.join(signals[:2])}")
        if lead.get("Industry"):
            reason_parts.append(f"Industry: {lead['Industry']}")
        lead["qualification_reason"] = "; ".join(reason_parts) or "General prospect"

        history.mark_contacted(
            lead.get("Contact Name", ""),
            lead.get("Company Name", ""),
            email,
        )
        qualified.append(lead)

    # Generate outputs
    today = _today_str()
    xlsx_path = os.path.join(OUTPUT_DIR, f"leads_{today}.xlsx")
    txt_path = os.path.join(OUTPUT_DIR, f"daily_summary_{today}.txt")
    pdf_path = os.path.join(OUTPUT_DIR, f"leads_{today}.pdf")

    generate_excel_report(qualified, xlsx_path, history)
    generate_daily_summary(qualified, rejected, txt_path)
    generate_pdf_report(qualified, rejected, pdf_path)

    # Export dashboard JSON for the live dashboard
    export_dashboard_json(qualified, rejected)

    # Generate individual .eml files for each qualified lead
    eml_dir = os.path.join(OUTPUT_DIR, f"emails_{today}")
    Path(eml_dir).mkdir(parents=True, exist_ok=True)
    eml_files = []
    for lead in qualified:
        eml_path = generate_lead_eml(lead, eml_dir)
        eml_files.append(eml_path)

    # Generate approval digest .eml
    digest_path = generate_approval_digest(qualified, rejected, OUTPUT_DIR)

    # Print summary to console
    print(f"\n{'='*60}")
    print(f"  LEAD GENERATION COMPLETE")
    print(f"{'='*60}")
    print(f"  Input file:        {input_path}")
    print(f"  Min score:         {min_score}")
    print(f"  Total leads:       {len(leads)}")
    print(f"  Qualified:         {len(qualified)}")
    print(f"  Rejected:          {len(rejected)}")
    print(f"  Excel report:      {xlsx_path}")
    print(f"  Summary:           {txt_path}")
    print(f"  Lead .eml files:   {len(eml_files)} in {eml_dir}/")
    print(f"  Approval digest:   {digest_path}")
    print(f"{'='*60}\n")

    # Show qualified leads table
    if qualified:
        print(f"{'Score':>6}  {'Company':30s}  {'Contact':20s}  {'Role':30s}")
        print("-" * 90)
        for q in sorted(qualified, key=lambda x: -x["score"]):
            print(f"{q['score']:>5.1f}  {q['Company Name']:30s}  {q['Contact Name']:20s}  {q['Job Title'][:30]:30s}")

    return qualified, rejected, history


# ═══════════════════════════════════════════════════════════════
#  CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LinkedIn SDR Agent — Lead Scoring & Outreach Engine",
    )
    parser.add_argument(
        "--input", "-i",
        help="Path to input CSV file with raw leads",
    )
    parser.add_argument(
        "--min-score", "-m",
        type=float,
        default=70.0,
        help="Minimum lead score threshold (default: 70)",
    )
    parser.add_argument(
        "--summary", "-s",
        action="store_true",
        help="Generate today's summary from existing output",
    )
    parser.add_argument(
        "--report", "-r",
        help="Path to an existing Excel report to print as text",
    )
    parser.add_argument(
        "--history-stats",
        action="store_true",
        help="Print lead history statistics",
    )
    parser.add_argument(
        "--approval", "-a",
        action="store_true",
        help="Generate approval digest .eml from today's existing output (no re-processing)",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Launch the Streamlit live dashboard",
    )
    parser.add_argument(
        "--pipeline",
        action="store_true",
        help="Run the full daily pipeline (scrape + ETL + qualify + report)",
    )
    parser.add_argument(
        "--skip-scraping",
        action="store_true",
        help="Skip scraping step in pipeline",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM qualification in pipeline",
    )

    args = parser.parse_args()

    if args.history_stats:
        h = LeadHistory()
        stats = h.get_stats()
        print(f"Lead History Statistics:")
        print(f"  Total unique contacts: {stats['total_contacts']}")
        print(f"  Total unique companies: {stats['total_companies']}")
        return

    if args.dashboard:
        print("Launching Streamlit dashboard...")
        print("Run: streamlit run app.py")
        return

    if args.pipeline:
        from pipeline.daily_run import run_pipeline
        run_pipeline(
            skip_scraping=args.skip_scraping,
            input_path=args.input,
            min_score=args.min_score,
            use_llm=not args.no_llm,
        )
        return

    if args.approval:
        today = _today_str()
        xlsx_path = os.path.join(OUTPUT_DIR, f"leads_{today}.xlsx")
        if not os.path.exists(xlsx_path):
            print(f"[ERROR] No report found for today. Run with --input first.")
            sys.exit(1)
        df = pd.read_excel(xlsx_path)
        # Build qualified/rejected lists from the Excel
        leads_list = df.to_dict(orient="records")
        qualified = []
        rejected = []
        for lead in leads_list:
            lead["score"] = lead.get("Lead Score", 0)
            lead["email_draft"] = lead.get("Email Draft", "")
            lead["qualification_reason"] = lead.get("Qualification Reason", "")
            qualified.append(lead)
        digest_path = generate_approval_digest(qualified, rejected, OUTPUT_DIR)
        print(f"Approval digest generated: {digest_path}")
        print(f"Open in Outlook by double-clicking the .eml file.")
        return

    if args.input:
        process_input_csv(args.input, args.min_score)
        return

    if args.summary:
        today = _today_str()
        txt_path = os.path.join(OUTPUT_DIR, f"daily_summary_{today}.txt")
        if os.path.exists(txt_path):
            with open(txt_path) as fh:
                print(fh.read())
        else:
            print(f"[INFO] No summary found for today. Run with --input first.")
        return

    if args.report:
        if not os.path.exists(args.report):
            print(f"[ERROR] Report not found: {args.report}")
            sys.exit(1)
        df = pd.read_excel(args.report)
        pd.set_option("display.max_columns", 20)
        pd.set_option("display.width", 120)
        print(df.to_string(index=False))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
