# Daily SDR Workflow

This guide explains how to use the LinkedIn SDR Agent day-to-day.

---

##  Morning Workflow (~30 min)

### 1. Collect LinkedIn Data

Search LinkedIn for hiring signals (manually or via LinkedIn Sales Navigator):

- Companies with recent job postings in your target technologies
- Recruiters / hiring managers posting about open roles
- Company pages with "We're Hiring" banners
- Startups that received funding (check Crunchbase / TechCrunch)

**Paste the raw data** into a new CSV file:

```
data/input/leads_YYYY-MM-DD.csv
```

Use the template at `templates/leads_input_template.csv` as a reference.

| Column | Required | Description |
|--------|----------|-------------|
| Company Name | Yes | Full legal / trading name |
| Contact Name | Yes | Person's full name |
| Job Title | Yes | Their role title |
| LinkedIn Profile | Yes | Full URL to their LinkedIn profile |
| Company LinkedIn | Recommended | Company page URL |
| Company Website | Recommended | Company website |
| Industry | Recommended | e.g. "Information Technology" |
| Company Size | Recommended | e.g. "1000-5000" |
| Country | Yes | Country of the contact/company |
| City | Recommended | City location |
| Technology Stack | Recommended | Technologies they use (comma separated) |
| Job Posting URL | If applicable | Link to the job posting |
| Job Posted Date | If applicable | Date the job was posted |
| notes | Optional | Any context about the lead |

### 2. Run the Lead Engine

```bash
python -m src.lead_engine --input data/input/leads_2026-06-27.csv --min-score 70
```

This will:
- Score every lead (0-100)
- Filter out duplicates using local history
- Generate personalized email drafts
- Create an Excel report: `data/output/leads_YYYY-MM-DD.xlsx`
- Create a text summary: `data/output/daily_summary_YYYY-MM-DD.txt`

### 3. Review Results

Open the Excel report and review:

- **Lead Score** — was the automated score accurate?
- **Email Draft** — is it appropriate for this prospect?
- **Duplicates** — mark any you've already contacted

### 4. Approval Workflow

For each email you want to send:

1. Copy the draft from the Excel `Email Draft` column
2. Paste into Outlook
3. Review, personalize further if needed
4. **Get approval** from your manager (in-person or via the approval email)
5. Send
6. Update the Excel: `Approval Status` → `Approved`, `Email Draft Status` → `Sent`

### 5. Update History

The engine automatically updates `data/history/leads_history.json`.
You don't need to do anything here — it prevents duplicate outreach.

---

##  End-of-Day Workflow (~10 min)

### 1. Review Today's Activity

```bash
python -m src.lead_engine --summary
```

Or re-run the engine on today's data to regenerate the latest report.

### 2. Update Follow-ups

For any leads that responded or need a follow-up:

- Update the `Next Action` column in the Excel
- Schedule follow-up tasks in your calendar

### 3. Archive Data

Keep your input CSVs organized:

```
data/input/
├── leads_2026-06-27.csv
├── leads_2026-06-28.csv
└── ...
```

---

##  Tips

- **Quality > quantity**: 5 well-qualified leads are better than 20 cold ones
- **Be specific**: The more detail in your CSV, the better the email drafts
- **Don't fabricate**: Never invent job postings or contact info
- **LinkedIn compliance**: Only use publicly available information
- **GDPR**: Ensure you have a lawful basis for processing personal data
- **CAN-SPAM**: Include an opt-out mechanism in every email

---

##  Extending the Agent

- Add new technologies to `src/config.py` → `TECHNOLOGY_KEYWORDS`
- Tune scoring weights in `src/config.py` → `ScoringWeights`
- Add a CRM integration by replacing the stub in `process_input_csv()`
- Enable the GitHub Actions workflow by pushing to GitHub
