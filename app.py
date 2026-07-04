"""
LinkedIn SDR Agent — Live Dashboard
=====================================
Self-contained Streamlit dashboard that reads lead data from the
engine's output files (Excel, JSON, or CSV).

Usage:
    streamlit run app.py
"""

import csv
import json
import os
import re
import sys
import threading
import traceback
from datetime import datetime
from io import StringIO
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr

import pandas as pd
import streamlit as st

# ── Page Config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="LinkedIn SDR Agent — Live Dashboard",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ────────────────────────────────────────────────────────────────

OUTPUT_DIR = "data/output"
HISTORY_FILE = "data/history/leads_history.json"
REFRESH_INTERVAL = 60  # seconds


# ── Data Loading ─────────────────────────────────────────────────────────────


@st.cache_data(ttl=REFRESH_INTERVAL, show_spinner="Loading latest lead data...")
def find_latest_excel() -> str | None:
    """Find the most recent Excel report in the output directory."""
    output_path = Path(OUTPUT_DIR)
    if not output_path.exists():
        return None
    xlsx_files = sorted(output_path.glob("leads_*.xlsx"), reverse=True)
    return str(xlsx_files[0]) if xlsx_files else None


@st.cache_data(ttl=REFRESH_INTERVAL, show_spinner="Loading latest lead data...")
def find_latest_summary() -> str | None:
    """Find the most recent summary text file."""
    output_path = Path(OUTPUT_DIR)
    txt_files = sorted(output_path.glob("daily_summary_*.txt"), reverse=True)
    return str(txt_files[0]) if txt_files else None


@st.cache_data(ttl=REFRESH_INTERVAL, show_spinner="Loading latest lead data...")
def find_latest_json() -> str | None:
    """Find the most recent dashboard JSON export."""
    output_path = Path(OUTPUT_DIR)
    json_files = sorted(output_path.glob("dashboard_data_*.json"), reverse=True)
    return str(json_files[0]) if json_files else None


