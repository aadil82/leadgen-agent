"""
Qualification Agent — LLM-powered lead qualification using GPT-4o.

Uses OpenAI GPT-4o to analyze leads against target criteria and
provide detailed qualification reasoning. Replaces/supplements
the rule-based scoring in lead_engine.py.

Usage:
    python -m agents.qualification_agent --input data/input/leads.csv
"""

import argparse
import json
import os
import sys
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

import yaml


# ── Config ─────────────────────────────────────────────────────

def _load_settings() -> Dict[str, Any]:
    settings_path = os.path.join("config", "settings.yaml")
    if os.path.exists(settings_path):
        with open(settings_path, "r") as fh:
            return yaml.safe_load(fh) or {}
    return {}


def _get_openai_client():
    """Create OpenAI client."""
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai not installed. Run: pip install openai")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set.")
    return OpenAI(api_key=api_key)


# ── Qualification Prompt ──────────────────────────────────────

QUALIFICATION_SYSTEM_PROMPT = """You are an expert B2B lead qualification analyst for a technology consulting firm called {company_name}.

Your company specializes in:
{services}

Target industries: {industries}
Target regions: {regions}

Your task is to evaluate a potential lead and determine if they are a qualified prospect for {company_name}'s consulting services.

For each lead, analyze:
1. Industry relevance — Is this company in a target industry?
2. Technology alignment — Do they use technologies your company can support?
3. Hiring signals — Are they actively hiring for roles that suggest they need consulting help?
4. Company size — Are they in the ideal company size range?
5. Decision-maker access — Is the contact a senior decision-maker?
6. Timing — Are there signals that suggest they have an immediate need?
7. Geographic fit — Are they in a target region?

Respond with a JSON object containing:
{{
    "qualifies": true/false,
    "score": 0-100,
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation of qualification decision",
    "industry_match": true/false,
    "tech_match": true/false,
    "hiring_signal_match": true/false,
    "size_match": true/false,
    "decision_maker": true/false,
    "region_match": true/false,
    "recommended_services": ["list of relevant services"],
    "outreach_angle": "suggested approach for outreach",
    "risk_factors": ["any concerns"]
}}"""


QUALIFICATION_USER_PROMPT = """Please qualify this lead:

Company: {company_name}
Job Title: {job_title}
Industry: {industry}
Company Size: {company_size}
Location: {city}, {country}
Technology Stack: {tech_stack}
Job URL: {job_url}
Job Description Snippet: {description}
LinkedIn Profile: {linkedin}
Company LinkedIn: {company_linkedin}

Evaluate this lead against our target criteria and respond with the JSON analysis."""


# ── Qualification Agent ────────────────────────────────────────


