"""
Database Connectors — PostgreSQL and MongoDB connectors for lead storage.

Provides persistent storage for leads, feedback, and pipeline metadata.

Usage:
    from db.postgres_connector import LeadDatabase
    db = LeadDatabase()
    db.insert_lead(lead_dict)
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional


# ── PostgreSQL Connector ──────────────────────────────────────


class LeadDatabase:
    """
    PostgreSQL-based lead storage.
    Falls back to JSON file storage if PostgreSQL is not available.
    """

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS leads (
        id SERIAL PRIMARY KEY,
        company_name VARCHAR(500),
        contact_name VARCHAR(300),
        job_title VARCHAR(500),
        linkedin_profile VARCHAR(500),
        company_linkedin VARCHAR(500),
        company_website VARCHAR(500),
        industry VARCHAR(300),
        company_size VARCHAR(100),
        country VARCHAR(100),
        city VARCHAR(100),
        technology_stack TEXT,
        job_posting_url VARCHAR(1000),
        job_posted_date VARCHAR(50),
        score FLOAT,
        priority VARCHAR(20),
        qualification_method VARCHAR(50),
        qualification_reason TEXT,
        email_draft TEXT,
        email_status VARCHAR(50),
        approval_status VARCHAR(50),
        customer_status VARCHAR(50),
        rejection_reason TEXT,
        source VARCHAR(100),
        raw_data JSONB,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS feedback (
        id SERIAL PRIMARY KEY,
        lead_id INTEGER REFERENCES leads(id),
        accepted BOOLEAN,
        feedback_text TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS pipeline_runs (
        id SERIAL PRIMARY KEY,
        run_date DATE,
        total_leads INTEGER,
        qualified_leads INTEGER,
        rejected_leads INTEGER,
        duration_seconds FLOAT,
        status VARCHAR(50),
        error_message TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_leads_company ON leads(company_name);
    CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(score DESC);
    CREATE INDEX IF NOT EXISTS idx_leads_country ON leads(country);
    CREATE INDEX IF NOT EXISTS idx_leads_created ON leads(created_at DESC);
    """

    def __init__(self, database_url: Optional[str] = None) -> None:
        self.database_url = database_url or os.environ.get("DATABASE_URL", "")
        self._conn = None
        self._use_json_fallback = not bool(self.database_url)
        self._json_path = "data/history/leads_database.json"

        if self._use_json_fallback:
            print("  [INFO] No DATABASE_URL set. Using JSON file storage.")
        else:
            self._connect()

    def _connect(self) -> None:
        """Connect to PostgreSQL."""
        try:
            import psycopg2
            self._conn = psycopg2.connect(self.database_url)
            self._conn.autocommit = True
            self._ensure_schema()
            print("  Connected to PostgreSQL.")
        except ImportError:
            print("  [WARN] psycopg2 not installed. Using JSON fallback.")
            self._use_json_fallback = True
        except Exception as e:
            print(f"  [WARN] PostgreSQL connection failed: {e}. Using JSON fallback.")
            self._use_json_fallback = True

    def _ensure_schema(self) -> None:
        """Create tables if they don't exist."""
        if self._conn:
            try:
                cursor = self._conn.cursor()
                cursor.execute(self.SCHEMA_SQL)
                cursor.close()
            except Exception as e:
                print(f"  [WARN] Schema creation failed: {e}")

    def _load_json(self) -> List[Dict[str, Any]]:
        """Load leads from JSON file."""
        if os.path.exists(self._json_path):
            with open(self._json_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        return []

    def _save_json(self, data: List[Dict[str, Any]]) -> None:
        """Save leads to JSON file."""
        os.makedirs(os.path.dirname(self._json_path), exist_ok=True)
        with open(self._json_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)

    def insert_lead(self, lead: Dict[str, Any]) -> Optional[int]:
        """Insert a lead into the database. Returns the lead ID."""
        if self._use_json_fallback:
            data = self._load_json()
            lead["_id"] = len(data) + 1
            lead["_created_at"] = datetime.now().isoformat()
            data.append(lead)
            self._save_json(data)
            return lead["_id"]

        try:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO leads (
                    company_name, contact_name, job_title, linkedin_profile,
                    company_linkedin, company_website, industry, company_size,
                    country, city, technology_stack, job_posting_url, job_posted_date,
                    score, priority, qualification_method, qualification_reason,
                    email_draft, email_status, approval_status, customer_status,
                    rejection_reason, source, raw_data
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) RETURNING id
            """, (
                lead.get("Company Name", ""),
                lead.get("Contact Name", ""),
                lead.get("Job Title", ""),
                lead.get("LinkedIn Profile", ""),
                lead.get("Company LinkedIn", ""),
                lead.get("Company Website", ""),
                lead.get("Industry", ""),
                lead.get("Company Size", ""),
                lead.get("Country", ""),
                lead.get("City", ""),
                lead.get("Technology Stack", ""),
                lead.get("Job Posting URL", ""),
                lead.get("Job Posted Date", ""),
                lead.get("score", lead.get("llm_score", 0)),
                lead.get("priority", lead.get("score_class", "")),
                lead.get("qualification_method", ""),
                lead.get("qualification_reason", ""),
                lead.get("email_draft", ""),
                lead.get("email_status", "Drafted"),
                lead.get("approval_status", "Pending"),
                lead.get("customer_status", "New Prospect"),
                lead.get("rejection_reason", ""),
                lead.get("source", ""),
                json.dumps(lead, default=str),
            ))
            lead_id = cursor.fetchone()[0]
            cursor.close()
            return lead_id
        except Exception as e:
            print(f"  [ERROR] Insert failed: {e}")
            return None

    def insert_batch(self, leads: List[Dict[str, Any]]) -> int:
        """Insert a batch of leads. Returns count of successful inserts."""
        count = 0
        for lead in leads:
            if self.insert_lead(lead) is not None:
                count += 1
        return count

    def get_leads(
        self,
        limit: int = 100,
        min_score: float = 0,
        country: str = "",
        status: str = "",
    ) -> List[Dict[str, Any]]:
        """Retrieve leads with optional filters."""
        if self._use_json_fallback:
            data = self._load_json()
            filtered = [
                l for l in data
                if l.get("score", l.get("llm_score", 0)) >= min_score
                and (not country or l.get("Country", "") == country)
                and (not status or l.get("approval_status", "") == status)
            ]
            return sorted(filtered, key=lambda x: -x.get("score", 0))[:limit]

        try:
            cursor = self._conn.cursor()
            query = "SELECT * FROM leads WHERE score >= %s"
            params: list = [min_score]

            if country:
                query += " AND country = %s"
                params.append(country)
            if status:
                query += " AND approval_status = %s"
                params.append(status)

            query += " ORDER BY score DESC LIMIT %s"
            params.append(limit)

            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            cursor.close()
            return results
        except Exception as e:
            print(f"  [ERROR] Query failed: {e}")
            return []

    def update_approval(self, lead_id: int, approved: bool) -> bool:
        """Update a lead's approval status."""
        status = "Approved" if approved else "Rejected"

        if self._use_json_fallback:
            data = self._load_json()
            for lead in data:
                if lead.get("_id") == lead_id:
                    lead["approval_status"] = status
                    self._save_json(data)
                    return True
            return False

        try:
            cursor = self._conn.cursor()
            cursor.execute(
                "UPDATE leads SET approval_status = %s, updated_at = NOW() WHERE id = %s",
                (status, lead_id),
            )
            cursor.close()
            return True
        except Exception as e:
            print(f"  [ERROR] Update failed: {e}")
            return False

    def log_pipeline_run(
        self,
        total: int,
        qualified: int,
        rejected: int,
        duration: float,
        status: str = "success",
        error: str = "",
    ) -> None:
        """Log a pipeline run for tracking."""
        if self._use_json_fallback:
            return  # skip for JSON fallback

        try:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO pipeline_runs (
                    run_date, total_leads, qualified_leads, rejected_leads,
                    duration_seconds, status, error_message
                ) VALUES (CURRENT_DATE, %s, %s, %s, %s, %s, %s)
            """, (total, qualified, rejected, duration, status, error))
            cursor.close()
        except Exception as e:
            print(f"  [WARN] Failed to log pipeline run: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        if self._use_json_fallback:
            data = self._load_json()
            return {
                "total_leads": len(data),
                "storage": "json",
            }

        try:
            cursor = self._conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM leads")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM leads WHERE score >= 70")
            qualified = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(DISTINCT company_name) FROM leads")
            companies = cursor.fetchone()[0]
            cursor.close()
            return {
                "total_leads": total,
                "qualified_leads": qualified,
                "unique_companies": companies,
                "storage": "postgresql",
            }
        except Exception as e:
            print(f"  [ERROR] Stats query failed: {e}")
            return {"total_leads": 0, "storage": "error"}

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


# ── Public API ────────────────────────────────────────────────


def get_database() -> LeadDatabase:
    """Get a database connection instance."""
    return LeadDatabase()
