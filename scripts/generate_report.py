"""Generate the exact AstroLive Orbit hackathon PDF from repository evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "report" / "report_source.md"
ASSETS = ROOT / "report" / "assets"
OUTPUT = ROOT / "submission" / "AstroLive_OrbitWorks_YatharthGarg.pdf"
EVALUATION = ROOT / "artifacts" / "models" / "evaluation.json"

NAVY = "#090D22"
SURFACE = "#171B3B"
VIOLET = "#8F71F4"
GOLD = "#E9B85E"
MINT = "#70D8B5"
WHITE = "#F5F1E8"
MUTED = "#A9ADC7"
GRID = "#303657"

EXPECTED_SCREENSHOTS = {
    "docs/screenshots/01_landing_desktop.png",
    "docs/screenshots/02_pulse_desktop.png",
    "docs/screenshots/03_bridge_desktop.png",
    "docs/screenshots/04_booking_confirmation_desktop.png",
    "docs/screenshots/05_astrologer_console_desktop.png",
    "docs/screenshots/06_circle_invitation_desktop.png",
    "docs/screenshots/07_mutual_circle_insight_desktop.png",
    "docs/screenshots/08_journey_desktop.png",
    "docs/screenshots/09_growth_cockpit_desktop.png",
    "docs/screenshots/10_experiment_simulator_desktop.png",
    "docs/screenshots/11_landing_mobile.png",
    "docs/screenshots/12_pulse_mobile.png",
    "docs/screenshots/13_growth_mobile.png",
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def browser_source_sha256() -> str:
    paths = [
        path for path in (ROOT / "app").rglob("*")
        if path.is_file() and path.suffix in {".py", ".html", ".css", ".js", ".svg"}
    ]
    paths.extend((ROOT / "artifacts" / "models").glob("*.json"))
    paths.extend((ROOT / "artifacts" / "models").glob("*.sha256"))
    paths.extend([
        ROOT / "data" / "demo" / "synthetic_orbit_users.csv",
        ROOT / "scripts" / "browser_smoke.py",
    ])
    digest = hashlib.sha256()
    for path in sorted({item.resolve() for item in paths if item.is_file()}):
        digest.update(path.relative_to(ROOT.resolve()).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def verified_browser_captures() -> tuple[list[Path], dict]:
    manifest_path = ROOT / "docs" / "browser_smoke_results.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("A successful browser evidence manifest is required") from exc
    listed = set(manifest.get("screenshots", []))
    evidence = manifest.get("screenshot_evidence", [])
    evidence_by_path = {
        item.get("path"): item for item in evidence if isinstance(item, dict)
    }
    mobile_checks = [
        item for item in manifest.get("overflow_checks", [])
        if "mobile" in str(item.get("page", ""))
    ]
    valid = (
        manifest.get("ok") is True
        and manifest.get("evidence_schema") == 2
        and not manifest.get("console_errors")
        and manifest.get("source_sha256") == browser_source_sha256()
        and listed == EXPECTED_SCREENSHOTS
        and set(evidence_by_path) == EXPECTED_SCREENSHOTS
        and mobile_checks
        and all(item.get("viewport") == 360 for item in mobile_checks)
        and "complete interactive journey repeated at 360px"
        in manifest.get("journey_steps", [])
    )
    captures: list[Path] = []
    if valid:
        for raw_path in sorted(EXPECTED_SCREENSHOTS):
            path = (ROOT / raw_path).resolve()
            item = evidence_by_path[raw_path]
            valid = (
                path.exists()
                and path.suffix.lower() == ".png"
                and (ROOT / "docs" / "screenshots").resolve() in path.parents
                and file_sha256(path) == item.get("sha256")
            )
            if valid:
                with Image.open(path) as capture:
                    valid = [capture.width, capture.height] == [
                        item.get("width"), item.get("height")
                    ]
                    if "_mobile" in path.stem:
                        valid = valid and capture.width == 360
            if not valid:
                break
            captures.append(path)
    if not valid or len(captures) != len(EXPECTED_SCREENSHOTS):
        raise RuntimeError(
            "Browser evidence is missing, stale, unbound, or not an exact 360px pass"
        )
    return captures, manifest


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = ["DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", "arialbd.ttf" if bold else "arial.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def base_image(width: int = 1200, height: int = 300) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (width, height), NAVY)
    draw = ImageDraw.Draw(image)
    for x in range(width):
        ratio = x / max(width - 1, 1)
        color = (
            int(9 + 15 * ratio),
            int(13 + 8 * ratio),
            int(34 + 30 * ratio),
        )
        draw.line((x, 0, x, height), fill=color)
    return image, draw


def save_dashboard_chart(path: Path) -> None:
    from app.analytics import growth_summary, load_demo_data

    metrics = growth_summary(load_demo_data())
    labels = ["WGU", "WAU", "MAU", "D1 retained", "D7 retained", "D30 retained"]
    values = [
        metrics["weekly_guided_users"],
        metrics["wau"],
        metrics["mau"],
        round(metrics["retention"]["d1"] * metrics["users"]),
        round(metrics["retention"]["d7"] * metrics["users"]),
        round(metrics["retention"]["d30"] * metrics["users"]),
    ]
    image, draw = base_image()
    draw.text((35, 20), "Synthetic Growth Cockpit snapshot (n=2,400)", font=font(24, True), fill=WHITE)
    max_value = max(values)
    chart_top, chart_bottom = 72, 245
    slot = 1110 / len(values)
    for index, (label, value) in enumerate(zip(labels, values)):
        x0 = 50 + index * slot + 20
        x1 = 50 + (index + 1) * slot - 20
        height = (value / max_value) * (chart_bottom - chart_top)
        fill = VIOLET if index < 3 else MINT
        draw.rounded_rectangle((x0, chart_bottom - height, x1, chart_bottom), 8, fill=fill)
        draw.text((x0, chart_bottom - height - 25), f"{value:,}", font=font(17, True), fill=WHITE)
        draw.text((x0, 258), label, font=font(15), fill=MUTED)
    image.save(path)


def save_model_chart(path: Path, evaluation: dict) -> None:
    image, draw = base_image()
    draw.text((35, 18), "Held-out model metrics — synthetic outcomes", font=font(24, True), fill=WHITE)
    tasks = [("Churn", evaluation["tasks"]["churn_risk"]["test_metrics"]), ("Intent", evaluation["tasks"]["consultation_intent"]["test_metrics"])]
    metric_names = [("ROC-AUC", "roc_auc"), ("PR-AUC", "pr_auc"), ("Recall", "recall"), ("F1", "f1")]
    colors = [VIOLET, GOLD]
    for row, (task, metrics) in enumerate(tasks):
        y = 93 + row * 92
        draw.text((35, y + 17), task, font=font(18, True), fill=WHITE)
        for index, (label, key) in enumerate(metric_names):
            x = 160 + index * 250
            value = float(metrics[key])
            draw.rounded_rectangle((x, y, x + 180, y + 27), 10, fill=GRID)
            draw.rounded_rectangle((x, y, x + 180 * value, y + 27), 10, fill=colors[row])
            draw.text((x, y + 34), f"{label} {value:.3f}", font=font(14), fill=MUTED)
    image.save(path)


def save_interval_chart(path: Path, scenario: dict) -> None:
    image, draw = base_image()
    draw.text((35, 18), "Seed-2026 scenario ranges — not measured impact", font=font(24, True), fill=WHITE)
    keys = [
        ("Retained users", "incremental_retained_users"),
        ("Consultations", "incremental_consultations"),
        ("Organic users", "incremental_organic_users"),
    ]
    all_values = [scenario["metrics"][key][bound] for _, key in keys for bound in ("p05", "p95")]
    low, high = min(all_values), max(all_values)
    axis_x0, axis_x1 = 240, 1140
    def px(value: float) -> float:
        return axis_x0 + (value - low) / (high - low) * (axis_x1 - axis_x0)
    for index, (label, key) in enumerate(keys):
        values = scenario["metrics"][key]
        y = 90 + index * 68
        draw.text((35, y - 11), label, font=font(17, True), fill=WHITE)
        draw.line((px(values["p05"]), y, px(values["p95"]), y), fill=MINT, width=8)
        draw.ellipse((px(values["median"]) - 9, y - 9, px(values["median"]) + 9, y + 9), fill=GOLD)
        draw.text((px(values["p05"]) - 18, y + 15), f"p05 {values['p05']:g}", font=font(13), fill=MUTED)
        draw.text((px(values["p95"]) - 35, y - 28), f"p95 {values['p95']:g}", font=font(13), fill=MUTED)
    draw.text((35, 270), "Gold dot = median; mint line = encoded 5th–95th percentile", font=font(14), fill=MUTED)
    image.save(path)


def save_flow_diagram(path: Path, architecture: bool = False) -> None:
    image, draw = base_image()
    if architecture:
        title = "Prototype architecture and governed evidence flow"
        nodes = ["Browser", "Flask + services", "SQLite demo state", "Synthetic CSV", "JSON + SHA models"]
    else:
        title = "Orbit's continuous guidance loop"
        nodes = ["Pulse", "Bridge", "Human consult", "Follow-up", "Circle"]
    draw.text((35, 18), title, font=font(24, True), fill=WHITE)
    count = len(nodes)
    box_w = 190
    gap = (1130 - count * box_w) / (count - 1)
    for index, label in enumerate(nodes):
        x = 35 + index * (box_w + gap)
        draw.rounded_rectangle((x, 110, x + box_w, 190), 18, fill=SURFACE, outline=VIOLET, width=3)
        bbox = draw.textbbox((0, 0), label, font=font(16, True))
        draw.text((x + (box_w - (bbox[2] - bbox[0])) / 2, 139), label, font=font(16, True), fill=WHITE)
        if index < count - 1:
            arrow_x = x + box_w + 8
            next_x = 35 + (index + 1) * (box_w + gap) - 8
            draw.line((arrow_x, 150, next_x, 150), fill=GOLD, width=4)
            draw.polygon([(next_x, 150), (next_x - 13, 142), (next_x - 13, 158)], fill=GOLD)
    subtitle = "Consent gates context and sharing" if not architecture else "No paid runtime API; explicit model/data fallback"
    draw.text((35, 240), subtitle, font=font(17), fill=MINT)
    image.save(path)


def save_evidence_taxonomy(path: Path) -> None:
    image, draw = base_image(1200, 300)
    draw.text((35, 18), "Evidence discipline used in the teardown", font=font(24, True), fill=WHITE)
    cards = [
        ("OBSERVED", "Visible on an opened public surface", MINT),
        ("PUBLISHER CLAIM", "First-party claim; not independently audited", GOLD),
        ("INFERENCE", "Product interpretation to test", VIOLET),
        ("NOT OBSERVED", "Absent only from reviewed public surfaces", MUTED),
    ]
    card_width = 266
    for index, (label, copy, accent) in enumerate(cards):
        x = 35 + index * 282
        draw.rounded_rectangle((x, 82, x + card_width, 240), 16, fill=SURFACE, outline=accent, width=3)
        draw.text((x + 18, 108), label, font=font(18, True), fill=accent)
        words = copy.split()
        lines, current = [], ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if draw.textlength(candidate, font=font(16)) <= card_width - 36:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        for line_index, line in enumerate(lines):
            draw.text((x + 18, 150 + line_index * 24), line, font=font(16), fill=WHITE)
    image.save(path)


def save_competitor_cards(path: Path) -> None:
    image, draw = base_image(1200, 300)
    draw.text((35, 18), "Point-in-time public capability scan", font=font(24, True), fill=WHITE)
    cards = [
        ("AstroLive", "500K+ Play tier", "Consult · content · reports"),
        ("AstroTalk", "100M+ Play tier", "Consult · live · commerce"),
        ("AstroSage", "50M+ Play tier", "Utilities · content · consult"),
        ("Astroyogi", "10M+ Play tier", "Consult · utilities · live"),
    ]
    for index, (name, tier, breadth) in enumerate(cards):
        x = 35 + index * 282
        draw.rounded_rectangle((x, 82, x + 266, 238), 16, fill=SURFACE, outline=VIOLET, width=2)
        draw.text((x + 18, 105), name, font=font(21, True), fill=WHITE)
        draw.text((x + 18, 148), tier, font=font(17, True), fill=GOLD)
        draw.text((x + 18, 187), breadth, font=font(15), fill=MINT)
    draw.text((35, 265), "Play install tiers are not active users; capability labels summarize cited public pages.", font=font(14), fill=MUTED)
    image.save(path)


def prototype_image() -> tuple[Path, str]:
    captures, _manifest = verified_browser_captures()
    placeholder = ASSETS / "prototype_evidence_placeholder.png"
    if placeholder.exists():
        placeholder.unlink()
    preferred = next((p for p in captures if "growth" in p.stem.lower()), captures[0])
    return preferred, (
        f"Verified browser-smoke capture: {preferred.name} "
        f"({len(captures)} hash-bound captures passed)"
    )


def build_assets() -> tuple[dict[int, Path], dict[int, str], dict]:
    ASSETS.mkdir(parents=True, exist_ok=True)
    evaluation = json.loads(EVALUATION.read_text(encoding="utf-8"))
    from app.services.experiments import simulate
    scenario = simulate({}, persist=False)
    save_dashboard_chart(ASSETS / "synthetic_dashboard.png")
    save_evidence_taxonomy(ASSETS / "evidence_taxonomy.png")
    save_competitor_cards(ASSETS / "competitor_scan.png")
    save_flow_diagram(ASSETS / "journey_loop.png")
    save_flow_diagram(ASSETS / "architecture_flow.png", architecture=True)
    save_model_chart(ASSETS / "model_performance.png", evaluation)
    save_interval_chart(ASSETS / "scenario_intervals.png", scenario)
    prototype, prototype_caption = prototype_image()
    images = {
        2: ASSETS / "synthetic_dashboard.png",
        3: ASSETS / "evidence_taxonomy.png",
        4: ASSETS / "competitor_scan.png",
        5: ASSETS / "journey_loop.png",
        7: ASSETS / "architecture_flow.png",
        9: ASSETS / "model_performance.png",
        10: ASSETS / "scenario_intervals.png",
        12: prototype,
    }
    captions = {
        2: "Figure 1. Repository-computed synthetic snapshot; values are not AstroLive KPIs.",
        3: "Figure 2. Claim taxonomy applied consistently across the public-surface review.",
        4: "Figure 3. Cited capability scan; Play install tiers are point-in-time, not active users.",
        5: "Figure 4. Closed-loop product journey; every sharing/context seam is consent-gated.",
        7: "Figure 5. Runtime and evidence architecture implemented in this repository.",
        9: "Figure 6. Held-out performance on simulated outcomes; no production validity claim.",
        10: "Figure 7. Default 10,000-trial scenario; percentiles are assumption-driven ranges.",
        12: f"Figure 8. {prototype_caption}.",
    }
    return images, captions, {"evaluation": evaluation, "scenario": scenario, "prototype_asset": str(prototype.relative_to(ROOT))}


def parse_source() -> list[list[tuple[str, str]]]:
    raw_pages = SOURCE.read_text(encoding="utf-8").split("<!-- PAGE -->")
    pages: list[list[tuple[str, str]]] = []
    for raw in raw_pages:
        blocks: list[tuple[str, str]] = []
        current_heading = ""
        body: list[str] = []
        for line in raw.strip().splitlines():
            if line.startswith("# Page "):
                continue
            if line.startswith("## "):
                if current_heading or any(item.strip() for item in body):
                    blocks.append((current_heading, "\n".join(body).strip()))
                current_heading = line[3:].strip()
                body = []
            else:
                body.append(line)
        if current_heading or any(item.strip() for item in body):
            blocks.append((current_heading, "\n".join(body).strip()))
        pages.append(blocks)
    if len(pages) != 12:
        raise ValueError(f"Report source must define exactly 12 pages, found {len(pages)}")
    return pages


def clean_text(value: str) -> str:
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = value.replace("→", "->").replace("≤", "<=").replace("≥", ">=")
    value = value.replace("₹", "INR ").replace("–", "-").replace("—", "-")
    return value.encode("cp1252", "replace").decode("cp1252")


def wrap_pdf(text: str, font_name: str, size: float, width: float) -> list[str]:
    words: list[str] = []
    for token in clean_text(text).split():
        while stringWidth(token, font_name, size) > width:
            cut = max(1, len(token) // 2)
            while cut < len(token) and stringWidth(token[: cut + 1], font_name, size) <= width:
                cut += 1
            while cut > 1 and stringWidth(token[:cut], font_name, size) > width:
                cut -= 1
            words.append(token[:cut])
            token = token[cut:]
        if token:
            words.append(token)
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or stringWidth(candidate, font_name, size) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def header_footer(pdf: canvas.Canvas, page: int) -> None:
    width, height = A4
    pdf.setFillColor(HexColor(NAVY))
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.setStrokeColor(HexColor(GRID))
    pdf.line(42, height - 38, width - 42, height - 38)
    pdf.line(42, 35, width - 42, 35)
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.setFillColor(HexColor(GOLD))
    pdf.drawString(42, height - 27, "ASTROLIVE ORBIT  /  ORBITWORKS")
    pdf.setFont("Helvetica", 7.5)
    pdf.setFillColor(HexColor(MUTED))
    pdf.drawRightString(width - 42, height - 27, "ASTROHACK 2026  |  EVIDENCE-LABELLED PROPOSAL")
    pdf.drawString(42, 21, "From one-time consultation to continuous guidance.")
    pdf.drawRightString(width - 42, 21, f"{page} / 12")


def image_dimensions(path: Path, max_height: float = 124) -> tuple[float, float]:
    page_width, _ = A4
    with Image.open(path) as image:
        max_width = page_width - 84
        scale = min(max_width / image.width, max_height / image.height)
        return image.width * scale, image.height * scale


def draw_image(
    pdf: canvas.Canvas,
    path: Path,
    caption: str,
    *,
    y: float = 54,
    max_height: float = 124,
) -> float:
    page_width, _ = A4
    width, height = image_dimensions(path, max_height)
    x = (page_width - width) / 2
    pdf.drawImage(ImageReader(str(path)), x, y, width, height, preserveAspectRatio=True, mask="auto")
    pdf.setFont("Helvetica-Oblique", 6.8)
    pdf.setFillColor(HexColor(MUTED))
    pdf.drawCentredString(page_width / 2, y - 10, clean_text(caption))
    return y + height + 12


def draw_cover(pdf: canvas.Canvas, blocks: list[tuple[str, str]]) -> None:
    width, height = A4
    pdf.setFillColor(HexColor(NAVY))
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.setStrokeColor(HexColor(VIOLET))
    for radius in (95, 145, 205):
        pdf.circle(width - 95, height - 135, radius, fill=0, stroke=1)
    pdf.setFillColor(HexColor(GOLD))
    pdf.circle(width - 95, height - 135, 8, fill=1, stroke=0)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(52, height - 70, "ASTROHACK 2026  /  ORBITWORKS")
    pdf.setFont("Helvetica", 7)
    pdf.setFillColor(HexColor(MUTED))
    pdf.drawString(52, height - 86, "Cover Page and Team Information")
    pdf.setFont("Helvetica-Bold", 39)
    pdf.setFillColor(HexColor(WHITE))
    pdf.drawString(52, height - 245, "AstroLive")
    pdf.setFillColor(HexColor(VIOLET))
    pdf.drawString(52, height - 289, "Orbit")
    pdf.setFont("Helvetica", 18)
    pdf.setFillColor(HexColor(GOLD))
    pdf.drawString(52, height - 326, "From one-time consultation to continuous guidance.")
    body = blocks[0][1].split("\n\n")
    y = height - 400
    for paragraph in body:
        if paragraph.startswith("AstroLive Orbit") or paragraph.startswith("From one-time"):
            continue
        size = 10 if len(paragraph) > 100 else 11
        pdf.setFont("Helvetica", size)
        pdf.setFillColor(HexColor(WHITE if len(paragraph) < 100 else MUTED))
        for line in wrap_pdf(paragraph, "Helvetica", size, width - 104):
            pdf.drawString(52, y, line)
            y -= 14
        y -= 8
    pdf.setFillColor(HexColor(SURFACE))
    pdf.roundRect(52, 70, width - 104, 73, 12, fill=1, stroke=0)
    pdf.setFillColor(HexColor(MINT))
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(67, 118, "WORKING PROTOTYPE  /  SYNTHETIC ANALYTICS  /  HUMAN-GUIDANCE FIRST")
    pdf.setFillColor(HexColor(MUTED))
    pdf.setFont("Helvetica", 8)
    pdf.drawString(67, 94, "Public facts cited. Publisher claims qualified. Inferences, simulations, and synthetic data labelled.")
    pdf.setFillColor(HexColor(GOLD))
    pdf.drawRightString(width - 52, 38, "01 / 12")


def draw_standard_page(
    pdf: canvas.Canvas,
    page: int,
    blocks: list[tuple[str, str]],
    image_path: Path | None,
    caption: str | None,
) -> None:
    width, height = A4
    header_footer(pdf, page)
    image_max_height = 190 if page == 12 else 124
    image_height = (
        image_dimensions(image_path, image_max_height)[1] if image_path else 0
    )
    bottom = 54 + image_height + 16 if image_path else 52
    y = height - 61
    font_size = 8.75 if page != 12 else 8.5
    leading = 11.2 if page != 12 else 10.5
    paragraph_gap = 4.5 if page != 12 else 3.0
    for heading, body in blocks:
        pdf.setFillColor(HexColor(GOLD if y > height - 100 else VIOLET))
        pdf.setFont("Helvetica-Bold", 14 if y > height - 100 else 11.5)
        for line in wrap_pdf(heading, "Helvetica-Bold", 14 if y > height - 100 else 11.5, width - 84):
            pdf.drawString(42, y, line)
            y -= 17 if y > height - 115 else 14
        y -= 4
        for paragraph in [item.strip() for item in body.split("\n\n") if item.strip()]:
            label_color = MINT if re.match(r"^(OBSERVED|PUBLISHER CLAIM|INFERENCE|SYNTHETIC|SIMULATION|REPOSITORY-VERIFIED)", paragraph) else WHITE
            pdf.setFillColor(HexColor(label_color))
            pdf.setFont("Helvetica", font_size)
            for line in wrap_pdf(paragraph, "Helvetica", font_size, width - 84):
                if y < bottom:
                    raise ValueError(f"Page {page} source overflows at: {paragraph[:60]}")
                pdf.drawString(42, y, line)
                y -= leading
            y -= paragraph_gap
        y -= 3
    if image_path:
        # Centre each figure in the remaining space instead of pinning a tiny
        # chart to the footer and leaving an accidental visual void.
        available = max(0, y - 18 - 54)
        image_y = 54 + max(0, (available - image_height) / 2)
        draw_image(
            pdf,
            image_path,
            caption or "",
            y=image_y,
            max_height=image_max_height,
        )
    # A small provenance strip makes sparse text-only space purposeful.
    elif y - bottom > 24:
        pdf.setFillColor(HexColor(SURFACE))
        pdf.roundRect(42, bottom, width - 84, min(28, y - bottom - 5), 6, fill=1, stroke=0)
        pdf.setFillColor(HexColor(MUTED))
        pdf.setFont("Helvetica", 6.8)
        pdf.drawString(52, bottom + 9, "Evidence discipline: observed public facts are cited; repository results are reproducible; scenarios are not forecasts.")


def generate() -> Path:
    images, captions, evidence = build_assets()
    pages = parse_source()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(OUTPUT), pagesize=A4, pageCompression=0)
    pdf.setTitle("AstroLive Orbit — OrbitWorks — AstroHack 2026")
    pdf.setAuthor("OrbitWorks — Yatharth Garg")
    pdf.setSubject("Continuous guidance product proposal and working prototype evidence")
    for index, blocks in enumerate(pages, start=1):
        if index == 1:
            draw_cover(pdf, blocks)
        else:
            draw_standard_page(pdf, index, blocks, images.get(index), captions.get(index))
        pdf.showPage()
    pdf.save()
    asset_paths = [
        path for path in sorted(set(images.values()))
        if ROOT in path.resolve().parents
    ]
    manifest = {
        "output": str(OUTPUT.relative_to(ROOT)),
        "pages": len(pages),
        "source": str(SOURCE.relative_to(ROOT)),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_sha256": file_sha256(SOURCE),
        "generator_sha256": file_sha256(Path(__file__)),
        "pdf_sha256": file_sha256(OUTPUT),
        "browser_manifest_sha256": file_sha256(
            ROOT / "docs" / "browser_smoke_results.json"
        ),
        "assets": [str(path.relative_to(ROOT)) for path in asset_paths],
        "asset_sha256": {
            str(path.relative_to(ROOT)): file_sha256(path) for path in asset_paths
        },
        "evaluation_split": evidence["evaluation"]["split"],
        "scenario_seed": evidence["scenario"]["inputs"]["seed"],
        "scenario_trials": evidence["scenario"]["inputs"]["trials"],
        "revenue_supported": evidence["scenario"]["revenue_supported"],
        "prototype_asset": evidence["prototype_asset"],
    }
    (ROOT / "report" / "build_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {OUTPUT} ({len(pages)} pages)")
    return OUTPUT


if __name__ == "__main__":
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    generate()
