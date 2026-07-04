# 🎯 LinkedIn SDR Agent — AI-Powered Lead Generation & Outreach Engine

An autonomous B2B lead generation system that scrapes job boards, qualifies leads with GPT-4o, scores them with an ML feedback loop, generates personalized outreach emails, and delivers daily reports — all orchestrated through a single pipeline.

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DAILY PIPELINE                               │
│                                                                     │
│  ┌──────────┐   ┌──────┐   ┌──────────┐   ┌────────┐   ┌───────┐ │
│  │ SCRAPERS │──▶│ ETL  │──▶│ QUALIFY  │──▶│ SCORE  │──▶│REPORTS│ │
│  │          │   │      │   │  (LLM)   │   │  (ML)  │   │       │ │
│  │ LinkedIn │   │Clean │   │ GPT-4o   │   │Feedback│   │Excel  │ │
│  │ Google   │   │Dedup │   │Batch     │   │Learning│   │PDF    │ │
│  │ Indeed   │   │Embed │   │Qualify   │   │Online  │   │JSON   │ │
│  │ Glassdoor│   │      │   │          │   │        │   │EML    │ │
│  │ Monster  │   └──────┘   └──────────┘   └────────┘   └───────┘ │
│  └──────────┘                                                      │
│                              │                                      │
│                    ┌─────────▼──────────┐                          │
│                    │   DASHBOARD (UI)    │                          │
│                    │  Streamlit + Plotly │                          │
│                    │  KPIs / Charts /    │                          │
│                    │  Feedback / Pipeline│                          │
│                    └────────────────────┘                          │
│                              │                                      │
│                    ┌─────────▼──────────┐                          │
│                    │   DATABASE (DB)     │                          │
│                    │  PostgreSQL / JSON  │                          │
│                    │  FAISS Vector Store │                          │
│                    └────────────────────┘                          │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Scrape** — LinkedIn API, Google Custom Search, job boards pull raw job postings and company profiles
2. **ETL** — Clean, normalize, deduplicate, and generate vector embeddings
3. **Qualify** — GPT-4o evaluates each lead against target criteria (industry, tech, region, signals)
4. **Score** — ML feedback model blends rule-based + LLM scores; learns from accepted/rejected leads
5. **Report** — Generate Excel, PDF, text summary, dashboard JSON, and Outlook-compatible .eml files
6. **Dashboard** — Streamlit app with KPIs, charts, filters, feedback buttons, and pipeline runner
7. **Store** — PostgreSQL (or JSON fallback) + FAISS vector index for similarity search

## 📁 Directory Structure

```
leadgen-agent/
├── config/
│   ├── __init__.py
│   ├── settings.yaml          # All configuration (scrapers, LLM, scoring, CRM)
│   └── .env.template          # API key template (copy to .env, never commit)
│
├── scrapers/
│   ├── __init__.py
│   ├── linkedin_scraper.py    # LinkedIn API + web scraping fallback
│   ├── google_search.py       # Google Custom Search API connector
│   └── jobboard_scraper.py    # Indeed, Glassdoor, Monster scrapers
│
├── etl/
│   ├── __init__.py
│   ├── clean_transform.py     # Data cleaning, dedup, normalization, tech extraction
│   └── embeddings.py          # OpenAI embeddings, FAISS/Pinecone/in-memory stores
│
├── agents/
│   ├── __init__.py
│   ├── qualification_agent.py # GPT-4o-powered lead qualification
│   └── scoring_agent.py       # ML scoring with online feedback learning
│
├── db/
│   ├── __init__.py
│   ├── postgres_connector.py  # PostgreSQL with JSON file fallback
│   └── vector_store.py        # Re-exports from etl/embeddings.py
│
├── pipeline/
│   ├── __init__.py
│   └── daily_run.py           # Full daily pipeline orchestrator
│
├── src/
│   ├── __init__.py
│   ├── config.py              # Core constants, scoring weights, tech keywords
│   └── lead_engine.py         # Lead scoring, email generation, reports, CRM history
│
├── data/
│   ├── input/                 # Input CSVs (leads to process)
│   ├── output/                # Generated reports, JSON, .eml files
│   ├── raw/                   # Raw scraped data (JSON)
│   ├── embeddings/            # FAISS vector index
│   ├── history/               # Lead history, feedback data, pipeline logs
│   └── model/                 # Trained scoring model (pickle)
│
├── templates/
│   └── leads_input_template.csv  # Sample CSV format
│
├── app.py                     # Streamlit live dashboard (primary)
├── requirements.txt           # Python dependencies
├── .gitignore
└── README.md
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
cp config/.env.template .env
# Edit .env with your real API keys
```

