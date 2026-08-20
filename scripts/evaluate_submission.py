"""Evidence-based machine-readable AstroHack judging-dimension evaluator."""

from __future__ import annotations

import argparse
import json
import re
import sys
from tempfile import TemporaryDirectory
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class Check:
    label: str
    test: Callable[[], bool]
    evidence: str


def exists(relative: str, minimum_bytes: int = 1) -> bool:
    path = ROOT / relative
    return path.is_file() and path.stat().st_size >= minimum_bytes


def contains(relative: str, *terms: str) -> bool:
    try:
        value = (ROOT / relative).read_text(encoding="utf-8").lower()
    except (FileNotFoundError, UnicodeDecodeError, OSError):
        return False
    return all(term.lower() in value for term in terms)


def count_templates() -> int:
    return len(list((ROOT / "app" / "templates").rglob("*.html")))


def test_count() -> int:
    total = 0
    for path in (ROOT / "tests").glob("test_*.py"):
        total += path.read_text(encoding="utf-8").count("def test_")
    return total


def pdf_pages() -> int:
    path = ROOT / "submission" / "AstroLive_OrbitWorks_YatharthGarg.pdf"
    if not path.exists():
        return 0
    raw = path.read_bytes()
    # Reliable for ReportLab output and deliberately excludes the /Pages node.
    return len(re.findall(rb"/Type\s*/Page(?!s)\b", raw))


def dynamic_smoke() -> bool:
    try:
        from app import create_app
        with TemporaryDirectory(prefix="orbit-evaluator-") as temporary:
            application = create_app({
                "TESTING": True,
                "SECRET_KEY": "evaluator-secret-not-for-production",
                "SECRET_KEY_IS_FALLBACK": False,
                "DATABASE": str(Path(temporary) / "evaluator.db"),
            })
            with application.test_client() as client:
                return all(client.get(path).status_code == 200 for path in ("/", "/onboarding", "/growth", "/experiments", "/privacy", "/api/health"))
    except Exception:
        return False


def browser_evidence_passed() -> bool:
    try:
        payload = json.loads(
            (ROOT / "docs" / "browser_smoke_results.json").read_text(encoding="utf-8")
        )
        screenshots = [ROOT / str(path) for path in payload["screenshots"]]
        mobile_checks = [
            item for item in payload["overflow_checks"]
            if "mobile" in str(item.get("page", ""))
        ]
        return (
            payload.get("ok") is True
            and not payload.get("console_errors")
            and len(screenshots) >= 10
            and all(path.is_file() and path.suffix.lower() == ".png" for path in screenshots)
            and mobile_checks
            and all(item.get("viewport") == 360 for item in mobile_checks)
            and "complete interactive journey repeated at 360px" in payload.get("journey_steps", [])
        )
    except (FileNotFoundError, KeyError, TypeError, json.JSONDecodeError):
        return False


def pdf_evidence_passed() -> bool:
    try:
        payload = json.loads(
            (ROOT / "report" / "qa" / "verification.json").read_text(encoding="utf-8")
        )
        rendering = payload["rendering"]
        pages = rendering["pages"]
        return (
            payload.get("status") == "passed"
            and payload.get("page_count") == 12
            and payload.get("required_sections_found") == payload.get("required_sections_total")
            and rendering.get("available") is True
            and len(pages) == 12
            and not any(page.get("blank_by_pixel_range") for page in pages)
            and payload.get("manual_visual_review", {}).get("status") == "passed"
            and not payload.get("failures")
        )
    except (FileNotFoundError, KeyError, TypeError, json.JSONDecodeError):
        return False


def artifact_metrics_present() -> bool:
    path = ROOT / "artifacts" / "models" / "evaluation.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        tasks = payload["tasks"]
        required = {"accuracy", "precision", "recall", "f1", "roc_auc", "pr_auc", "brier", "confusion_matrix"}
        return all(required <= set(tasks[name]["test_metrics"]) for name in ("churn_risk", "consultation_intent"))
    except (FileNotFoundError, KeyError, TypeError, json.JSONDecodeError):
        return False