@st.cache_data(ttl=REFRESH_INTERVAL)
def load_excel_data(filepath: str) -> pd.DataFrame:
    """Load leads from an Excel report."""
    try:
        df = pd.read_excel(filepath)
        # Normalize column names
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        print(f"  [WARN] Failed to load Excel {filepath}: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=REFRESH_INTERVAL)
def load_json_data(filepath: str) -> dict | None:
    """Load dashboard JSON data."""
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:
        print(f"  [WARN] Failed to load JSON {filepath}: {e}")
        return None


@st.cache_data(ttl=REFRESH_INTERVAL)
def load_summary_text(filepath: str) -> str:
    """Load summary text file."""
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            return fh.read()
    except Exception as e:
        print(f"  [WARN] Failed to load summary {filepath}: {e}")
        return ""


@st.cache_data(ttl=REFRESH_INTERVAL)
def load_history() -> dict:
    """Load lead history / CRM data."""
    history_path = Path(HISTORY_FILE)
    if history_path.exists():
        try:
            with open(history_path, "r") as fh:
                return json.load(fh)
        except Exception as e:
            print(f"  [WARN] Failed to load history: {e}")
    return {"contacts": {}, "companies": {}}


def detect_technologies(text: str) -> list[str]:
    """Simple tech keyword detection from text."""
    tech_keywords = [
        "Python", "Java", "C#", ".NET", "Node.js", "TypeScript", "Go", "Rust",
        "AWS", "Azure", "GCP", "Google Cloud",
        "Kubernetes", "Docker", "Terraform", "Ansible", "DevOps", "Linux",
        "SQL", "PostgreSQL", "MySQL", "Snowflake", "Oracle", "MongoDB",
        "Databricks", "Spark", "ETL", "Informatica", "Talend",
        "AI", "Machine Learning", "ML", "Generative AI", "LLM", "OpenAI",
        "React", "Angular", "Vue.js", "Full Stack",
        "Salesforce", "SAP", "Power BI", "Tableau",
        "Cyber Security", "Cloud Migration", "Data Engineering", "Data Science",
        "Spring Boot", "Django", "FastAPI", "Flask", "Microservices",
    ]
    text_lower = text.lower()
    matched = []
    for kw in tech_keywords:
        if kw.lower() in text_lower:
            matched.append(kw)
    return list(set(matched))


def format_score_class(score: float) -> str:
    if score >= 85:
        return "HOT"
    if score >= 75:
        return "WARM"
    return "QUALIFIED"


def parse_leads_from_df(df: pd.DataFrame) -> list[dict]:
    """Convert a DataFrame of leads into a list of dicts for the dashboard."""
    leads = []
    for _, row in df.iterrows():
        # Map various possible column names
        company = row.get("Company Name", row.get("company", ""))
        contact = row.get("Contact Name", row.get("contact", ""))
        title = row.get("Job Title", row.get("title", ""))
        score_col = row.get("Lead Score", row.get("score", row.get("lead_score", 0)))
        try:
            score = float(score_col) if score_col else 0
        except (ValueError, TypeError):
            score = 0
        industry = row.get("Industry", row.get("industry", ""))
        country = row.get("Country", row.get("country", ""))
        tech_stack = row.get("Technology Stack", row.get("tech_stack", ""))
        approval = row.get("Approval Status", row.get("approval_status", "Pending"))
        email_status = row.get("Email Draft Status", row.get("email_status", "Drafted"))
        reason = row.get("Qualification Reason", row.get("reason", ""))

        # Detect technologies from combined text
        tech_text = f"{title} {tech_stack}"
        detected_techs = detect_technologies(tech_text)

        leads.append({
            "score": score,
            "priority": format_score_class(score),
            "company": str(company) if company else "",
            "contact": str(contact) if contact else "",
            "title": str(title) if title else "",
            "industry": str(industry) if industry else "",
            "country": str(country) if country else "",
            "tech_stack": detected_techs,
            "approval_status": str(approval),
            "email_status": str(email_status),
            "reason": str(reason) if reason else "",
        })
    return leads


def compute_summary(leads: list[dict]) -> dict:
    """Compute summary statistics from a list of lead dicts."""
    if not leads:
        return {
            "total_leads": 0,
            "qualified": 0,
            "rejected": 0,
            "score_ranges": {"hot": 0, "warm": 0, "qualified": 0},
            "top_technologies": [],
            "top_industries": [],
        }

    tech_counter: dict[str, int] = {}
    industry_counter: dict[str, int] = {}
    score_ranges = {"hot": 0, "warm": 0, "qualified": 0}

    for l in leads:
        sc = l["score"]
        if sc >= 85:
            score_ranges["hot"] += 1
        elif sc >= 75:
            score_ranges["warm"] += 1
        else:
            score_ranges["qualified"] += 1

        for t in l.get("tech_stack", []):
            tech_counter[t] = tech_counter.get(t, 0) + 1

        ind = l.get("industry", "")
        if ind:
            industry_counter[ind] = industry_counter.get(ind, 0) + 1

    return {
        "total_leads": len(leads),
        "qualified": len([l for l in leads if l["score"] >= 70]),
        "rejected": len([l for l in leads if l["score"] < 70]),
        "score_ranges": score_ranges,
        "top_technologies": sorted(tech_counter.items(), key=lambda x: -x[1])[:10],
        "top_industries": sorted(industry_counter.items(), key=lambda x: -x[1])[:10],
    }


# ── Dashboard UI ──────────────────────────────────────────────────────────────


def render_kpi_metrics(summary: dict) -> None:
    """Render the top KPI metric cards."""
    cols = st.columns(5)
    metrics = [
        ("🎯 Total Leads", summary["total_leads"], "All leads processed"),
        ("🔥 Hot (85+)", summary["score_ranges"]["hot"], "High-priority leads"),
        ("⭐ Warm (75-84)", summary["score_ranges"]["warm"], "Moderate-priority"),
        ("✅ Qualified (70-74)", summary["score_ranges"]["qualified"], "Qualified leads"),
        ("❌ Rejected", summary["rejected"], "Below threshold"),
    ]
    for col, (label, value, help_text) in zip(cols, metrics):
        with col:
            st.metric(label=label, value=value, help=help_text)


def render_score_chart(leads: list) -> None:
    """Bar chart of lead scores."""
    if not leads:
        st.info("No qualified leads to chart.")
        return
    df = pd.DataFrame(leads)
    df = df.sort_values("score", ascending=True)

    st.subheader("📊 Lead Score Distribution")
    df_chart = df.set_index("company")["score"]
    if not df_chart.empty:
        st.bar_chart(df_chart, height=350)


def render_pie_charts(leads: list, summary: dict) -> None:
    """Priority breakdown and industry charts."""
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🎯 Priority Breakdown")
        sr = summary["score_ranges"]
        priority_data = pd.DataFrame(
            {
                "Priority": ["🔥 Hot (85+)", "⭐ Warm (75-84)", "✅ Qualified (70-74)"],
                "Count": [sr["hot"], sr["warm"], sr["qualified"]],
            }
        )
        if priority_data["Count"].sum() > 0:
            st.plotly_chart(
                _make_pie_chart(
                    priority_data, names="Priority", values="Count",
                    colors=["#ef4444", "#f59e0b", "#22c55e"],
                ),
                use_container_width=True,
            )
        else:
            st.info("No data yet.")

    with col2:
        st.subheader("🏢 Industry Breakdown")
        industries = summary.get("top_industries", [])
        if industries:
            ind_df = pd.DataFrame(industries, columns=["name", "count"])
            st.plotly_chart(
                _make_pie_chart(ind_df, names="name", values="count"),
                use_container_width=True,
            )
        else:
            st.info("No industry data yet.")


def _make_pie_chart(data: pd.DataFrame, names: str, values: str, colors: list | None = None):
    """Create a Plotly pie chart."""
    import plotly.express as px

    fig = px.pie(
        data,
        names=names,
        values=values,
        color_discrete_sequence=colors or px.colors.qualitative.Set2,
        hole=0.4,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0), height=300)
    return fig


