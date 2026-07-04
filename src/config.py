"""
Configuration — sender profile, technology keywords, scoring weights, and paths.
Edit this file before first use with your real company details.
"""

from dataclasses import dataclass
from typing import List

# ═══════════════════════════════════════════════════════════════
# 1.  SENDER / COMPANY PROFILE  —  EDIT THESE WITH YOUR INFO
# ═══════════════════════════════════════════════════════════════

COMPANY_NAME = "Logixal"
SENDER_NAME = "Aadil Shaikh"
SENDER_TITLE = "AI Tech Architect"
SENDER_EMAIL = "aadil.shaikh@logixal.com"
SENDER_PHONE = "+1-555-000-0000"
SENDER_LINKEDIN = "https://www.linkedin.com/in/aadil-shaikh-b8511a154"

# Company description used in outreach emails
COMPANY_DESCRIPTION = (
    "a leading technology consulting firm specialising in cloud infrastructure, "
    "data engineering, AI/ML solutions, and enterprise software development"
)

# Relevant experience summary (be factual — never exaggerate)
RELEVANT_EXPERIENCE = (
    "successfully delivered 50+ cloud migration and data engineering projects "
    "for enterprise clients across healthcare, finance, and e-commerce"
)

SERVICES_OFFERED = [
    "Cloud Migration (AWS, Azure, GCP)",
    "Data Engineering & Analytics",
    "AI / Machine Learning Solutions",
    "DevOps & Platform Engineering",
    "Staff Augmentation & Consulting",
]

# ═══════════════════════════════════════════════════════════════
# 2.  TECHNOLOGY KEYWORDS  —  extend this list freely
# ═══════════════════════════════════════════════════════════════

TECHNOLOGY_KEYWORDS: List[str] = [
    # Languages & Runtimes
    "Python",
    "Java",
    "C#",
    ".NET",
    "Node.js",
    "TypeScript",
    "Go",
    "Rust",
    # Cloud Providers
    "AWS",
    "Amazon Web Services",
    "Microsoft Azure",
    "Azure",
    "Google Cloud Platform",
    "GCP",
    # DevOps & Infrastructure
    "DevOps",
    "Kubernetes",
    "Docker",
    "Terraform",
    "Ansible",
    "Linux",
    "CI/CD",
    "Jenkins",
    "GitHub Actions",
    # Databases
    "SQL",
    "PostgreSQL",
    "MySQL",
    "Snowflake",
    "Oracle",
    "MongoDB",
    "DynamoDB",
    # Big Data & ETL
    "Databricks",
    "Spark",
    "Apache Spark",
    "ETL",
    "Informatica",
    "Talend",
    "Airflow",
    # AI / ML
    "AI",
    "Artificial Intelligence",
    "Machine Learning",
    "ML",
    "Generative AI",
    "GenAI",
    "LLM",
    "Large Language Model",
    "OpenAI",
    "Azure AI",
    "LangChain",
    "Computer Vision",
    "NLP",
    # Frontend
    "React",
    "Angular",
    "Vue.js",
    "Full Stack",
    "Frontend",
    # Backend
    "Backend Engineering",
    "Microservices",
    "REST API",
    "GraphQL",
    "Spring Boot",
    "Django",
    "FastAPI",
    "Flask",
    # Enterprise
    "Salesforce",
    "SAP",
    "Power BI",
    "Tableau",
    "Oracle DBA",
    # Security
    "Cyber Security",
    "Network Engineering",
    "Cloud Security",
    "IAM",
    # Skills
    "Cloud Migration",
    "Digital Transformation",
    "Data Engineering",
    "Data Science",
    "Solution Architect",
    "Technical Architect",
]

# ═══════════════════════════════════════════════════════════════
# 3.  HIRING SIGNAL PHRASES  —  matched against LinkedIn posts
# ═══════════════════════════════════════════════════════════════

HIRING_SIGNALS: List[str] = [
    "Hiring",
    "Now Hiring",
    "Urgent Hiring",
    "Immediate Requirement",
    "We are hiring",
    "Join our team",
    "We're looking for",
    "Open Position",
    "Job Opening",
    "Career Opportunity",
    "Contract Position",
    "Permanent Position",
    "Consultant Needed",
    "Freelance Opportunity",
    "Cloud Migration Project",
    "Digital Transformation",
    "Data Engineering Project",
    "AI Project",
    "Machine Learning Engineer",
    "Generative AI",
    "Azure Architect",
    "GCP Engineer",
    "Oracle DBA",
    "DevOps Engineer",
    "Platform Engineer",
]

# ═══════════════════════════════════════════════════════════════
# 4.  SCORING WEIGHTS  —  tune to your preference
# ═══════════════════════════════════════════════════════════════

@dataclass
class ScoringWeights:
    """Weights for each dimension of the lead score (0-100 total)."""
    technology_match: float = 30.0       # max 30
    hiring_activity: float = 20.0        # max 20
    company_size: float = 10.0           # max 10
    industry_relevance: float = 10.0     # max 10
    decision_maker_seniority: float = 15.0  # max 15
    growth_indicators: float = 10.0      # max 10
    consulting_likelihood: float = 5.0   # max 5

    @classmethod
    def defaults(cls) -> "ScoringWeights":
        return cls()

    def max_score(self) -> float:
        return sum([
            self.technology_match,
            self.hiring_activity,
            self.company_size,
            self.industry_relevance,
            self.decision_maker_seniority,
            self.growth_indicators,
            self.consulting_likelihood,
        ])


DEFAULT_WEIGHTS = ScoringWeights.defaults()

# ═══════════════════════════════════════════════════════════════
# 5.  PATHS   (relative to project root)
# ═══════════════════════════════════════════════════════════════

DATA_DIR = "data"
INPUT_DIR = f"{DATA_DIR}/input"
OUTPUT_DIR = f"{DATA_DIR}/output"
HISTORY_DIR = f"{DATA_DIR}/history"
TEMPLATES_DIR = "templates"
DOCS_DIR = "docs"

# ═══════════════════════════════════════════════════════════════
# 6.  DUPLICATE DETECTION
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# 7.  APPROVAL EMAIL  —  Outlook address for draft approval
# ═══════════════════════════════════════════════════════════════

APPROVAL_EMAIL = "aadil.shaikh@logixal.com"  # where approval digests are sent

# ═══════════════════════════════════════════════════════════════
# 8.  DUPLICATE DETECTION
# ═══════════════════════════════════════════════════════════════

DUPLICATE_COOLDOWN_DAYS = 90  # don't contact same person within this window
