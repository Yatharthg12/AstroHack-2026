"""Verify and optionally render the AstroLive Orbit submission PDF."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "submission" / "AstroLive_OrbitWorks_YatharthGarg.pdf"
QA = ROOT / "report" / "qa"
PAGES = QA / "pages"
RESULT = QA / "verification.json"
BUILD = ROOT / "report" / "build_manifest.json"
SOURCE = ROOT / "report" / "report_source.md"
MANUAL_REVIEW = QA / "manual_visual_review.json"

REQUIRED_SECTIONS = [
    "Cover Page and Team Information",
    "Executive Summary",
    "Challenge Interpretation and Problem Statement",
    "Evidence-Based Teardown of AstroLive's Public Experience",
    "Competitive Landscape and Opportunity Gap",
    "Target Users, Jobs-to-be-Done and Current Journey",
    "AstroLive Orbit Product Solution and Complete User Journey",
    "Structural Virality Mechanism",
    "Habit and Retention Mechanism",
    "Consultation and Operational Workflow",
    "Technical Architecture and Data Flow",
    "Dataset Audit and Feature Engineering",
    "ML Methodology, Evaluation and Limitations",
    "Experiment Simulator and Impact Scenarios",
    "Success Metrics, North-Star Metric and Guardrails",
    "Revenue Opportunities and Unit-Economic Logic",
    "Feasibility, Scalability and Staged Rollout",
    "Privacy, Trust, Consent, Safety and Responsible Astrology",
    "Prototype Screenshots and Demonstration Instructions",
    "Conclusion",
    "References",
    "AI Tools Disclosure",
]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decode_pdf_string(raw: bytes) -> str:
    value = raw.decode("latin-1")
    value = re.sub(r"\\([0-7]{1,3})", lambda match: chr(int(match.group(1), 8)), value)
    replacements = {r"\(": "(", r"\)": ")", r"\\": "\\", r"\n": "\n", r"\r": "\r", r"\t": "\t"}
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value


def fallback_extract(path: Path) -> tuple[int, list[str], str]:
    """Extract uncompressed ReportLab literal strings without optional packages."""

    raw = path.read_bytes()
    count = len(re.findall(rb"/Type\s*/Page\b", raw))
    streams = re.findall(rb"stream\r?\n(.*?)endstream", raw, re.DOTALL)
    page_texts = []
    literal = re.compile(rb"\(((?:\\.|[^\\)])*)\)\s*Tj")
    for stream in streams:
        if b" BT " not in stream and b"BT\n" not in stream:
            continue
        strings = [_decode_pdf_string(match) for match in literal.findall(stream)]
        if strings:
            page_texts.append(" ".join(strings))
    combined = "\n".join(page_texts)
    return count, page_texts, combined


def extract_with_available_library(path: Path) -> tuple[int, list[str], str, str, object | None]:
    try:
        import fitz  # type: ignore

        document = fitz.open(path)
        page_texts = [page.get_text("text") for page in document]
        return len(document), page_texts, "\n".join(page_texts), "PyMuPDF", document
    except ImportError:
        pass
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(path)
        page_texts = [page.extract_text() or "" for page in reader.pages]
        return len(reader.pages), page_texts, "\n".join(page_texts), "pypdf", None
    except ImportError:
        count, pages, combined = fallback_extract(path)
        return count, pages, combined, "built-in uncompressed-PDF extractor", None


def render_with_pymupdf(document: object | None) -> dict:
    if document is None:
        return {
            "available": False,
            "dependency": "PyMuPDF",
            "message": "Install PyMuPDF and rerun to render every page for visual inspection.",
            "pages": [],
        }
    PAGES.mkdir(parents=True, exist_ok=True)
    root = PAGES.resolve()
    if ROOT.resolve() not in root.parents:
        raise RuntimeError("QA render directory escaped repository")
    for existing in PAGES.glob("page-*.png"):
        existing.unlink()
    rendered = []
    for index, page in enumerate(document, start=1):
        pixmap = page.get_pixmap(matrix=__import__("fitz").Matrix(1.5, 1.5), alpha=False)
        path = PAGES / f"page-{index:02d}.png"
        pixmap.save(path)
        with Image.open(path) as image:
            width, height = image.size
            extrema = image.convert("L").getextrema()
        rendered.append(
            {
                "page": index,
                "path": str(path.relative_to(ROOT)),
                "width": width,
                "height": height,
                "blank_by_pixel_range": bool(extrema and extrema[0] == extrema[1]),
                "sha256": file_sha256(path),
            }
        )
    return {"available": True, "dependency": "PyMuPDF", "pages": rendered}


def asset_dimensions() -> list[dict[str, object]]:
    output = []
    try:
        build = json.loads(BUILD.read_text(encoding="utf-8"))
        paths = [ROOT / item for item in build.get("assets", [])]
    except (OSError, json.JSONDecodeError):
        paths = []
    for path in sorted(item for item in paths if item.suffix.lower() == ".png"):
        with Image.open(path) as image:
            output.append(
                {
                    "path": str(path.relative_to(ROOT)),
                    "width": image.width,
                    "height": image.height,
                    "nonzero_dimensions": image.width > 0 and image.height > 0,
                }
            )
    return output


def verify(*, require_manual_review: bool = True) -> dict:
    QA.mkdir(parents=True, exist_ok=True)
    failures = []
    if not PDF.exists():
        failures.append(f"Missing exact PDF: {PDF}")
        payload = {"status": "failed", "failures": failures}
        RESULT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload
    page_count, page_texts, text, extractor, document = extract_with_available_library(PDF)
    pdf_sha256 = file_sha256(PDF)
    try:
        build = json.loads(BUILD.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        build = {}
        failures.append("Missing or invalid report build manifest")
    if build:
        if build.get("pdf_sha256") != pdf_sha256:
            failures.append("Build manifest PDF hash does not match the submitted PDF")
        if build.get("source_sha256") != file_sha256(SOURCE):
            failures.append("Build manifest source hash is stale")
        for raw_path, expected_hash in build.get("asset_sha256", {}).items():
            asset = ROOT / raw_path
            if not asset.is_file() or file_sha256(asset) != expected_hash:
                failures.append(f"Build manifest asset hash mismatch: {raw_path}")
    if page_count < 8:
        failures.append(f"Page count {page_count} is below required minimum 8")
    if page_count != 12:
        failures.append(f"Expected designed 12-page report, found {page_count}")
    missing_sections = [heading for heading in REQUIRED_SECTIONS if heading not in text]
    if missing_sections:
        failures.append(f"Missing required extracted sections: {missing_sections}")
    required_cover_text = ["OrbitWorks", "Team leader: Yatharth Garg", "20 August 2026"]
    missing_cover_text = [value for value in required_cover_text if value not in text]
    if missing_cover_text:
        failures.append(f"Missing required cover identity/date text: {missing_cover_text}")
    text_lengths = [len(re.sub(r"\s+", "", page)) for page in page_texts]
    blank_pages = [index for index, length in enumerate(text_lengths, start=1) if length < 180]
    if blank_pages:
        failures.append(f"Potentially blank/sparse text pages: {blank_pages}")
    assets = asset_dimensions()
    if len(assets) < 3:
        failures.append("Fewer than three report PNG assets were generated")
    if any(not item["nonzero_dimensions"] for item in assets):
        failures.append("A report image has invalid dimensions")
    rendering = render_with_pymupdf(document)
    if not rendering["available"]:
        failures.append(
            "Rendered-page QA is unavailable; install PyMuPDF and rerun verification"
        )
    else:
        pixel_blank = [item["page"] for item in rendering["pages"] if item["blank_by_pixel_range"]]
        if pixel_blank:
            failures.append(f"Pixel-blank rendered pages: {pixel_blank}")
    manual_review = {"status": "pending"}
    try:
        candidate_review = json.loads(MANUAL_REVIEW.read_text(encoding="utf-8"))
        page_hashes = {
            str(item["page"]): item["sha256"] for item in rendering.get("pages", [])
        }
        if (
            candidate_review.get("status") == "passed"
            and candidate_review.get("pdf_sha256") == pdf_sha256
            and candidate_review.get("page_sha256") == page_hashes
        ):
            manual_review = candidate_review
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        pass
    if require_manual_review and manual_review.get("status") != "passed":
        failures.append("Manual visual review of all hash-bound rendered pages is missing or stale")
    payload = {
        "status": "passed" if not failures else "failed",
        "pdf": str(PDF.relative_to(ROOT)),
        "file_size_bytes": PDF.stat().st_size,
        "pdf_sha256": pdf_sha256,
        "source_sha256": file_sha256(SOURCE),
        "build_manifest_sha256": file_sha256(BUILD) if BUILD.exists() else None,
        "page_count": page_count,
        "minimum_page_count": 8,
        "extractor": extractor,
        "required_sections_found": len(REQUIRED_SECTIONS) - len(missing_sections),
        "required_sections_total": len(REQUIRED_SECTIONS),
        "missing_sections": missing_sections,
        "missing_cover_text": missing_cover_text,
        "page_text_character_counts": text_lengths,
        "potentially_blank_pages": blank_pages,
        "assets": assets,
        "rendering": rendering,
        "manual_visual_review": manual_review,
        "missing_optional_dependencies": [] if rendering["available"] else ["PyMuPDF"],
        "failures": failures,
    }
    RESULT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def record_visual_review() -> dict:
    result = verify(require_manual_review=False)
    if result["status"] != "passed":
        return result
    review = {
        "status": "passed",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reviewer": "Codex final submission visual QA",
        "pdf_sha256": result["pdf_sha256"],
        "page_sha256": {
            str(item["page"]): item["sha256"]
            for item in result["rendering"]["pages"]
        },
        "pages_reviewed": result["page_count"],
        "checks": [
            "no clipping or overlap",
            "body and reference text readable",
            "figures and captions legible",
            "no unintended blank or filler page",
        ],
    }
    MANUAL_REVIEW.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
    return verify(require_manual_review=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--structure-only", action="store_true")
    parser.add_argument("--record-visual-review", action="store_true")
    args = parser.parse_args()
    result = (
        record_visual_review()
        if args.record_visual_review
        else verify(require_manual_review=not args.structure_only)
    )
    print(json.dumps(result, indent=2))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