def render_tech_chart(summary: dict) -> None:
    """Horizontal bar chart of top technologies."""
    techs = summary.get("top_technologies", [])
    if not techs:
        st.info("No technology data yet.")
        return

    st.subheader("💻 Top Hiring Technologies")
    df = pd.DataFrame(techs, columns=["name", "count"]).sort_values("count", ascending=True)
    import plotly.express as px

    fig = px.bar(
        df, x="count", y="name", orientation="h", text="count",
        color="count", color_continuous_scale="blues",
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        xaxis_title="Mentions", yaxis_title=None, showlegend=False,
        height=400, margin=dict(t=0, b=0, l=0, r=0),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_leads_table(leads: list) -> None:
    """Interactive data table with filters."""
    if not leads:
        st.info("No qualified leads to display.")
        return

    df = pd.DataFrame(leads)
    df["tech_stack"] = df["tech_stack"].apply(
        lambda x: ", ".join(x) if isinstance(x, list) else str(x)
    )

    # Filters
    st.subheader("📋 Qualified Leads")
    col1, col2, col3 = st.columns(3)

    with col1:
        priority_filter = st.multiselect(
            "Priority",
            options=sorted(df["priority"].unique()),
            default=[],
        )
    with col2:
        status_filter = st.multiselect(
            "Approval Status",
            options=sorted(df["approval_status"].unique()),
            default=[],
        )
    with col3:
        country_filter = st.multiselect(
            "Country",
            options=sorted(df["country"].unique()) if "country" in df.columns else [],
            default=[],
        )

    # Apply filters
    filtered = df.copy()
    if priority_filter:
        filtered = filtered[filtered["priority"].isin(priority_filter)]
    if status_filter:
        filtered = filtered[filtered["approval_status"].isin(status_filter)]
    if country_filter:
        filtered = filtered[filtered["country"].isin(country_filter)]

    # Search
    search = st.text_input("🔍 Search by company or contact", "")
    if search:
        mask = (
            filtered["company"].str.contains(search, case=False, na=False)
            | filtered["contact"].str.contains(search, case=False, na=False)
        )
        filtered = filtered[mask]

    # Display
    display_cols = [
        "score", "priority", "company", "contact", "title",
        "industry", "country", "tech_stack", "approval_status", "reason",
    ]
    available_cols = [c for c in display_cols if c in filtered.columns]

    st.dataframe(
        filtered[available_cols],
        use_container_width=True,
        height=min(400, 40 * len(filtered) + 40),
        column_config={
            "score": st.column_config.NumberColumn("Score", help="Lead score (0-100)"),
            "priority": st.column_config.TextColumn("Priority"),
            "company": st.column_config.TextColumn("Company"),
            "contact": st.column_config.TextColumn("Contact"),
            "title": st.column_config.TextColumn("Role"),
            "industry": st.column_config.TextColumn("Industry"),
            "country": st.column_config.TextColumn("Country"),
            "tech_stack": st.column_config.TextColumn("Technologies"),
            "approval_status": st.column_config.TextColumn("Approval"),
            "reason": st.column_config.TextColumn("Reason"),
        },
        hide_index=True,
    )

    # Download
    csv = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Download Filtered CSV",
        csv,
        f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        "text/csv",
    )


