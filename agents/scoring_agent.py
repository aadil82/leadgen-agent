"""
Scoring Agent — ML-based lead scoring that learns from feedback.

Combines rule-based scoring with LLM-enhanced scoring and
feedback-driven model retraining.

Usage:
    python -m agents.scoring_agent --input data/input/leads.csv --feedback data/history/feedback.json
"""

import argparse
import json
import math
import os
import pickle
import re
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


# ── Config ─────────────────────────────────────────────────────

FEEDBACK_FILE = "data/history/feedback.json"
MODEL_FILE = "data/model/scoring_model.pkl"


# ── Feature Engineering ───────────────────────────────────────


def extract_features(lead: Dict[str, Any]) -> Dict[str, float]:
    """Extract numeric features from a lead for scoring."""
    features: Dict[str, float] = {}

    # Technology match count
    tech_text = f"{lead.get('Job Title', '')} {lead.get('Technology Stack', '')} {lead.get('Job Posting URL', '')}"
    tech_keywords = [
        "python", "java", "aws", "azure", "gcp", "kubernetes", "docker",
        "terraform", "ai", "machine learning", "ml", "genai", "llm",
        "react", "angular", "django", "fastapi", "spring boot",
        "postgresql", "mysql", "mongodb", "snowflake", "databricks",
        "salesforce", "sap", "devops", "microservices", "cloud migration",
    ]
    tech_count = sum(1 for kw in tech_keywords if kw in tech_text.lower())
    features["tech_match_count"] = min(tech_count, 10) / 10.0

    # Hiring signal count
    signals = [
        "hiring", "now hiring", "urgent", "immediate", "join our team",
        "looking for", "open position", "job opening", "career opportunity",
    ]
    signal_count = sum(1 for s in signals if s in tech_text.lower())
    features["hiring_signal_count"] = min(signal_count, 5) / 5.0

    # Company size score
    size_str = lead.get("Company Size", "")
    size_score = 0.5
    if size_str:
        numbers = [int(n) for n in re.findall(r"\d+", size_str.replace(",", ""))]
        if numbers:
            max_val = max(numbers)
            if max_val >= 1000:
                size_score = 1.0
            elif max_val >= 200:
                size_score = 0.8
            elif max_val >= 50:
                size_score = 0.6
            else:
                size_score = 0.3
    features["company_size"] = size_score

    # Industry relevance
    high_industries = [
        "information technology", "software", "technology", "computer software",
        "internet", "telecommunications", "financial services", "banking",
        "healthcare", "consulting", "e-commerce", "retail technology",
    ]
    industry = lead.get("Industry", "").lower()
    features["industry_relevance"] = 1.0 if any(ind in industry for ind in high_industries) else 0.3

    # Decision-maker seniority
    title = lead.get("Job Title", "").lower()
    senior_keywords = [
        "cto", "chief", "vp", "vice president", "director", "head of",
        "engineering manager", "technical manager", "architect",
    ]
    features["seniority"] = 1.0 if any(kw in title for kw in senior_keywords) else 0.3

    # Region match
    country = lead.get("Country", "").lower()
    target_regions = ["united states", "united kingdom", "canada", "germany", "india", "australia"]
    features["region_match"] = 1.0 if any(r in country for r in target_regions) else 0.2

    # Has LinkedIn profile
    features["has_linkedin"] = 1.0 if lead.get("LinkedIn Profile") else 0.0

    # Has job URL
    features["has_job_url"] = 1.0 if lead.get("Job Posting URL") else 0.0

    # Has company website
    features["has_website"] = 1.0 if lead.get("Company Website") else 0.0

    return features


# ── Online Learning Scorer ────────────────────────────────────