def rubric() -> dict[str, list[Check]]:
    return {
        "problem_comprehension": [
            Check("challenge evidence", lambda: contains("docs/PRODUCT_TEARDOWN.md", "observed", "inference"), "docs/PRODUCT_TEARDOWN.md labels evidence"),
            Check("official sources", lambda: contains("docs/REFERENCES.md", "unstop", "astrolive"), "docs/REFERENCES.md"),
            Check("competitor review", lambda: contains("docs/PRODUCT_TEARDOWN.md", "astrotalk", "astrosage", "astroyogi"), "three named competitors"),
            Check("closed-loop thesis", lambda: contains("README.md", "continuous", "guidance"), "README product thesis"),
            Check("observed vs inferred", lambda: contains("docs/PRODUCT_TEARDOWN.md", "not observed", "inference"), "claim taxonomy"),
            Check("no invented metrics", lambda: contains("docs/REFERENCES.md", "company-reported"), "source qualification"),
            Check("user jobs", lambda: contains("README.md", "journey"), "README journey"),
            Check("human role", lambda: contains("docs/PRIVACY_AND_ETHICS.md", "human"), "ethics guidance"),
            Check("differentiation", lambda: contains("README.md", "circle", "bridge", "pulse"), "closed-loop modules"),
            Check("limitations", lambda: contains("README.md", "limitations"), "README limitations"),
        ],
        "solution_design": [
            Check("landing", lambda: exists("app/templates/landing.html", 500), "landing template"),
            Check("onboarding", lambda: exists("app/templates/onboarding.html", 500), "minimal onboarding"),
            Check("Pulse", lambda: exists("app/templates/pulse.html", 500), "daily ritual"),
            Check("Bridge", lambda: exists("app/templates/bridge.html", 500), "consultation preparation"),
            Check("console", lambda: exists("app/templates/console.html", 500), "astrologer view"),
            Check("Journey", lambda: exists("app/templates/journey.html", 500), "continuity timeline"),
            Check("Circle", lambda: exists("app/templates/circle.html", 500) and exists("app/templates/circle_invite.html", 500), "two-sided referral"),
            Check("Growth", lambda: exists("app/templates/growth.html", 500), "operator dashboard"),
            Check("simulator", lambda: exists("app/templates/experiments.html", 500), "Monte Carlo UI"),
            Check("accessible system", lambda: contains("app/static/css/orbit.css", "prefers-reduced-motion", ":focus"), "focus and reduced motion CSS"),
        ],
        "prototype_functionality": [
            Check("dynamic public smoke", dynamic_smoke, "Flask test-client smoke"),
            Check("application factory", lambda: contains("app/__init__.py", "create_app"), "factory"),
            Check("idempotent database", lambda: contains("app/db.py", "create table if not exists"), "SQLite schema"),
            Check("JSON APIs", lambda: contains("app/routes/api.py", "/check-ins", "/referrals", "/experiments"), "interactive APIs"),
            Check("secure token", lambda: contains("app/services/referrals.py", "secrets.token_urlsafe"), "server-side random token"),
            Check("follow-up", lambda: contains("app/services/consultations.py", "create_followup"), "post-consultation state"),
            Check("comprehensive tests", lambda: test_count() >= 25, f"{test_count()} test functions"),
            Check("verified browser journey", browser_evidence_passed, "successful desktop and exact-360 browser manifest"),
            Check("health endpoint", lambda: contains("app/routes/api.py", "/health"), "health API"),
            Check("reset workflow", lambda: contains("app/routes/api.py", "/reset"), "local deletion"),
        ],
        "uniqueness": [
            Check("structural referral", lambda: contains("app/services/referrals.py", "consented_completion", "mutual_insight"), "unlock after mutual consent"),
            Check("prepared handoff", lambda: contains("app/services/consultations.py", "console_context"), "consented console handoff"),
            Check("habit loop", lambda: contains("app/services/journey.py", "streak", "micro_action"), "Pulse rhythm"),
            Check("follow-up continuity", lambda: contains("app/services/consultations.py", "scheduled_checkin"), "local follow-up"),
            Check("not a generic horoscope", lambda: contains("README.md", "not", "horoscope"), "differentiation statement"),
            Check("transparent reflections", lambda: contains("app/services/journey.py", "no birth-chart inference"), "reason shown"),
            Check("privacy-safe URL", lambda: contains("tests/test_product_flow.py", "birth", "referral"), "non-disclosure test"),
            Check("organic loop metrics", lambda: contains("app/analytics/metrics.py", "k_factor"), "K-factor analytics"),
            Check("operator simulation", lambda: contains("app/services/experiments.py", "monte carlo"), "editable scenario engine"),
            Check("product teardown gap", lambda: contains("docs/PRODUCT_TEARDOWN.md", "closed loop"), "evidence-grounded gap"),
        ],
        "scalability_and_feasibility": [
            Check("modular boundaries", lambda: all((ROOT / path).is_dir() for path in ("app/routes", "app/services", "app/ml", "app/analytics")), "modular package layout"),
            Check("deployment image", lambda: exists("Dockerfile", 100), "Dockerfile"),
            Check("Render config", lambda: exists("render.yaml", 50), "render.yaml"),
            Check("Gunicorn", lambda: contains("Procfile", "gunicorn"), "production command"),
            Check("environment config", lambda: exists(".env.example", 20), "environment example"),
            Check("safe models", lambda: exists("artifacts/models/churn_risk.json") and exists("artifacts/models/churn_risk.sha256"), "JSON+SHA artifact"),
            Check("graceful model fallback", lambda: contains("app/ml/inference.py", "artifact unavailable"), "fallback inference"),
            Check("security headers", lambda: contains("app/__init__.py", "content-security-policy", "x-frame-options"), "security middleware"),
            Check("data deletion", lambda: contains("app/services/journey.py", "reset_current_user"), "cascade reset"),
            Check("architecture docs", lambda: contains("docs/ARCHITECTURE.md", "data flow"), "architecture documentation"),
        ],
        "report_clarity": [
            Check("exact PDF", lambda: exists("submission/AstroLive_OrbitWorks_YatharthGarg.pdf", 10_000), "required filename"),
            Check("minimum pages", lambda: pdf_pages() >= 8, f"{pdf_pages()} PDF pages"),
            Check("editable source", lambda: exists("report/report_source.md", 1000), "editable report source"),
            Check("generator", lambda: exists("scripts/generate_report.py", 1000), "Python generator"),
            Check("charts", lambda: len(list((ROOT / "report" / "assets").glob("*.png"))) >= 3, "generated visual assets"),
            Check("screenshots", browser_evidence_passed, "manifest-gated prototype captures"),
            Check("references", lambda: contains("docs/REFERENCES.md", "accessed"), "source register"),
            Check("AI disclosure", lambda: contains("report/report_source.md", "openai chatgpt", "openai codex"), "truthful AI disclosure"),
            Check("demo script", lambda: exists("docs/DEMO_SCRIPT.md", 500), "three-minute walkthrough"),
            Check("PDF QA", pdf_evidence_passed, "passed render/text/page QA evidence"),
        ],
        "potential_business_impact": [
            Check("north star", lambda: contains("app/analytics/metrics.py", "weekly_guided_users"), "Weekly Guided Users"),
            Check("retention", lambda: contains("app/analytics/metrics.py", "retained_d1", "retained_d7", "retained_d30"), "D1/D7/D30"),
            Check("funnel", lambda: contains("app/analytics/metrics.py", "activation_funnel"), "activation funnel"),
            Check("referral economics", lambda: contains("app/analytics/metrics.py", "k_factor"), "viral coefficient"),
            Check("10k trials", lambda: contains("app/services/experiments.py", '"trials": 10000'), "minimum trial default"),
            Check("uncertainty ranges", lambda: contains("app/services/experiments.py", "p05", "p95", "median"), "scenario intervals"),
            Check("sensitivity", lambda: contains("app/services/experiments.py", "sensitivity"), "driver ranking"),
            Check("no invented revenue", lambda: contains("app/services/experiments.py", "revenue_supported"), "conditional revenue"),
            Check("actual ML metrics", artifact_metrics_present, "full held-out metrics"),
            Check("experimentation plan", lambda: contains("docs/EXPERIMENTATION.md", "guardrail", "hypothesis"), "measurement plan"),
        ],
    }


def evaluate() -> dict:
    dimensions = {}
    for name, checks in rubric().items():
        passed, gaps = [], []
        for check in checks:
            try:
                outcome = bool(check.test())
            except Exception:
                outcome = False
            (passed if outcome else gaps).append(check.evidence if outcome else check.label)
        dimensions[name] = {"score": len(passed), "out_of": len(checks), "evidence": passed, "gaps": gaps}
    minimum = min(value["score"] for value in dimensions.values())
    return {
        "evaluator": "AstroLive Orbit repository-evidence rubric v1",
        "dimensions": dimensions,
        "minimum_score": minimum,
        "passes_target": minimum >= 8,
        "note": "Scores reflect checkable repository evidence; they are not organizer judging results.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate()
    rendered = json.dumps(result, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if result["passes_target"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