def render_history(history: dict) -> None:
    """Display lead history / CRM stats in sidebar."""
    st.sidebar.subheader("📚 Lead History")
    contacts = history.get("contacts", {})
    companies = history.get("companies", {})
    st.sidebar.metric("Total Contacts Tracked", len(contacts))
    st.sidebar.metric("Total Companies Tracked", len(companies))

    if contacts:
        st.sidebar.divider()
        st.sidebar.caption("Recent Contacts")
        recent = sorted(
            contacts.items(),
            key=lambda x: x[1].get("last_contacted", ""),
            reverse=True,
        )[:5]
        for key, data in recent:
            st.sidebar.write(f"**{data.get('name', '?')}** @ {data.get('company', '?')}")
            st.sidebar.caption(f"Contacted: {data.get('last_contacted', '?')[:10]}")


def load_feedback() -> dict:
    """Load feedback data from disk."""
    feedback_path = Path("data/history/feedback.json")
    if feedback_path.exists():
        try:
            with open(feedback_path, "r") as fh:
                return json.load(fh)
        except Exception as e:
            print(f"  [WARN] Failed to load feedback: {e}")
    return {"accepted": [], "rejected": [], "history": []}


def save_feedback(feedback: dict) -> None:
    """Save feedback data to disk."""
    feedback_path = Path("data/history/feedback.json")
    feedback_path.parent.mkdir(parents=True, exist_ok=True)
    with open(feedback_path, "w", encoding="utf-8") as fh:
        json.dump(feedback, fh, indent=2, default=str)