Minimum required:
- `OPENAI_API_KEY` — for LLM qualification and embeddings

Optional:
- `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` — for Google search scraping
- `LINKEDIN_ACCESS_TOKEN` — for LinkedIn API access
- `DATABASE_URL` — for PostgreSQL storage

### 3. Edit Configuration

Edit `config/settings.yaml` to customize:
- Company profile and sender details
- Target industries, regions, company sizes
- Scraping queries and sources
- LLM model and scoring weights

### 4. Run the Pipeline

```bash
# Full pipeline (scrape + ETL + qualify + score + report)
python -m pipeline.daily_run

# Process existing CSV (skip scraping)
python -m pipeline.daily_run --skip-scraping --input data/input/leads.csv

# Rule-based only (no OpenAI required)
python -m pipeline.daily_run --no-llm --skip-scraping --input data/input/leads.csv
```

### 5. Launch Dashboard

```bash
streamlit run app.py
```

## 📊 Component Reference

### Scrapers (`scrapers/`)

| Module | Source | Requires |
|--------|--------|----------|
| `linkedin_scraper.py` | LinkedIn Jobs API / Web | `LINKEDIN_ACCESS_TOKEN` |
| `google_search.py` | Google Custom Search API | `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` |
| `jobboard_scraper.py` | Indeed, Glassdoor, Monster | None (web scraping) |

```bash
# Scrape LinkedIn
python -m scrapers.linkedin_scraper --query "AI engineer" --limit 50

# Search Google
python -m scrapers.google_search --query "cloud architect hiring" --limit 30

# Scrape job boards
python -m scrapers.jobboard_scraper --source indeed glassdoor --limit 25
```

### ETL (`etl/`)

| Module | Purpose |
|--------|---------|
| `clean_transform.py` | Clean, normalize, deduplicate, export to lead-engine CSV |
| `embeddings.py` | Generate OpenAI embeddings, build FAISS/Pinecone/in-memory index |

```bash
# Clean raw scraped data
python -m etl.clean_transform --input data/raw --output data/input/leads.csv

# Build embeddings index
python -m etl.embeddings --input data/input/leads.csv --output data/embeddings

# Search similar leads
python -m etl.embeddings --search "AWS cloud migration" --top-k 5
```

### Agents (`agents/`)

| Module | Purpose |
|--------|---------|
| `qualification_agent.py` | GPT-4o-powered lead qualification with detailed reasoning |
| `scoring_agent.py` | ML scoring model with online feedback learning |

```bash
# LLM qualification
python -m agents.qualification_agent --input data/input/leads.csv --model gpt-4o

# Feedback scoring
python -m agents.scoring_agent --input data/input/leads.csv --min-score 70

# Retrain on feedback
python -m agents.scoring_agent --retrain --features

# Give feedback on a lead
python -m agents.scoring_agent --feedback-lead '{"Company Name": "Acme"}' --accepted
```

### Database (`db/`)

| Module | Purpose |
|--------|---------|
| `postgres_connector.py` | PostgreSQL storage with automatic JSON fallback |
| `vector_store.py` | Re-exports from `etl/embeddings.py` for backward compatibility |

```python
from db.postgres_connector import LeadDatabase

db = LeadDatabase()  # auto-detects PostgreSQL or falls back to JSON
db.insert_batch(leads)
leads = db.get_leads(min_score=70, country="United States")
db.update_approval(lead_id=1, approved=True)
```