class QualificationAgent:
    """LLM-powered lead qualification agent."""

    def __init__(
        self,
        model: str = "gpt-4o",
        temperature: float = 0.3,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.client = _get_openai_client()
        self.settings = _load_settings()

        company = self.settings.get("company", {})
        self.company_name = company.get("name", "Logixal")
        self.services = "\n".join(
            f"  - {s}" for s in self.settings.get("services_offered", [
                "Cloud Migration (AWS, Azure, GCP)",
                "Data Engineering & Analytics",
                "AI / Machine Learning Solutions",
                "DevOps & Platform Engineering",
                "Staff Augmentation & Consulting",
            ])
        )
        self.industries = ", ".join(self.settings.get("target_industries", [
            "Information Technology", "Software", "E-Commerce",
            "Financial Services", "Healthcare", "Manufacturing",
        ]))
        self.regions = ", ".join(self.settings.get("target_regions", [
            "United States", "United Kingdom", "Canada", "Germany",
            "India", "Australia", "Netherlands", "Singapore",
        ]))

    def _build_system_prompt(self) -> str:
        return QUALIFICATION_SYSTEM_PROMPT.format(
            company_name=self.company_name,
            services=self.services,
            industries=self.industries,
            regions=self.regions,
        )

    def qualify_lead(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Qualify a single lead using LLM analysis."""
        user_prompt = QUALIFICATION_USER_PROMPT.format(
            company_name=lead.get("Company Name", ""),
            job_title=lead.get("Job Title", ""),
            industry=lead.get("Industry", ""),
            company_size=lead.get("Company Size", ""),
            city=lead.get("City", ""),
            country=lead.get("Country", ""),
            tech_stack=lead.get("Technology Stack", ""),
            job_url=lead.get("Job Posting URL", ""),
            description=lead.get("notes", lead.get("description", ""))[:1000],
            linkedin=lead.get("LinkedIn Profile", ""),
            company_linkedin=lead.get("Company LinkedIn", ""),
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._build_system_prompt()},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                max_tokens=2000,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content or "{}"
            result = json.loads(content)

            # Ensure all required fields exist with defaults
            result.setdefault("qualifies", False)
            result.setdefault("score", 0)
            result.setdefault("confidence", 0.5)
            result.setdefault("reasoning", "")
            result.setdefault("industry_match", False)
            result.setdefault("tech_match", False)
            result.setdefault("hiring_signal_match", False)
            result.setdefault("size_match", False)
            result.setdefault("decision_maker", False)
            result.setdefault("region_match", False)
            result.setdefault("recommended_services", [])
            result.setdefault("outreach_angle", "")
            result.setdefault("risk_factors", [])

            return result

        except Exception as e:
            print(f"  [ERROR] LLM qualification failed for {lead.get('Company Name', '?')}: {e}")
            traceback.print_exc()
            return {
                "qualifies": False,
                "score": 0,
                "confidence": 0.0,
                "reasoning": f"LLM qualification failed: {e}",
                "industry_match": False,
                "tech_match": False,
                "hiring_signal_match": False,
                "size_match": False,
                "decision_maker": False,
                "region_match": False,
                "recommended_services": [],
                "outreach_angle": "",
                "risk_factors": ["LLM qualification failed"],
            }

    def qualify_batch(
        self,
        leads: List[Dict[str, Any]],
        min_score: float = 70.0,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Qualify a batch of leads.
        Returns (qualified, rejected) lists.
        """
        qualified: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []

        print(f"\n{'='*60}")
        print(f"  LLM Qualification Agent")
        print(f"  Model: {self.model} | Leads: {len(leads)}")
        print(f"{'='*60}")

        for i, lead in enumerate(leads, 1):
            company = lead.get("Company Name", "?")
            print(f"\n  [{i}/{len(leads)}] Qualifying: {company}")

            result = self.qualify_lead(lead)

            # Merge LLM results into lead
            lead["llm_qualification"] = result
            lead["qualification_method"] = "llm"
            lead["llm_score"] = result.get("score", 0)
            lead["llm_confidence"] = result.get("confidence", 0)
            lead["llm_reasoning"] = result.get("reasoning", "")

            # Build qualification reason
            reasons = []
            if result.get("industry_match"):
                reasons.append("Industry match")
            if result.get("tech_match"):
                reasons.append("Tech match")
            if result.get("hiring_signal_match"):
                reasons.append("Hiring signals")
            if result.get("size_match"):
                reasons.append("Company size fit")
            if result.get("decision_maker"):
                reasons.append("Decision-maker access")
            if result.get("region_match"):
                reasons.append("Region match")
            lead["qualification_reason"] = "; ".join(reasons) or result.get("reasoning", "")

            # Store recommended services
            lead["recommended_services"] = result.get("recommended_services", [])
            lead["outreach_angle"] = result.get("outreach_angle", "")

            score = result.get("score", 0)
            qualifies = result.get("qualifies", False)

            if qualifies and score >= min_score:
                qualified.append(lead)
                print(f"    ✅ QUALIFIED (score: {score}, confidence: {result.get('confidence', 0):.2f})")
                print(f"    Reasoning: {result.get('reasoning', '')[:120]}")
            else:
                lead["rejection_reason"] = result.get("reasoning", f"LLM score {score} below threshold")
                rejected.append(lead)
                print(f"    ❌ REJECTED (score: {score})")
                print(f"    Reasoning: {result.get('reasoning', '')[:120]}")

        print(f"\n  Summary: {len(qualified)} qualified, {len(rejected)} rejected")
        return qualified, rejected


# ── Public API ────────────────────────────────────────────────


def qualify_leads(
    leads: List[Dict[str, Any]],
    min_score: float = 70.0,
    model: str = "gpt-4o",
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Run LLM qualification on a list of leads."""
    agent = QualificationAgent(model=model)
    return agent.qualify_batch(leads, min_score=min_score)


# ── CLI ────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM Lead Qualification Agent")
    parser.add_argument("--input", "-i", required=True, help="Input CSV or JSON file")
    parser.add_argument("--min-score", "-m", type=float, default=70.0, help="Minimum score threshold")
    parser.add_argument("--model", default="gpt-4o", help="OpenAI model to use")
    parser.add_argument("--output", "-o", help="Output JSON path")
    args = parser.parse_args()

    import pandas as pd
    if args.input.endswith(".csv"):
        df = pd.read_csv(args.input)
        leads = df.to_dict(orient="records")
    else:
        with open(args.input, "r", encoding="utf-8") as fh:
            leads = json.load(fh)

    qualified, rejected = qualify_leads(leads, args.min_score, args.model)

    output = {
        "generated_at": datetime.now().isoformat(),
        "total": len(leads),
        "qualified": len(qualified),
        "rejected": len(rejected),
        "qualified_leads": qualified,
        "rejected_leads": rejected,
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(output, fh, indent=2, default=str)
        print(f"\nResults saved to: {args.output}")
    else:
        print(f"\nQualified: {len(qualified)} | Rejected: {len(rejected)}")


if __name__ == "__main__":
    main()