def render_feedback_section(leads: list) -> None:
    """Render feedback buttons for accepting/rejecting leads."""
    st.subheader("🔄 Lead Feedback")
    st.caption("Accept or reject leads to train the scoring model.")

    feedback = load_feedback()
    accepted_companies = {e["company"] for e in feedback.get("accepted", [])}
    rejected_companies = {e["company"] for e in feedback.get("rejected", [])}

    qualified = [l for l in leads if l["score"] >= 70]
    if not qualified:
        st.info("No qualified leads to provide feedback on.")
        return

    # Show feedback stats
    fcol1, fcol2, fcol3 = st.columns(3)
    with fcol1:
        st.metric("✅ Accepted", len(feedback.get("accepted", [])))
    with fcol2:
        st.metric("❌ Rejected", len(feedback.get("rejected", [])))
    with fcol3:
        total = len(feedback.get("accepted", [])) + len(feedback.get("rejected", []))
        st.metric("📊 Total Feedback", total)

    st.markdown("---")

    # Feedback form
    for i, lead in enumerate(qualified[:20]):  # limit to top 20
        company = lead.get("company", "")
        contact = lead.get("contact", "")
        score = lead.get("score", 0)

        already_accepted = company in accepted_companies
        already_rejected = company in rejected_companies
        status = "✅ Accepted" if already_accepted else ("❌ Rejected" if already_rejected else "⏳ Pending")

        col_a, col_b, col_c, col_d = st.columns([4, 1, 1, 1])
        with col_a:
            st.write(f"**{company}** — {contact} (Score: {score}) [{status}]")
        with col_b:
            if not already_accepted and not already_rejected:
                if st.button("✅ Accept", key=f"accept_{i}_{company}"):
                    entry = {
                        "timestamp": datetime.now().isoformat(),
                        "company": company,
                        "contact": contact,
                        "title": lead.get("title", ""),
                        "score": score,
                    }
                    feedback["accepted"].append(entry)
                    feedback["history"].append({**entry, "accepted": True})
                    accepted_companies.add(company)
                    save_feedback(feedback)
                    st.rerun()
            else:
                st.write("")
        with col_c:
            if not already_accepted and not already_rejected:
                if st.button("❌ Reject", key=f"reject_{i}_{company}"):
                    entry = {
                        "timestamp": datetime.now().isoformat(),
                        "company": company,
                        "contact": contact,
                        "title": lead.get("title", ""),
                        "score": score,
                    }
                    feedback["rejected"].append(entry)
                    feedback["history"].append({**entry, "accepted": False})
                    rejected_companies.add(company)
                    save_feedback(feedback)
                    st.rerun()
            else:
                st.write("")

    if len(qualified) > 20:
        st.caption(f"... and {len(qualified) - 20} more leads")


def render_pipeline_runner() -> None:
    """Render the pipeline runner controls."""
    st.subheader("🚀 Run Pipeline")
    st.caption("Run the daily lead generation pipeline from the dashboard.")

    pcol1, pcol2, pcol3 = st.columns(3)
    with pcol1:
        skip_scraping = st.checkbox("Skip scraping", value=False)
    with pcol2:
        min_score = st.slider("Min score", 50, 100, 70, 5, key="pipeline_min_score")
    with pcol3:
        use_llm = st.checkbox("Use LLM qualification", value=True)

    if st.button("▶️ Run Daily Pipeline", type="primary", use_container_width=True):
        # Capture output in a text buffer so we can display it after completion
        output_buffer = StringIO()
        error_buffer = StringIO()
        pipeline_error = [None]

        def _run_pipeline():
            try:
                from pipeline.daily_run import run_pipeline
                with redirect_stdout(output_buffer), redirect_stderr(error_buffer):
                    run_pipeline(
                        skip_scraping=skip_scraping,
                        min_score=float(min_score),
                        use_llm=use_llm,
                    )
            except Exception as e:
                pipeline_error[0] = e
                traceback.print_exc(file=error_buffer)

        with st.spinner("Running pipeline... (this may take a few minutes)"):
            try:
                thread = threading.Thread(target=_run_pipeline, daemon=True)
                thread.start()
                thread.join(timeout=600)

                stdout_text = output_buffer.getvalue()
                stderr_text = error_buffer.getvalue()

                if pipeline_error[0] is None and thread.is_alive():
                    st.warning("Pipeline is still running (timed out after 10 min). Check back later.")
                elif pipeline_error[0] is not None:
                    st.error(f"Pipeline failed: {pipeline_error[0]}")
                    if stderr_text:
                        st.code(stderr_text[-2000:], language="text")
                else:
                    st.success("Pipeline completed successfully!")
                    if stdout_text:
                        st.code(stdout_text[-2000:], language="text")
                    st.cache_data.clear()
                    st.rerun()
            except Exception as e:
                st.error(f"Error running pipeline: {e}")
                traceback.print_exc(file=error_buffer)