### Pipeline (`pipeline/`)

| Module | Purpose |
|--------|---------|
| `daily_run.py` | Full 7-step pipeline orchestrator |

```bash
# Full pipeline
python -m pipeline.daily_run

# With options
python -m pipeline.daily_run \
  --skip-scraping \
  --input data/input/leads.csv \
  --min-score 75 \
  --no-llm \
  --skip-embeddings
```

### Lead Engine (`src/lead_engine.py`)

The core scoring and report generation engine.

```bash
# Process CSV with scoring + email generation
python -m src.lead_engine --input data/input/leads.csv --min-score 70

# Generate today's summary
python -m src.lead_engine --summary

# Generate approval digest .eml
python -m src.lead_engine --approval

# Show lead history stats
python -m src.lead_engine --history-stats

# Run full pipeline
python -m src.lead_engine --pipeline --skip-scraping --input data/input/leads.csv
```

### Dashboard (`app.py`)

Streamlit dashboard with:
- **KPI Cards** — Total leads, Hot/Warm/Qualified/Rejected counts
- **Score Distribution** — Bar chart of lead scores by company
- **Technology Chart** — Top hiring technologies (horizontal bar)
- **Pie Charts** — Priority breakdown and industry distribution
- **Lead Table** — Interactive filters (priority, approval, country, search)
- **Feedback Section** — Accept/Reject buttons to train the scoring model
- **Pipeline Runner** — Run the full pipeline from the dashboard UI
- **CSV Export** — Download filtered leads

```bash
streamlit run app.py
# Opens at http://localhost:8501
```

## ⚙️ Configuration Reference

All configuration lives in `config/settings.yaml`. Key sections:

| Section | Purpose |
|---------|---------|
| `company` | Company name, description, website, LinkedIn |
| `sender` | Outreach sender name, title, email |
| `target_industries` | Industries to target |
| `target_regions` | Countries/regions to target |
| `company_size` | Min/max employee count |
| `scrapers.linkedin` | LinkedIn queries, rate limits |
| `scrapers.google` | Google search queries |
| `scrapers.jobboards` | Job board sources and queries |
| `genai` | LLM provider, model, RAG config |
| `scoring` | Score weights, thresholds |
| `crm` | HubSpot/Salesforce integration |
| `automation` | Daily run time, retries |
| `dashboard` | Port, refresh interval |

## 📈 Scoring System

Leads are scored on a 0-100 scale using multiple signals:

| Dimension | Max Points | Description |
|-----------|-----------|-------------|
| Technology Match | 30 | Keywords found in job title/description |
| Hiring Activity | 20 | Hiring signal phrases detected |
| Company Size | 10 | Enterprise/mid-market preference |
| Industry Relevance | 10 | Target industry alignment |
| Decision-Maker Seniority | 15 | CTO/Director/VP vs junior role |
| Growth Indicators | 10 | Company expansion signals |
| Consulting Likelihood | 5 | Probability of needing external help |

**Thresholds:**
- 🔥 **Hot** (85+): High-priority, immediate outreach
- ⭐ **Warm** (75-84): Good fit, schedule nurture
- ✅ **Qualified** (70-74): Worth monitoring
- ❌ **Rejected** (<70): Below threshold

The scoring model learns from feedback — accepted/rejected leads retrain a logistic regression model that blends with the rule-based scores.

## 🔄 Feedback Loop

1. Run pipeline → generate qualified leads
2. Review leads in dashboard → Accept or Reject each
3. Feedback stored in `data/history/feedback.json`
4. Run `python -m agents.scoring_agent --retrain` to retrain
5. Next pipeline run uses updated model

The blended score formula: `final_score = 0.6 × rule_score + 0.4 × feedback_score`

## 📧 Output Files

After each pipeline run, the following files are generated in `data/output/`:

