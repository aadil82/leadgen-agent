"""
LinkedIn SDR Agent — Enhanced Live Dashboard
=============================================
A beautiful, multi-page Streamlit dashboard for lead generation management.

Features:
  - Executive Dashboard with KPIs and charts
  - Daily Leads browser with detailed views
  - Customer Profiles with full history
  - Email Follow-up tracking and management
  - Pipeline Runner with live status

Usage:
    streamlit run app.py
"""

import csv
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

# ── Page Config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="LeadGen Agent — Command Center",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ───────────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* Main header styling */
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        color: white;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
    }
    .main-header h1 { color: white; margin: 0; font-size: 1.8rem; }
    .main-header p { color: rgba(255,255,255,0.85); margin: 0.3rem 0 0 0; font-size: 0.95rem; }

    /* KPI cards */
    .kpi-card {
        background: white;
        border-radius: 12px;
        padding: 1.2rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        border-left: 4px solid #667eea;
        transition: transform 0.2s;
    }
    .kpi-card:hover { transform: translateY(-2px); box-shadow: 0 4px 15px rgba(0,0,0,0.12); }
    .kpi-card.hot { border-left-color: #ef4444; }
    .kpi-card.warm { border-left-color: #f59e0b; }
    .kpi-card.qualified { border-left-color: #22c55e; }
    .kpi-card.rejected { border-left-color: #6b7280; }
    .kpi-card.email { border-left-color: #3b82f6; }
    .kpi-card.pipeline { border-left-color: #8b5cf6; }

    .kpi-value { font-size: 2rem; font-weight: 700; color: #1f2937; }
    .kpi-label { font-size: 0.85rem; color: #6b7280; margin-top: 0.2rem; }

    /* Status badges */
    .badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-hot { background: #fef2f2; color: #dc2626; }
    .badge-warm { background: #fffbeb; color: #d97706; }
    .badge-qualified { background: #f0fdf4; color: #16a34a; }
    .badge-sent { background: #eff6ff; color: #2563eb; }
    .badge-pending { background: #fefce8; color: #ca8a04; }
    .badge-opened { background: #f0fdf4; color: #16a34a; }
    .badge-replied { background: #faf5ff; color: #9333ea; }
    .badge-bounced { background: #fef2f2; color: #dc2626; }

    /* Lead card */
    .lead-card {
        background: white;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.75rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        border-left: 3px solid #e5e7eb;
        transition: all 0.2s;
    }
    .lead-card:hover { box-shadow: 0 3px 10px rgba(0,0,0,0.1); border-left-color: #667eea; }
    .lead-card .company { font-weight: 600; color: #1f2937; font-size: 1.05rem; }
    .lead-card .role { color: #6b7280; font-size: 0.9rem; }
    .lead-card .score { font-weight: 700; font-size: 1.1rem; }

    /* Email thread */
    .email-thread {
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 0.75rem;
        background: #fafafa;
    }
    .email-thread .subject { font-weight: 600; color: #1f2937; }
    .email-thread .date { color: #9ca3af; font-size: 0.8rem; }
    .email-thread .snippet { color: #6b7280; font-size: 0.9rem; margin-top: 0.3rem; }

    /* Sidebar styling */
    [data-testid="stSidebar"] { background: #f8fafc; }
    [data-testid="stSidebar"] .stRadio > div > label { padding: 0.4rem 0; }

    /* Tables */
    .stDataFrame { border-radius: 8px; overflow: hidden; }

    /* Section headers */
    .section-header {
        font-size: 1.1rem;
        font-weight: 600;
        color: #374151;
        margin: 1.5rem 0 0.75rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid #e5e7eb;
    }

    /* Timeline */
    .timeline-item {
        padding: 0.75rem 0 0.75rem 1.5rem;
        border-left: 2px solid #e5e7eb;
        position: relative;
        margin-left: 0.5rem;
    }
    .timeline-item::before {
        content: '';
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: #667eea;
        position: absolute;
        left: -6px;
        top: 1rem;
    }
    .timeline-item .tl-date { font-size: 0.8rem; color: #9ca3af; }
    .timeline-item .tl-action { font-size: 0.9rem; color: #374151; }
</style>
""", unsafe_allow_html=True)

# ── Constants ────────────────────────────────────────────────────────────────

OUTPUT_DIR = "data/output"
HISTORY_FILE = "data/history/leads_history.json"
FEEDBACK_FILE = "data/history/feedback.json"
EMAILS_DIR = "data/output/emails"
REFRESH_INTERVAL = 60

# ── Data Loading ─────────────────────────────────────────────────────────────


@st.cache_data(ttl=REFRESH_INTERVAL)
def find_latest_file(pattern: str, directory: str = OUTPUT_DIR) -> str | None:
    """Find the most recent file matching a pattern."""
    path = Path(directory)
    if not path.exists():
        return None
    files = sorted(path.glob(pattern), reverse=True)
    return str(files[0]) if files else None


@st.cache_data(ttl=REFRESH_INTERVAL)
def load_json(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


@st.cache_data(ttl=REFRESH_INTERVAL)
def load_excel(path: str) -> pd.DataFrame:
    try:
        df = pd.read_excel(path)
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=REFRESH_INTERVAL)
def load_history() -> dict:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as fh:
                return json.load(fh)
        except Exception:
            pass
    return {"contacts": {}, "companies": {}}


@st.cache_data(ttl=REFRESH_INTERVAL)
def load_feedback() -> dict:
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, "r") as fh:
                return json.load(fh)
        except Exception:
            pass
    return {"accepted": [], "rejected": [], "history": []}


def save_feedback(data: dict) -> None:
    Path(FEEDBACK_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(FEEDBACK_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)


def load_leads() -> tuple[list[dict], dict | None]:
    """Load leads from JSON or Excel, return (leads, summary)."""
    latest_json = find_latest_file("dashboard_data_*.json")
    if latest_json:
        data = load_json(latest_json)
        if data:
            return data.get("qualified_leads", []), data.get("summary")

    latest_xlsx = find_latest_file("leads_*.xlsx")
    if latest_xlsx:
        df = load_excel(latest_xlsx)
        if not df.empty:
            leads = []
            for _, row in df.iterrows():
                score_col = row.get("Lead Score", row.get("score", 0))
                try:
                    score = float(score_col) if score_col else 0
                except (ValueError, TypeError):
                    score = 0
                leads.append({
                    "score": score,
                    "priority": "HOT" if score >= 85 else "WARM" if score >= 75 else "QUALIFIED",
                    "company": str(row.get("Company Name", "")),
                    "contact": str(row.get("Contact Name", "")),
                    "title": str(row.get("Job Title", "")),
                    "industry": str(row.get("Industry", "")),
                    "country": str(row.get("Country", "")),
                    "city": str(row.get("City", "")),
                    "tech_stack": str(row.get("Technology Stack", "")),
                    "linkedin_profile": str(row.get("LinkedIn Profile", "")),
                    "company_website": str(row.get("Company Website", "")),
                    "approval_status": str(row.get("Approval Status", "Pending")),
                    "email_status": str(row.get("Email Draft Status", "Drafted")),
                    "reason": str(row.get("Qualification Reason", "")),
                    "email_draft": str(row.get("Email Draft", "")),
                })
            return leads, None

    return [], None


def detect_techs(text: str) -> list[str]:
    keywords = [
        "Python", "Java", "C#", ".NET", "Node.js", "TypeScript", "Go", "Rust",
        "AWS", "Azure", "GCP", "Kubernetes", "Docker", "Terraform", "DevOps",
        "SQL", "PostgreSQL", "MySQL", "Snowflake", "MongoDB", "Databricks",
        "AI", "Machine Learning", "ML", "GenAI", "LLM", "OpenAI",
        "React", "Angular", "Vue.js", "Django", "FastAPI", "Spring Boot",
        "Salesforce", "SAP", "Power BI", "Tableau", "E-Commerce", "POS",
    ]
    text_lower = text.lower()
    return list(set(kw for kw in keywords if kw.lower() in text_lower))


# ── Sidebar Navigation ───────────────────────────────────────────────────────

def render_sidebar():
    st.sidebar.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 1rem; border-radius: 10px; margin-bottom: 1rem;">
        <h2 style="color: white; margin: 0; font-size: 1.3rem;">🎯 LeadGen Agent</h2>
        <p style="color: rgba(255,255,255,0.8); margin: 0.2rem 0 0 0; font-size: 0.8rem;">Command Center v2.0</p>
    </div>
    """, unsafe_allow_html=True)

    page = st.sidebar.radio(
        "Navigate",
        ["📊 Executive Dashboard", "📋 Daily Leads", "👤 Customer Details",
         "📧 Email Follow-ups", "🚀 Pipeline Runner"],
        label_visibility="collapsed",
    )

    st.sidebar.divider()
    st.sidebar.caption(f"⏱️ Auto-refresh: {REFRESH_INTERVAL}s")
    if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    # Quick stats in sidebar
    leads, _ = load_leads()
    if leads:
        st.sidebar.divider()
        st.sidebar.markdown("**📈 Quick Stats**")
        qualified = [l for l in leads if l.get("score", 0) >= 70]
        st.sidebar.metric("Qualified", len(qualified))
        st.sidebar.metric("Hot Leads", len([l for l in qualified if l.get("score", 0) >= 85]))

    history = load_history()
    contacts = history.get("contacts", {})
    st.sidebar.metric("Contacts Tracked", len(contacts))

    return page


# ── Page: Executive Dashboard ────────────────────────────────────────────────

def page_dashboard():
    leads, summary = load_leads()

    # Header
    st.markdown("""
    <div class="main-header">
        <h1>📊 Executive Dashboard</h1>
        <p>Real-time lead generation overview and pipeline analytics</p>
    </div>
    """, unsafe_allow_html=True)

    if not leads:
        st.warning("⚠️ No lead data found. Run the pipeline first or upload a CSV.")
        return

    qualified = [l for l in leads if l.get("score", 0) >= 70]
    rejected = [l for l in leads if l.get("score", 0) < 70]
    hot = [l for l in qualified if l.get("score", 0) >= 85]
    warm = [l for l in qualified if 75 <= l.get("score", 0) < 85]

    # KPI Cards
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    kpi_data = [
        ("🎯", "Total Leads", len(leads), ""),
        ("🔥", "Hot Leads", len(hot), "hot"),
        ("⭐", "Warm Leads", len(warm), "warm"),
        ("✅", "Qualified", len(qualified), "qualified"),
        ("📧", "Emails Drafted", len([l for l in qualified if l.get("email_status") == "Drafted"]), "email"),
        ("❌", "Rejected", len(rejected), "rejected"),
    ]
    for col, (icon, label, value, css_class) in zip([col1, col2, col3, col4, col5, col6], kpi_data):
        with col:
            st.markdown(f"""
            <div class="kpi-card {css_class}">
                <div class="kpi-value">{icon} {value}</div>
                <div class="kpi-label">{label}</div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    # Charts Row
    col_left, col_right = st.columns([3, 2])
    with col_left:
        st.markdown('<div class="section-header">📊 Lead Score Distribution</div>', unsafe_allow_html=True)
        df_chart = pd.DataFrame(qualified) if qualified else pd.DataFrame({"score": [0], "company": ["No data"]})
        if not df_chart.empty and "score" in df_chart.columns:
            df_sorted = df_chart.sort_values("score", ascending=True)
            st.bar_chart(df_sorted.set_index("company")["score"], height=350)

    with col_right:
        st.markdown('<div class="section-header">💻 Top Technologies</div>', unsafe_allow_html=True)
        tech_counter = {}
        for l in leads:
            techs = detect_techs(f"{l.get('title', '')} {l.get('tech_stack', '')}")
            for t in techs:
                tech_counter[t] = tech_counter.get(t, 0) + 1
        if tech_counter:
            tech_df = pd.DataFrame(
                sorted(tech_counter.items(), key=lambda x: -x[1])[:10],
                columns=["Technology", "Count"]
            ).sort_values("Count", ascending=True)
            import plotly.express as px
            fig = px.bar(tech_df, x="Count", y="Technology", orientation="h",
                        text="Count", color="Count", color_continuous_scale="blues")
            fig.update_traces(textposition="outside")
            fig.update_layout(height=350, showlegend=False, margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)

    # Pie Charts
    col_pie1, col_pie2, col_pie3 = st.columns(3)
    with col_pie1:
        st.markdown('<div class="section-header">🎯 Priority Mix</div>', unsafe_allow_html=True)
        import plotly.express as px
        priority_data = pd.DataFrame({
            "Priority": ["🔥 Hot", "⭐ Warm", "✅ Qualified"],
            "Count": [len(hot), len(warm), len(qualified) - len(hot) - len(warm)],
        })
        fig = px.pie(priority_data, names="Priority", values="Count",
                    color_discrete_sequence=["#ef4444", "#f59e0b", "#22c55e"], hole=0.4)
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(showlegend=False, height=280, margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)

    with col_pie2:
        st.markdown('<div class="section-header">🏢 Industry Split</div>', unsafe_allow_html=True)
        ind_counter = {}
        for l in leads:
            ind = l.get("industry", "Unknown")
            if ind:
                ind_counter[ind] = ind_counter.get(ind, 0) + 1
        if ind_counter:
            ind_df = pd.DataFrame(sorted(ind_counter.items(), key=lambda x: -x[1])[:8], columns=["Industry", "Count"])
            fig = px.pie(ind_df, names="Industry", values="Count",
                        color_discrete_sequence=px.colors.qualitative.Set2, hole=0.4)
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(showlegend=False, height=280, margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)

    with col_pie3:
        st.markdown('<div class="section-header">🌍 Geography</div>', unsafe_allow_html=True)
        country_counter = {}
        for l in leads:
            c = l.get("country", "Unknown")
            if c:
                country_counter[c] = country_counter.get(c, 0) + 1
        if country_counter:
            geo_df = pd.DataFrame(sorted(country_counter.items(), key=lambda x: -x[1])[:8], columns=["Country", "Count"])
            fig = px.pie(geo_df, names="Country", values="Count",
                        color_discrete_sequence=px.colors.qualitative.Pastel, hole=0.4)
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(showlegend=False, height=280, margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)

    # Recent Hot Leads
    st.divider()
    st.markdown('<div class="section-header">🔥 Top Hot Leads</div>', unsafe_allow_html=True)
    for lead in hot[:5]:
        score = lead.get("score", 0)
        st.markdown(f"""
        <div class="lead-card" style="border-left-color: #ef4444;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span class="company">{lead.get('company', '?')}</span>
                    <span class="role"> — {lead.get('title', '?')}</span>
                </div>
                <span class="score" style="color: #ef4444;">{score:.0f}</span>
            </div>
            <div style="font-size: 0.85rem; color: #6b7280; margin-top: 0.3rem;">
                {lead.get('industry', '')} · {lead.get('country', '')} · {lead.get('tech_stack', '')[:80]}
            </div>
        </div>
        """, unsafe_allow_html=True)


# ── Page: Daily Leads ────────────────────────────────────────────────────────

def page_daily_leads():
    leads, _ = load_leads()

    st.markdown("""
    <div class="main-header">
        <h1>📋 Daily Leads</h1>
        <p>Browse and manage all qualified leads with filters and search</p>
    </div>
    """, unsafe_allow_html=True)

    if not leads:
        st.warning("No leads found.")
        return

    # Filters
    fcol1, fcol2, fcol3, fcol4 = st.columns(4)
    with fcol1:
        priority_filter = st.multiselect("Priority", ["HOT", "WARM", "QUALIFIED"], default=[])
    with fcol2:
        industry_options = sorted(set(l.get("industry", "") for l in leads if l.get("industry")))
        industry_filter = st.multiselect("Industry", industry_options, default=[])
    with fcol3:
        country_options = sorted(set(l.get("country", "") for l in leads if l.get("country")))
        country_filter = st.multiselect("Country", country_options, default=[])
    with fcol4:
        search = st.text_input("🔍 Search company or contact", "")

    # Apply filters
    filtered = leads.copy()
    if priority_filter:
        filtered = [l for l in filtered if l.get("priority") in priority_filter]
    if industry_filter:
        filtered = [l for l in filtered if l.get("industry") in industry_filter]
    if country_filter:
        filtered = [l for l in filtered if l.get("country") in country_filter]
    if search:
        search_lower = search.lower()
        filtered = [l for l in filtered if search_lower in l.get("company", "").lower()
                    or search_lower in l.get("contact", "").lower()
                    or search_lower in l.get("title", "").lower()]

    st.caption(f"Showing {len(filtered)} of {len(leads)} leads")

    # Lead cards
    for i, lead in enumerate(filtered):
        score = lead.get("score", 0)
        priority = lead.get("priority", "QUALIFIED")
        border_color = "#ef4444" if priority == "HOT" else "#f59e0b" if priority == "WARM" else "#22c55e"
        badge_class = "badge-hot" if priority == "HOT" else "badge-warm" if priority == "WARM" else "badge-qualified"

        with st.expander(f"{'🔥' if priority == 'HOT' else '⭐' if priority == 'WARM' else '✅'} {lead.get('company', '?')} — {lead.get('contact', '?')} ({score:.0f})", expanded=False):
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                st.markdown(f"**Role:** {lead.get('title', 'N/A')}")
                st.markdown(f"**Industry:** {lead.get('industry', 'N/A')}")
                st.markdown(f"**Country:** {lead.get('country', 'N/A')}")
                st.markdown(f"**Tech:** {lead.get('tech_stack', 'N/A')[:100]}")
            with c2:
                st.markdown(f"**LinkedIn:** {lead.get('linkedin_profile', 'N/A')[:60]}")
                st.markdown(f"**Website:** {lead.get('company_website', 'N/A')[:60]}")
                st.markdown(f"**Reason:** {lead.get('reason', 'N/A')[:120]}")
            with c3:
                st.markdown(f'<span class="badge {badge_class}">{priority}</span>', unsafe_allow_html=True)
                st.markdown(f"**Score:** {score:.0f}/100")
                st.markdown(f"**Approval:** {lead.get('approval_status', 'Pending')}")

            # Email preview
            email_draft = lead.get("email_draft", "")
            if email_draft:
                st.divider()
                st.markdown("**📧 Email Draft:**")
                st.code(email_draft[:800] + ("..." if len(email_draft) > 800 else ""), language="text")


# ── Page: Customer Details ───────────────────────────────────────────────────

def page_customer_details():
    leads, _ = load_leads()
    history = load_history()
    feedback = load_feedback()

    st.markdown("""
    <div class="main-header">
        <h1>👤 Customer Details</h1>
        <p>Deep dive into individual customer profiles and interaction history</p>
    </div>
    """, unsafe_allow_html=True)

    if not leads:
        st.warning("No leads found.")
        return

    # Customer selector
    companies = sorted(set(l.get("company", "") for l in leads if l.get("company")))
    selected_company = st.selectbox("Select a company", ["-- All Companies --"] + companies)

    if selected_company == "-- All Companies --":
        # Show company overview table
        company_data = []
        for company in companies:
            company_leads = [l for l in leads if l.get("company") == company]
            best_lead = max(company_leads, key=lambda x: x.get("score", 0))
            company_data.append({
                "Company": company,
                "Leads": len(company_leads),
                "Best Score": best_lead.get("score", 0),
                "Industry": best_lead.get("industry", ""),
                "Country": best_lead.get("country", ""),
                "Status": best_lead.get("approval_status", "Pending"),
            })
        df = pd.DataFrame(company_data).sort_values("Best Score", ascending=False)
        st.dataframe(df, use_container_width=True, hide_index=True)
        return

    # Show selected company details
    company_leads = [l for l in leads if l.get("company") == selected_company]

    st.markdown(f'<div class="section-header">🏢 {selected_company}</div>', unsafe_allow_html=True)

    # Company info card
    best_lead = max(company_leads, key=lambda x: x.get("score", 0))
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Leads Found", len(company_leads))
    with c2:
        st.metric("Best Score", f"{best_lead.get('score', 0):.0f}")
    with c3:
        st.metric("Industry", best_lead.get("industry", "N/A"))
    with c4:
        st.metric("Country", best_lead.get("country", "N/A"))

    # Lead profiles
    st.markdown('<div class="section-header">👥 Contacts at this Company</div>', unsafe_allow_html=True)
    for lead in company_leads:
        score = lead.get("score", 0)
        st.markdown(f"""
        <div class="lead-card">
            <div style="display: flex; justify-content: space-between;">
                <div>
                    <span class="company">{lead.get('contact', 'Unknown')}</span>
                    <span class="role"> — {lead.get('title', 'N/A')}</span>
                </div>
                <span class="score">{score:.0f}</span>
            </div>
            <div style="font-size: 0.85rem; color: #6b7280; margin-top: 0.3rem;">
                Tech: {lead.get('tech_stack', 'N/A')[:80]} · Approval: {lead.get('approval_status', 'Pending')}
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Interaction timeline
    st.markdown('<div class="section-header">📅 Interaction Timeline</div>', unsafe_allow_html=True)
    contacts = history.get("contacts", {})
    company_timeline = []
    for key, data in contacts.items():
        if selected_company.lower() in key.lower():
            company_timeline.append(data)

    if company_timeline:
        for entry in sorted(company_timeline, key=lambda x: x.get("last_contacted", ""), reverse=True):
            st.markdown(f"""
            <div class="timeline-item">
                <div class="tl-date">{entry.get('last_contacted', 'Unknown')[:16]}</div>
                <div class="tl-action">📧 Contacted: {entry.get('name', 'Unknown')}</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No interaction history found for this company.")

    # Email drafts
    st.markdown('<div class="section-header">📧 Email Drafts</div>', unsafe_allow_html=True)
    for lead in company_leads:
        email = lead.get("email_draft", "")
        if email:
            st.code(email[:1000], language="text")


# ── Page: Email Follow-ups ───────────────────────────────────────────────────

def page_email_followups():
    leads, _ = load_leads()
    feedback = load_feedback()

    st.markdown("""
    <div class="main-header">
        <h1>📧 Email Follow-ups</h1>
        <p>Track email status, manage follow-ups, and monitor engagement</p>
    </div>
    """, unsafe_allow_html=True)

    if not leads:
        st.warning("No leads found.")
        return

    qualified = [l for l in leads if l.get("score", 0) >= 70]

    # Email status summary
    status_counts = {}
    for l in qualified:
        status = l.get("email_status", "Drafted")
        status_counts[status] = status_counts.get(status, 0) + 1

    ecol1, ecol2, ecol3, ecol4 = st.columns(4)
    with ecol1:
        st.markdown(f"""<div class="kpi-card email">
            <div class="kpi-value">📧 {status_counts.get('Drafted', 0)}</div>
            <div class="kpi-label">Drafted</div>
        </div>""", unsafe_allow_html=True)
    with ecol2:
        st.markdown(f"""<div class="kpi-card">
            <div class="kpi-value">📤 {status_counts.get('Sent', 0)}</div>
            <div class="kpi-label">Sent</div>
        </div>""", unsafe_allow_html=True)
    with ecol3:
        st.markdown(f"""<div class="kpi-card qualified">
            <div class="kpi-value">👀 {status_counts.get('Opened', 0)}</div>
            <div class="kpi-label">Opened</div>
        </div>""", unsafe_allow_html=True)
    with ecol4:
        st.markdown(f"""<div class="kpi-card warm">
            <div class="kpi-value">💬 {status_counts.get('Replied', 0)}</div>
            <div class="kpi-label">Replied</div>
        </div>""", unsafe_allow_html=True)

    st.divider()

    # Follow-up pipeline view
    st.markdown('<div class="section-header">📬 Follow-up Pipeline</div>', unsafe_allow_html=True)

    # Tabs for different statuses
    tab_draft, tab_sent, tab_opened, tab_replied = st.tabs(["📝 Drafts", "📤 Sent", "👀 Opened", "💬 Replied"])

    with tab_draft:
        drafted = [l for l in qualified if l.get("email_status") == "Drafted"]
        if drafted:
            for lead in drafted[:10]:
                st.markdown(f"""
                <div class="lead-card">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <span class="company">{lead.get('company', '?')}</span>
                            <span class="role"> — {lead.get('contact', '?')}</span>
                        </div>
                        <span class="badge badge-pending">Draft Ready</span>
                    </div>
                    <div style="font-size: 0.85rem; color: #6b7280; margin-top: 0.3rem;">
                        {lead.get('title', '')} · Score: {lead.get('score', 0):.0f}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No drafted emails pending.")

    with tab_sent:
        sent = [l for l in qualified if l.get("email_status") == "Sent"]
        if sent:
            for lead in sent[:10]:
                st.markdown(f"""
                <div class="lead-card">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <span class="company">{lead.get('company', '?')}</span>
                            <span class="role"> — {lead.get('contact', '?')}</span>
                        </div>
                        <span class="badge badge-sent">Sent</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No emails sent yet.")

    with tab_opened:
        st.info("No open tracking data yet. Integrate with an email service for open tracking.")

    with tab_replied:
        st.info("No reply tracking data yet. Integrate with an email service for reply tracking.")

    # Feedback history
    st.divider()
    st.markdown('<div class="section-header">📊 Feedback History</div>', unsafe_allow_html=True)
    history_entries = feedback.get("history", [])
    if history_entries:
        for entry in reversed(history_entries[-20:]):
            action = "✅ Accepted" if entry.get("accepted") else "❌ Rejected"
            st.markdown(f"""
            <div class="email-thread">
                <div style="display: flex; justify-content: space-between;">
                    <span class="subject">{entry.get('company', '?')} — {entry.get('contact', '?')}</span>
                    <span>{action}</span>
                </div>
                <div class="date">{entry.get('timestamp', '')[:16]}</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No feedback recorded yet. Use the dashboard to accept/reject leads.")

    # Approval digest
    st.divider()
    st.markdown('<div class="section-header">📬 Approval Digest</div>', unsafe_allow_html=True)
    today = datetime.now().strftime("%Y-%m-%d")
    digest_path = f"data/output/approval_digest_{today}.eml"
    if os.path.exists(digest_path):
        with open(digest_path, "r", encoding="utf-8", errors="ignore") as fh:
            content = fh.read()
        st.code(content[:3000], language="text")
        with open(digest_path, "rb") as fh:
            st.download_button("📥 Download Approval Digest (.eml)", fh, file_name=os.path.basename(digest_path))
    else:
        st.info("No approval digest for today. Run the pipeline to generate one.")


# ── Page: Pipeline Runner ────────────────────────────────────────────────────

def page_pipeline():
    st.markdown("""
    <div class="main-header">
        <h1>🚀 Pipeline Runner</h1>
        <p>Execute the full lead generation pipeline with custom options</p>
    </div>
    """, unsafe_allow_html=True)

    # Pipeline options
    pcol1, pcol2, pcol3 = st.columns(3)
    with pcol1:
        skip_scraping = st.checkbox("Skip scraping", value=False, help="Use existing data in data/raw/")
    with pcol2:
        min_score = st.slider("Min score threshold", 50, 100, 70, 5)
    with pcol3:
        use_llm = st.checkbox("Use LLM qualification", value=True, help="Requires OPENAI_API_KEY")

    input_csv = st.text_input("Input CSV path (optional)", placeholder="data/input/leads.csv")

    st.divider()

    if st.button("▶️ Run Pipeline", type="primary", use_container_width=True):
        import threading
        from io import StringIO
        from contextlib import redirect_stdout, redirect_stderr

        output_buffer = StringIO()
        error_buffer = StringIO()
        pipeline_error = [None]

        def _run():
            try:
                from pipeline.daily_run import run_pipeline
                with redirect_stdout(output_buffer), redirect_stderr(error_buffer):
                    run_pipeline(
                        skip_scraping=skip_scraping,
                        input_path=input_csv if input_csv else None,
                        min_score=float(min_score),
                        use_llm=use_llm,
                    )
            except Exception as e:
                pipeline_error[0] = e
                import traceback
                traceback.print_exc(file=error_buffer)

        with st.spinner("🔄 Running pipeline... This may take several minutes."):
            thread = threading.Thread(target=_run, daemon=True)
            thread.start()
            thread.join(timeout=600)

            stdout_text = output_buffer.getvalue()
            stderr_text = error_buffer.getvalue()

            if pipeline_error[0] is not None:
                st.error(f"❌ Pipeline failed: {pipeline_error[0]}")
                if stderr_text:
                    st.code(stderr_text[-3000:], language="text")
            elif thread.is_alive():
                st.warning("⏳ Pipeline still running (timed out after 10 min). Check back later.")
            else:
                st.success("✅ Pipeline completed successfully!")
                st.cache_data.clear()

                # Show summary
                if stdout_text:
                    with st.expander("📋 Pipeline Output", expanded=True):
                        st.code(stdout_text[-3000:], language="text")

                st.rerun()

    # Recent pipeline runs
    st.divider()
    st.markdown('<div class="section-header">📊 Recent Pipeline Runs</div>', unsafe_allow_html=True)
    summary_files = sorted(Path(OUTPUT_DIR).glob("pipeline_summary_*.json"), reverse=True)[:5]
    for sf in summary_files:
        data = load_json(str(sf))
        if data:
            st.markdown(f"""
            <div class="email-thread">
                <div style="display: flex; justify-content: space-between;">
                    <span class="subject">{data.get('date', '?')[:10]}</span>
                    <span>{data.get('qualified', 0)} qualified / {data.get('total_leads', 0)} total</span>
                </div>
                <div class="snippet">Duration: {data.get('duration_seconds', 0):.1f}s · LLM: {'Yes' if data.get('use_llm') else 'No'}</div>
            </div>
            """, unsafe_allow_html=True)


# ── Main App ─────────────────────────────────────────────────────────────────

def main():
    page = render_sidebar()

    if page == "📊 Executive Dashboard":
        page_dashboard()
    elif page == "📋 Daily Leads":
        page_daily_leads()
    elif page == "👤 Customer Details":
        page_customer_details()
    elif page == "📧 Email Follow-ups":
        page_email_followups()
    elif page == "🚀 Pipeline Runner":
        page_pipeline()

    # Footer
    st.divider()
    st.caption("🎯 LinkedIn SDR Agent v2.0 — Built with Streamlit · Plotly · GPT-4o · FAISS")


if __name__ == "__main__":
    main()