def render_sidebar(data_available: bool, history: dict, latest_excel: str | None) -> None:
    """Render the sidebar with controls and history."""
    st.sidebar.title("🎯 LinkedIn SDR Agent")
    st.sidebar.caption("Live Lead Generation Dashboard")

    st.sidebar.divider()
    st.sidebar.write(f"⏱️ Auto-refresh every {REFRESH_INTERVAL}s")
    if st.sidebar.button("🔄 Refresh Now"):
        st.cache_data.clear()
        st.rerun()

    if data_available and latest_excel:
        st.sidebar.divider()
        st.sidebar.caption(f"📄 **Latest data:** `{Path(latest_excel).name}`")

    st.sidebar.divider()
    st.sidebar.write("**Output files:** `data/output/`")
    st.sidebar.caption("📊 Excel reports • 📧 Approval digests (.eml)")
    st.sidebar.caption("📄 PDF reports • 📝 Text summaries")

    st.sidebar.divider()
    render_history(history)


# ── Main App ──────────────────────────────────────────────────────────────────


def main():
    # Load data
    latest_excel = find_latest_excel()
    latest_json = find_latest_json()
    latest_summary = find_latest_summary()
    history = load_history()

    # Try to load data from JSON first (richest), then Excel, then summary
    leads = []
    summary = None

    if latest_json:
        json_data = load_json_data(latest_json)
        if json_data:
            leads = json_data.get("qualified_leads", [])
            summary = json_data.get("summary", compute_summary(leads) if leads else None)

    if not leads and latest_excel:
        df = load_excel_data(latest_excel)
        if not df.empty:
            leads = parse_leads_from_df(df)
            summary = compute_summary(leads)

    # Sidebar
    render_sidebar(bool(leads), history, latest_excel)

    # Main content
    if not leads:
        st.warning(
            "⚠️ No lead data found. Please run the lead engine first:\n\n"
            "```bash\n"
            "python -m src.lead_engine --input data/input/leads_YYYY-MM-DD.csv\n"
            "```\n\n"
            "Or place an Excel report in `data/output/` with the format `leads_YYYY-MM-DD.xlsx`.\n\n"
            "**Sample data is available at:** `templates/leads_input_template.csv`"
        )

        # Show summary file if available
        if latest_summary:
            with st.expander("📝 Latest Daily Summary"):
                text = load_summary_text(latest_summary)
                st.text(text[:5000])

        return

    if not summary:
        summary = compute_summary(leads)

    # Title
    st.title("🎯 LinkedIn SDR Agent — Live Dashboard")
    qualified_count = len([l for l in leads if l["score"] >= 70])
    st.markdown(
        f"**{summary.get('date', 'Today')}** — {qualified_count} qualified leads out of "
        f"{len(leads)} total | Auto-refresh every {REFRESH_INTERVAL}s"
    )
    st.divider()

    # KPI cards
    render_kpi_metrics(summary)

    # Charts row
    st.divider()
    col1, col2 = st.columns([3, 2])
    with col1:
        qualified = [l for l in leads if l["score"] >= 70]
        render_score_chart(qualified)
    with col2:
        render_tech_chart(summary)

    # Pie charts
    st.divider()
    render_pie_charts(qualified, summary)

    # Lead table
    st.divider()
    render_leads_table(leads)

    # Rejected leads (those below 70)
    rejected = [l for l in leads if l["score"] < 70]
    if rejected:
        with st.expander(f"❌ Leads Below Threshold ({len(rejected)})"):
            rej_df = pd.DataFrame(rejected)
            st.dataframe(
                rej_df[["score", "company", "contact", "title", "reason"]],
                use_container_width=True,
                hide_index=True,
            )

    # Feedback section
    st.divider()
    render_feedback_section(leads)

    # Pipeline runner
    st.divider()
    render_pipeline_runner()

    # Footer
    st.divider()
    st.caption(
        "LinkedIn SDR Agent v2.0 — Always comply with LinkedIn ToS, GDPR, and CAN-SPAM. "
        "No emails sent without explicit human approval."
    )


if __name__ == "__main__":
    main()