| File | Format | Description |
|------|--------|-------------|
| `leads_YYYY-MM-DD.xlsx` | Excel | Full qualified leads report |
| `leads_YYYY-MM-DD.pdf` | PDF | Formatted summary report |
| `daily_summary_YYYY-MM-DD.txt` | Text | Human-readable summary |
| `dashboard_data_YYYY-MM-DD.json` | JSON | Dashboard-ready data |
| `approval_digest_YYYY-MM-DD.eml` | EML | Outlook approval digest |
| `emails_YYYY-MM-DD/*.eml` | EML | Individual lead emails |
| `pipeline_summary_YYYY-MM-DD.json` | JSON | Pipeline run stats |

## 🛠️ Input CSV Format

Use `templates/leads_input_template.csv` as reference:

```csv
Company Name,Contact Name,Job Title,LinkedIn Profile,Company LinkedIn,Company Website,Industry,Company Size,Country,City,Technology Stack,Job Posting URL,Job Posted Date,notes
TechGrowth Inc,John Smith,Senior Python Developer,https://linkedin.com/in/johnsmith,https://linkedin.com/company/techgrowth,https://techgrowth.com,Information Technology,500-1000,United States,San Francisco,"Python, AWS, Docker",https://linkedin.com/jobs/view/12345,2026-06-28,Hiring for cloud infrastructure team
```

**Required columns:** Company Name, Contact Name, Job Title, LinkedIn Profile, Industry, Company Size, Country, City

## ⚠️ Compliance

- Always comply with LinkedIn ToS, GDPR, and CAN-SPAM
- No emails are sent without explicit human approval
- All outreach goes through the approval digest workflow
- Leads are deduplicated with configurable cooldown periods (default: 90 days per person, 30 days per company)

## 📋 Requirements

**Core:**
- Python 3.10+
- pandas, openpyxl, fpdf2, streamlit, plotly

**Scrapers:**
- requests, beautifulsoup4

**GenAI:**
- openai (for GPT-4o qualification and embeddings)

**Vector Store:**
- faiss-cpu (local) or pinecone-client (cloud)

**Database:**
- psycopg2-binary (PostgreSQL) or JSON fallback (no dependencies)

**Config:**
- pyyaml

## ⏰ Automated Scheduling

The pipeline can run automatically on a daily schedule using Windows Task Scheduler or cron.

### Windows (Task Scheduler)

```powershell
# Run PowerShell as Administrator, then:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\pipeline\setup_task_scheduler.ps1

# This registers a daily task at 08:00 AM
# To change the time:
.\pipeline\setup_task_scheduler.ps1 -RunTime "09:30"

# To remove the task:
.\pipeline\setup_task_scheduler.ps1 -Remove
```

The batch script (`pipeline/run_daily.bat`) handles:
- Virtual environment activation
- Loading `.env` environment variables
- Logging to `data/logs/pipeline_YYYY-MM-DD.log`

### Linux/Mac (cron)

```bash
# Make the script executable
chmod +x pipeline/run_daily.sh

# Add to crontab (runs daily at 8:00 AM)
crontab -e
# Add this line:
0 8 * * * /full/path/to/project/pipeline/run_daily.sh
```

See `pipeline/crontab.example` for alternative schedules.

### Manual Run

```bash
# Run pipeline from the dashboard UI (Streamlit)
# Or from the command line:
python -m pipeline.daily_run
```

### Logs

Pipeline logs are stored in `data/logs/pipeline_YYYY-MM-DD.log`.
Each log includes timestamps, lead counts, and any errors.

## 🐛 Troubleshooting

**No lead data in dashboard:**
```bash
# Process a CSV first
python -m src.lead_engine --input data/input/leads.csv
```

**OpenAI errors:**
```bash
# Check your API key
echo $OPENAI_API_KEY
# Run without LLM
python -m pipeline.daily_run --no-llm --input data/input/leads.csv
```

**FAISS import errors:**
```bash
pip install faiss-cpu
```

**PostgreSQL connection failed:**
The system auto-falls back to JSON file storage if PostgreSQL is unavailable.

## 📄 License

Internal use only. Do not distribute without authorization.