class FeedbackScorer:
    """
    Scoring model that learns from accepted/rejected lead feedback.
    Uses a simple logistic regression with online updates.
    """

    def __init__(self) -> None:
        self.weights: Dict[str, float] = {}
        self.bias: float = 0.0
        self.learning_rate: float = 0.01
        self.n_samples: int = 0
        self.feature_names: List[str] = []

    def _sigmoid(self, x: float) -> float:
        """Sigmoid activation function."""
        x = max(-500, min(500, x))
        return 1.0 / (1.0 + math.exp(-x))

    def predict_proba(self, features: Dict[str, float]) -> float:
        """Predict probability of lead being qualified."""
        if not self.weights:
            return 0.5  # default if no training data

        dot_product = self.bias
        for name, value in features.items():
            weight = self.weights.get(name, 0.0)
            dot_product += weight * value

        return self._sigmoid(dot_product)

    def predict(self, features: Dict[str, float], threshold: float = 0.5) -> bool:
        """Predict if a lead qualifies."""
        return self.predict_proba(features) >= threshold

    def update(self, features: Dict[str, float], label: bool) -> None:
        """
        Update weights based on a labeled example (online learning).
        label=True means accepted, label=False means rejected.
        """
        target = 1.0 if label else 0.0
        prediction = self.predict_proba(features)
        error = target - prediction

        # Update weights
        for name, value in features.items():
            if name not in self.weights:
                self.weights[name] = 0.0
            self.weights[name] += self.learning_rate * error * value

        self.bias += self.learning_rate * error
        self.n_samples += 1

    def train_batch(
        self,
        leads: List[Dict[str, Any]],
        accepted: List[Dict[str, Any]],
    ) -> None:
        """Train the model on a batch of labeled data."""
        accepted_keys = set()
        for lead in accepted:
            key = f"{lead.get('Company Name', '')}|{lead.get('Job Title', '')}"
            accepted_keys.add(key)

        for lead in leads:
            features = extract_features(lead)
            key = f"{lead.get('Company Name', '')}|{lead.get('Job Title', '')}"
            label = key in accepted_keys
            self.update(features, label)

        print(f"  Trained on {len(leads)} examples ({len(accepted)} accepted)")

    def score_lead(self, lead: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
        """Score a single lead. Returns (score, features)."""
        features = extract_features(lead)
        prob = self.predict_proba(features)
        # Convert probability to 0-100 score
        score = round(prob * 100, 1)
        return score, features

    def save(self, path: str = MODEL_FILE) -> None:
        """Save the model to disk."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            "weights": self.weights,
            "bias": self.bias,
            "learning_rate": self.learning_rate,
            "n_samples": self.n_samples,
            "feature_names": list(self.weights.keys()),
        }
        with open(path, "wb") as fh:
            pickle.dump(data, fh)
        print(f"  Model saved to: {path}")

    def load(self, path: str = MODEL_FILE) -> bool:
        """Load the model from disk."""
        if not os.path.exists(path):
            return False
        with open(path, "rb") as fh:
            data = pickle.load(fh)
        self.weights = data.get("weights", {})
        self.bias = data.get("bias", 0.0)
        self.learning_rate = data.get("learning_rate", 0.01)
        self.n_samples = data.get("n_samples", 0)
        self.feature_names = data.get("feature_names", [])
        print(f"  Model loaded: {self.n_samples} samples, {len(self.weights)} features")
        return True

    def get_feature_importance(self) -> List[Tuple[str, float]]:
        """Get feature importance sorted by absolute weight."""
        return sorted(
            self.weights.items(),
            key=lambda x: abs(x[1]),
            reverse=True,
        )


# ── Feedback Management ───────────────────────────────────────


def load_feedback() -> Dict[str, Any]:
    """Load feedback data from disk."""
    if os.path.exists(FEEDBACK_FILE):
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {"accepted": [], "rejected": [], "history": []}


def save_feedback(feedback: Dict[str, Any]) -> None:
    """Save feedback data to disk."""
    os.makedirs(os.path.dirname(FEEDBACK_FILE), exist_ok=True)
    with open(FEEDBACK_FILE, "w", encoding="utf-8") as fh:
        json.dump(feedback, fh, indent=2, default=str)


def add_feedback(
    lead: Dict[str, Any],
    accepted: bool,
    feedback_text: str = "",
) -> None:
    """Add a feedback entry for a lead."""
    feedback = load_feedback()

    entry = {
        "timestamp": datetime.now().isoformat(),
        "company": lead.get("Company Name", ""),
        "contact": lead.get("Contact Name", ""),
        "title": lead.get("Job Title", ""),
        "score": lead.get("score", lead.get("llm_score", 0)),
        "accepted": accepted,
        "feedback_text": feedback_text,
    }

    if accepted:
        feedback["accepted"].append(entry)
    else:
        feedback["rejected"].append(entry)

    feedback["history"].append(entry)
    save_feedback(feedback)
    print(f"  Feedback recorded: {'ACCEPTED' if accepted else 'REJECTED'} - {entry['company']}")


def retrain_model(model: Optional[FeedbackScorer] = None) -> FeedbackScorer:
    """Retrain the scoring model on all feedback data."""
    if model is None:
        model = FeedbackScorer()
        model.load()

    feedback = load_feedback()
    accepted = feedback.get("accepted", [])
    rejected = feedback.get("rejected", [])

    # Build training data from feedback
    all_leads = []
    accepted_leads = []

    for entry in accepted:
        lead = {
            "Company Name": entry.get("company", ""),
            "Contact Name": entry.get("contact", ""),
            "Job Title": entry.get("title", ""),
            "score": entry.get("score", 0),
        }
        all_leads.append(lead)
        accepted_leads.append(lead)

    for entry in rejected:
        lead = {
            "Company Name": entry.get("company", ""),
            "Contact Name": entry.get("contact", ""),
            "Job Title": entry.get("title", ""),
            "score": entry.get("score", 0),
        }
        all_leads.append(lead)

    if all_leads:
        model.train_batch(all_leads, accepted_leads)
        model.save()
        print(f"  Model retrained on {len(all_leads)} feedback entries")
    else:
        print("  No feedback data to train on.")

    return model


# ── Public API ────────────────────────────────────────────────


def score_leads_with_feedback(
    leads: List[Dict[str, Any]],
    min_score: float = 70.0,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], FeedbackScorer]:
    """
    Score leads using the feedback-enhanced model.
    Returns (qualified, rejected, model).
    """
    model = FeedbackScorer()
    model.load()

    qualified: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    print(f"\n{'='*60}")
    print(f"  Feedback-Enhanced Scoring Agent")
    print(f"  Model samples: {model.n_samples} | Features: {len(model.weights)}")
    print(f"  Leads to score: {len(leads)}")
    print(f"{'='*60}")

    for lead in leads:
        score, features = model.score_lead(lead)
        lead["feedback_score"] = score
        lead["feedback_features"] = features

        if score >= min_score:
            qualified.append(lead)
        else:
            lead["rejection_reason"] = f"Feedback model score {score} below threshold"
            rejected.append(lead)

    # Print top features
    importance = model.get_feature_importance()
    if importance:
        print("\n  Top features:")
        for name, weight in importance[:5]:
            print(f"    {name}: {weight:.4f}")

    print(f"\n  Results: {len(qualified)} qualified, {len(rejected)} rejected")
    return qualified, rejected, model


# ── CLI ────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="ML Scoring Agent with Feedback Learning")
    parser.add_argument("--input", "-i", help="Input CSV or JSON file to score")
    parser.add_argument("--min-score", "-m", type=float, default=70.0, help="Minimum score threshold")
    parser.add_argument("--feedback-lead", help="JSON string of lead to give feedback on")
    parser.add_argument("--accepted", action="store_true", help="Mark feedback as accepted")
    parser.add_argument("--rejected", action="store_true", help="Mark feedback as rejected")
    parser.add_argument("--retrain", action="store_true", help="Retrain model on feedback data")
    parser.add_argument("--features", action="store_true", help="Show feature importance")
    parser.add_argument("--output", "-o", help="Output JSON path")
    args = parser.parse_args()

    if args.retrain:
        model = retrain_model()
        if args.features:
            importance = model.get_feature_importance()
            print("\nFeature Importance:")
            for name, weight in importance:
                print(f"  {name}: {weight:.4f}")
        return

    if args.feedback_lead:
        lead = json.loads(args.feedback_lead)
        if args.accepted:
            add_feedback(lead, accepted=True)
        elif args.rejected:
            add_feedback(lead, accepted=False)
        else:
            print("Specify --accepted or --rejected")
        return

    if args.input:
        import pandas as pd
        if args.input.endswith(".csv"):
            df = pd.read_csv(args.input)
            leads = df.to_dict(orient="records")
        else:
            with open(args.input, "r", encoding="utf-8") as fh:
                leads = json.load(fh)

        qualified, rejected, model = score_leads_with_feedback(leads, args.min_score)

        if args.output:
            output = {
                "generated_at": datetime.now().isoformat(),
                "model_samples": model.n_samples,
                "qualified": len(qualified),
                "rejected": len(rejected),
                "qualified_leads": qualified,
                "rejected_leads": rejected,
            }
            with open(args.output, "w", encoding="utf-8") as fh:
                json.dump(output, fh, indent=2, default=str)
            print(f"\nResults saved to: {args.output}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
