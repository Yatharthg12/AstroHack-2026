"""Exercise the complete Orbit journey in headless Chrome at desktop and mobile sizes.

This script starts an isolated local Flask server, drives real browser controls,
captures curated screenshots, checks horizontal overflow and console errors, and
deletes its temporary profile/database on exit. It never touches a user's normal
``instance/orbit.db``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import socket
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin
from uuid import uuid4

from PIL import Image

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from werkzeug.serving import make_server


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402


MAIN_PATHS = [
    "/", "/onboarding", "/pulse", "/bridge", "/booking", "/console",
    "/follow-up", "/circle", "/journey", "/growth", "/experiments", "/privacy",
]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def browser_source_sha256() -> str:
    """Bind browser evidence to the app, synthetic data, and model artifacts."""

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


class LocalServer(threading.Thread):
    def __init__(self, application, host: str, port: int):
        super().__init__(daemon=True)
        self.server = make_server(host, port, application, threaded=True)

    def run(self) -> None:
        self.server.serve_forever()

    def stop(self) -> None:
        self.server.shutdown()


def available_port() -> int:
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", 0))
        return int(connection.getsockname()[1])


def chrome_binary() -> Path:
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError("Chrome or Edge was not found in a standard Windows location.")


def chrome_options(binary: Path, profile: Path, downloads: Path, headless: bool) -> Options:
    """Build an isolated, nonblocking browser profile for explicit wait-driven QA."""

    options = Options()
    options.binary_location = str(binary)
    options.page_load_strategy = "none"
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--force-device-scale-factor=1")
    options.add_argument(f"--user-data-dir={profile}")
    options.add_argument("--window-size=1440,1000")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    options.add_experimental_option("prefs", {
        "download.default_directory": str(downloads.resolve()),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    })
    return options


def click(driver, wait: WebDriverWait, selector: str) -> None:
    element = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
    driver.execute_script("arguments[0].scrollIntoView({block:'center',behavior:'instant'});", element)
    element.click()


def exercise_link_and_navigate(driver, wait: WebDriverWait, selector: str, base: str) -> None:
    """Exercise a visible link click without Selenium blocking on native navigation."""

    element = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
    href = element.get_attribute("href")
    if not href:
        raise AssertionError(f"Navigation control has no href: {selector}")
    driver.execute_script(
        "window.__orbitLinkClicked=false;arguments[0].addEventListener('click',event=>{"
        "event.preventDefault();window.__orbitLinkClicked=true;},{once:true});",
        element,
    )
    element.click()
    if not driver.execute_script("return window.__orbitLinkClicked===true"):
        raise AssertionError(f"Navigation click did not fire: {selector}")
    driver.get(urljoin(base, href))


def fill(driver, selector: str, value: str) -> None:
    element = driver.find_element(By.CSS_SELECTOR, selector)
    element.clear()
    element.send_keys(value)


def wait_text(wait: WebDriverWait, selector: str, fragment: str) -> None:
    wait.until(lambda browser: fragment.lower() in browser.find_element(By.CSS_SELECTOR, selector).text.lower())


def set_exact_mobile_viewport(driver, width: int = 360, height: int = 800) -> None:
    """Use device emulation because headless Chrome clamps native windows to 500px."""

    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": width,
            "height": height,
            "deviceScaleFactor": 1,
            "mobile": True,
        },
    )
    actual = driver.execute_script("return {width: innerWidth, height: innerHeight};")
    if actual["width"] != width:
        raise AssertionError(f"Requested {width}px viewport, browser reported {actual}")


def clear_mobile_viewport(driver, width: int = 1440, height: int = 1000) -> None:
    driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
    driver.set_window_size(width, height)


def assert_no_overflow(driver, label: str, results: dict) -> None:
    dimensions = driver.execute_script(
        "return {viewport: window.innerWidth, scroll: document.documentElement.scrollWidth};"
    )
    overflow = dimensions["scroll"] - dimensions["viewport"]
    results["overflow_checks"].append({"page": label, **dimensions, "overflow_px": overflow})
    if overflow > 1:
        raise AssertionError(f"Horizontal overflow on {label}: {overflow}px")


def screenshot(driver, output: Path, name: str, results: dict) -> None:
    destination = output / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not driver.save_screenshot(str(destination)):
        raise RuntimeError(f"Could not capture {destination}")
    results["screenshots"].append(f"docs/screenshots/{name}")


def browser_logs(driver) -> list[dict]:
    failures = []
    for entry in driver.get_log("browser"):
        if entry.get("level") in {"SEVERE", "ERROR"}:
            failures.append({"level": entry.get("level"), "message": entry.get("message")})
    return failures


def run_smoke(headless: bool = True) -> dict:
    run_id = uuid4().hex[:10]
    scratch = ROOT / "tmp" / f"browser-smoke-{run_id}"
    profile = scratch / "chrome-profile"
    guest_profile = scratch / "guest-profile"
    mobile_guest_profile = scratch / "mobile-guest-profile"
    downloads = scratch / "downloads"
    guest_downloads = scratch / "guest-downloads"
    database = scratch / "orbit-browser.db"
    screenshots = scratch / "screenshots"
    published_screenshots = ROOT / "docs" / "screenshots"
    for directory in (profile, guest_profile, mobile_guest_profile, downloads, guest_downloads, screenshots):
        directory.mkdir(parents=True, exist_ok=True)

    port = available_port()
    base = f"http://127.0.0.1:{port}"
    application = create_app({
        "TESTING": False,
        "SECRET_KEY": "browser-smoke-secret-not-for-production",
        "SECRET_KEY_IS_FALLBACK": False,
        "DATABASE": str(database),
        "SESSION_COOKIE_SECURE": False,
        "RATE_LIMIT_PER_MINUTE": 1000,
    })
    server = LocalServer(application, "127.0.0.1", port)
    server.start()

    binary = chrome_binary()
    options = chrome_options(binary, profile, downloads, headless)

    results = {
        "ok": False,
        "browser": binary.name,
        "base_url": "isolated localhost server",
        "journey_steps": [],
        "screenshots": [],
        "overflow_checks": [],
        "downloads": [],
        "console_errors": [],
        "accessibility_checks": [],
        "main_paths": MAIN_PATHS,
        "last_stage": "browser-start",
    }
    driver = None
    guest_driver = None
    try:
        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, 15)
        driver.set_window_size(1440, 1000)

        results["last_stage"] = "landing-load"
        driver.get(base + "/")
        wait.until(EC.title_contains("AstroLive Orbit"))
        assert "continuous guidance" in driver.find_element(By.TAG_NAME, "body").text.lower()
        assert_no_overflow(driver, "landing-desktop", results)
        screenshot(driver, screenshots, "01_landing_desktop.png", results)
        results["journey_steps"].append("landing")

        driver.execute_cdp_cmd(
            "Emulation.setEmulatedMedia",
            {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]},
        )
        reduced = driver.execute_script(
            "return {matches:matchMedia('(prefers-reduced-motion: reduce)').matches,"
            "scroll:getComputedStyle(document.documentElement).scrollBehavior};"
        )
        if not reduced["matches"] or reduced["scroll"] != "auto":
            raise AssertionError(f"Reduced-motion behavior was not respected: {reduced}")
        driver.execute_cdp_cmd(
            "Emulation.setEmulatedMedia",
            {"features": [{"name": "prefers-reduced-motion", "value": "no-preference"}]},
        )
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.TAB)
        focus = driver.execute_script(
            "const e=document.activeElement,s=getComputedStyle(e);return {tag:e.tagName,href:e.getAttribute('href'),"
            "visible:!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length),outline:s.outlineStyle,width:s.outlineWidth};"
        )
        if not focus["visible"] or focus["tag"] == "BODY" or focus["outline"] == "none":
            raise AssertionError(f"Keyboard focus was not visibly exposed: {focus}")
        results["accessibility_checks"].extend([
            {"check": "prefers-reduced-motion", "passed": True, **reduced},
            {"check": "keyboard-focus-visible", "passed": True, **focus},
        ])

        results["last_stage"] = "onboarding-navigation"
        exercise_link_and_navigate(driver, wait, 'a[href="/onboarding"]', base)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-onboarding-form]")))
        results["last_stage"] = "onboarding-display-name"
        fill(driver, "#display_name", "Judge Demo")
        results["last_stage"] = "onboarding-birth-date"
        driver.execute_script(
            "const e=document.querySelector('#birth_date');e.value='1994-08-17';e.dispatchEvent(new Event('change',{bubbles:true}));"
        )
        results["last_stage"] = "onboarding-birth-city"
        fill(driver, "#birth_city", "Jaipur")
        results["last_stage"] = "onboarding-focus"
        click(driver, wait, 'label[for="focus_1"]')
        results["last_stage"] = "onboarding-preference"
        Select(driver.find_element(By.ID, "communication_preference")).select_by_value("concise")
        results["last_stage"] = "onboarding-save-consent"
        click(driver, wait, 'label[for="save_consent"]')
        results["last_stage"] = "onboarding-circle-consent"
        click(driver, wait, 'label[for="circle_consent"]')
        results["last_stage"] = "onboarding-validity"
        invalid = driver.execute_script(
            "return [...document.querySelector('[data-onboarding-form]').elements].filter(e=>!e.checkValidity()).map(e=>({name:e.name,type:e.type,value:e.value,checked:e.checked}));"
        )
        if invalid:
            raise AssertionError(f"Onboarding form remained invalid: {invalid}")
        results["last_stage"] = "onboarding-submit-listener"
        driver.execute_script(
            "window.__orbitSubmitSeen=false;window.__orbitSubmitError=null;"
            "const f=document.querySelector('[data-onboarding-form]');"
            "f.addEventListener('submit',event=>{event.preventDefault();window.__orbitSubmitSeen=true;"
            "fetch(f.action,{method:'POST',body:new FormData(f),credentials:'same-origin'})"
            ".then(response=>{if(!response.ok)throw new Error(`Onboarding HTTP ${response.status}`);"
            "location.assign(response.url);}).catch(error=>{window.__orbitSubmitError=String(error);});},{once:true});"
        )
        results["last_stage"] = "onboarding-submit-click"
        click(driver, wait, '[data-onboarding-form] button[type="submit"]')
        results["last_stage"] = "onboarding-response"
        try:
            wait.until(EC.url_contains("/pulse"))
        except Exception as exc:
            probe = driver.execute_script(
                "return {url:location.href,submitSeen:window.__orbitSubmitSeen,"
                "error:window.__orbitSubmitError,"
                "valid:document.querySelector('[data-onboarding-form]')?.checkValidity(),"
                "active:document.activeElement?.outerHTML};"
            )
            raise AssertionError(f"Onboarding did not navigate: {probe}") from exc
        results["journey_steps"].append("onboarding")
        results["last_stage"] = "pulse"

        click(driver, wait, 'label[for="mood_grounded"]')
        driver.execute_script(
            "const e=document.querySelector('#confidence');e.value='4';e.dispatchEvent(new Event('input',{bubbles:true}));"
        )
        fill(driver, "#concern", "I want to compare two career paths without rushing the decision.")
        click(driver, wait, '[data-pulse-form] button[type="submit"]')
        wait_text(wait, "[data-form-status]", "saved privately")
        wait_text(wait, "[data-reflection-why]", "no birth-chart inference")
        wait_text(wait, "[data-streak-label]", "1 day streak")
        wait.until(lambda browser: len(browser.find_elements(By.CSS_SELECTOR, "[data-week-day].done")) >= 1)
        click(driver, wait, '[data-feedback="true"]')
        assert_no_overflow(driver, "pulse-desktop", results)
        screenshot(driver, screenshots, "02_pulse_desktop.png", results)
        results["journey_steps"].extend(["pulse", "saved check-in", "relevance feedback"])

        results["last_stage"] = "bridge"
        driver.get(base + "/bridge")
        if driver.find_element(By.CSS_SELECTOR, "[data-revoke-brief]").is_displayed():
            raise AssertionError("Withdraw control was visible before brief approval.")
        fill(driver, "#context", "I am weighing a stable role against a role with more learning and uncertainty.")
        fill(driver, "#outcome", "A calm set of trade-offs and one reversible next step.")
        fill(driver, "#questions", "Which trade-offs deserve more attention?\nWhat could I test before deciding?")
        Select(driver.find_element(By.ID, "language")).select_by_visible_text("English")
        Select(driver.find_element(By.ID, "mode")).select_by_value("audio")
        Select(driver.find_element(By.ID, "urgency")).select_by_value("soon")
        click(driver, wait, 'label[for="include_checkins"]')
        click(driver, wait, '[data-bridge-form] button[type="submit"]')
        wait.until(lambda browser: bool(browser.find_element(By.CSS_SELECTOR, "[data-bridge-form]").get_attribute("data-brief-id")))
        if driver.find_element(By.CSS_SELECTOR, "[data-revoke-brief]").is_displayed():
            raise AssertionError("Withdraw control was visible for an unapproved draft.")
        screenshot(driver, screenshots, "03_bridge_desktop.png", results)
        click(driver, wait, 'label[for="approve_brief"]')
        wait.until(lambda browser: browser.find_element(By.CSS_SELECTOR, "[data-book-cta]").get_attribute("aria-disabled") == "false")
        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "[data-revoke-brief]")))
        exercise_link_and_navigate(driver, wait, "[data-book-cta]", base)
        wait.until(EC.url_contains("/booking"))
        results["journey_steps"].extend(["consultation draft", "explicit brief approval"])

        results["last_stage"] = "booking"
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="astrologer_id"]:checked')))
        Select(driver.find_element(By.ID, "booking_mode")).select_by_value("audio")
        click(driver, wait, '[data-booking-form] button[type="submit"]')
        wait.until(lambda browser: browser.find_element(By.CSS_SELECTOR, "[data-booking-confirmation]").is_displayed())
        screenshot(driver, screenshots, "04_booking_confirmation_desktop.png", results)
        results["journey_steps"].append("demo booking")

        results["last_stage"] = "console"
        driver.get(base + "/console")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-console]")))
        body = driver.find_element(By.TAG_NAME, "body").text
        assert "weighing a stable role" in body.lower()
        assert "1994-08-17" not in body
        screenshot(driver, screenshots, "05_astrologer_console_desktop.png", results)
        results["journey_steps"].append("consent-filtered astrologer console")

        results["last_stage"] = "follow-up"
        driver.get(base + "/follow-up")
        fill(driver, "#summary", "I will compare the paths without treating guidance as certainty.")
        followup_date = (date.today() + timedelta(days=7)).isoformat()
        driver.execute_script(
            "const e=document.querySelector('#checkin_date');e.value=arguments[0];e.dispatchEvent(new Event('change',{bubbles:true}));",
            followup_date,
        )
        click(driver, wait, '#help_helpful')
        assert driver.find_element(By.CSS_SELECTOR, '[data-helpfulness-input]').get_attribute("value") == "helpful"
        click(driver, wait, 'label[for="approve_followup"]')
        click(driver, wait, '[data-followup-form] button[type="submit"]')
        wait_text(wait, "[data-form-status]", "saved to your journey")
        results["journey_steps"].append("post-consultation follow-up")

        results["last_stage"] = "circle-inviter"
        driver.get(base + "/circle")
        click(driver, wait, "[data-create-invite]")
        wait.until(lambda browser: browser.find_element(By.CSS_SELECTOR, "[data-share-url]").get_attribute("value").startswith(base + "/circle/"))
        invitation_url = driver.find_element(By.CSS_SELECTOR, "[data-share-url]").get_attribute("value")
        whats_app = driver.find_element(By.CSS_SELECTOR, "[data-whatsapp]").get_attribute("href")
        assert "%2Fcircle%2F" in whats_app and "birth" not in whats_app.lower()
        click(driver, wait, '[data-download-card="png"]')
        wait.until(lambda _browser: any(downloads.glob("orbit-circle-safe-card*.png")))
        results["downloads"].append("privacy-safe Circle PNG")
        # Never publish a live bearer token in curated screenshot evidence.
        driver.execute_script(
            "document.querySelector('[data-share-url]').value=arguments[0]+'/circle/[redacted]';",
            base,
        )
        screenshot(driver, screenshots, "06_circle_invitation_desktop.png", results)
        results["journey_steps"].append("secure Circle invitation")

        results["last_stage"] = "circle-independent-invitee"
        guest_options = chrome_options(binary, guest_profile, guest_downloads, headless)
        guest_driver = webdriver.Chrome(options=guest_options)
        guest_wait = WebDriverWait(guest_driver, 15)
        guest_driver.set_window_size(1440, 1000)
        guest_driver.get(invitation_url)
        guest_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-invite-form]")))
        if guest_driver.get_cookie("session") == driver.get_cookie("session"):
            raise AssertionError("Invitee browser unexpectedly reused the inviter session.")
        Select(guest_driver.find_element(By.ID, "conversation_style")).select_by_value("ideas")
        click(guest_driver, guest_wait, 'label[for="guest_consent"]')
        click(guest_driver, guest_wait, '[data-invite-form] button[type="submit"]')
        guest_wait.until(
            lambda browser: browser.find_element(By.CSS_SELECTOR, "[data-mutual-insight]").is_displayed()
        )
        assert "deterministic" in guest_driver.find_element(
            By.CSS_SELECTOR, "[data-mutual-insight]"
        ).text.lower()
        screenshot(guest_driver, screenshots, "07_mutual_circle_insight_desktop.png", results)
        guest_errors = browser_logs(guest_driver)
        if guest_errors:
            raise AssertionError(f"Invitee browser console errors: {guest_errors}")
        guest_driver.quit()
        guest_driver = None

        driver.get(base + "/circle")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-circle]")))
        assert "mutual insight unlocked" in driver.find_element(By.TAG_NAME, "body").text.lower()
        results["journey_steps"].extend([
            "independent invitee browser",
            "invitee consented check-in",
            "mutual insight unlock",
        ])

        results["last_stage"] = "journey"
        driver.get(base + "/journey")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-journey]")))
        for action_selector in (
            '.completion-toggle[data-action-endpoint*="follow-up-actions"][aria-pressed="false"]',
            '.completion-toggle[data-action-endpoint*="/journey/actions/"][aria-pressed="false"]',
        ):
            action = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, action_selector)))
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center',behavior:'instant'});", action
            )
            action.click()
            wait.until(lambda _browser, target=action: target.get_attribute("aria-pressed") == "true")
        wait.until(
            lambda browser: browser.find_element(By.CSS_SELECTOR, "[data-action-count]").get_attribute("data-completed")
            == browser.find_element(By.CSS_SELECTOR, "[data-action-count]").get_attribute("data-total")
        )
        click(driver, wait, '[data-consultation-feedback] [data-value="helpful"]')
        screenshot(driver, screenshots, "08_journey_desktop.png", results)
        results["journey_steps"].extend([
            "Journey timeline", "Pulse action completion", "follow-up action completion",
            "consultation helpfulness",
        ])

        results["last_stage"] = "growth"
        driver.get(base + "/growth")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-dashboard]")))
        assert "reproducible synthetic data" in driver.find_element(By.TAG_NAME, "body").text.lower()
        Select(driver.find_element(By.ID, "focus_filter")).select_by_value("career")
        filter_form = driver.find_element(By.CSS_SELECTOR, "[data-dashboard-filters]")
        filter_button = filter_form.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
        if not filter_button.is_enabled() or not filter_button.is_displayed():
            raise AssertionError("Growth filter submit control is not operable.")
        driver.get(base + "/growth?period=90d&segment=all&focus=career")
        wait.until(EC.url_contains("focus=career"))
        assert_no_overflow(driver, "growth-desktop", results)
        screenshot(driver, screenshots, "09_growth_cockpit_desktop.png", results)
        results["journey_steps"].append("filtered Growth Cockpit")

        results["last_stage"] = "experiments-load"
        driver.get(base + "/experiments")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-simulator]")))
        results["last_stage"] = "experiments-fill"
        fill(driver, "#trials", "10000")
        invalid_experiment_fields = driver.execute_script(
            "return [...document.querySelectorAll('[data-simulator-form] [required]')]"
            ".filter(field=>!field.checkValidity()).map(field=>({name:field.name,value:field.value,"
            "message:field.validationMessage}));"
        )
        if invalid_experiment_fields:
            raise AssertionError(
                f"Simulator contains invalid fields: {invalid_experiment_fields}"
            )
        results["last_stage"] = "experiments-submit"
        click(driver, wait, '[data-simulator-form] button[type="submit"]')
        results["last_stage"] = "experiments-wait"
        wait_text(wait, "[data-form-status]", "scenario complete")
        retained = driver.find_element(By.CSS_SELECTOR, '[data-result="retained"]').text
        assert retained not in {"", "0", "—"}
        click(driver, wait, '[data-download="json"]')
        click(driver, wait, '[data-download="csv"]')
        wait.until(lambda _browser: any(downloads.glob("orbit-scenario*.json")) and any(downloads.glob("orbit-scenario*.csv")))
        results["downloads"].extend(["simulator JSON", "simulator CSV"])
        screenshot(driver, screenshots, "10_experiment_simulator_desktop.png", results)
        results["journey_steps"].append("10,000-trial experiment simulation")

        results["last_stage"] = "mobile-360"
        set_exact_mobile_viewport(driver)
        driver.get(base + "/")
        mobile_toggle = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-nav-toggle]")))
        mobile_toggle.send_keys(Keys.SPACE)
        wait.until(lambda _browser: mobile_toggle.get_attribute("aria-expanded") == "true")
        results["accessibility_checks"].append({
            "check": "mobile-nav-keyboard-toggle", "passed": True, "width": 360,
        })
        curated_mobile = {
            "/": "11_landing_mobile.png",
            "/pulse": "12_pulse_mobile.png",
            "/growth": "13_growth_mobile.png",
        }
        for path in MAIN_PATHS:
            driver.get(base + path)
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "main")))
            assert_no_overflow(driver, f"{path}-mobile", results)
            interactive_count = driver.execute_script(
                "return [...document.querySelectorAll('a,button,input,select,textarea')].filter(e=>"
                "!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length)).length;"
            )
            if interactive_count < 1:
                raise AssertionError(f"No visible interactive control at 360px on {path}")
            if path in curated_mobile:
                screenshot(driver, screenshots, curated_mobile[path], results)
        results["journey_steps"].append("populated 360px route and control inspection")

        results["last_stage"] = "reset"
        clear_mobile_viewport(driver)
        driver.get(base + "/journey")
        click(driver, wait, "[data-reset]")
        wait.until(lambda browser: browser.find_element(By.CSS_SELECTOR, "[data-reset-dialog]").get_attribute("open") is not None)
        click(driver, wait, "[data-confirm-reset]")
        wait.until(EC.url_contains("/onboarding"))
        results["journey_steps"].append("server-side demo deletion/reset")

        # Repeat the entire critical journey at exactly 360px in a fresh session.
        results["last_stage"] = "mobile-full-onboarding"
        set_exact_mobile_viewport(driver)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-onboarding-form]")))
        fill(driver, "#display_name", "Mobile Judge")
        driver.execute_script(
            "const e=document.querySelector('#birth_date');e.value='1996-02-10';"
            "e.dispatchEvent(new Event('change',{bubbles:true}));"
        )
        fill(driver, "#birth_city", "Pune")
        click(driver, wait, 'label[for="focus_4"]')
        Select(driver.find_element(By.ID, "communication_preference")).select_by_value("supportive")
        click(driver, wait, 'label[for="save_consent"]')
        click(driver, wait, 'label[for="circle_consent"]')
        driver.execute_script(
            "const f=document.querySelector('[data-onboarding-form]');"
            "f.addEventListener('submit',event=>{event.preventDefault();"
            "fetch(f.action,{method:'POST',body:new FormData(f),credentials:'same-origin'})"
            ".then(response=>{if(!response.ok)throw new Error(String(response.status));location.assign(response.url);})"
            ".catch(error=>{window.__mobileOnboardingError=String(error);});},{once:true});"
        )
        click(driver, wait, '[data-onboarding-form] button[type="submit"]')
        wait.until(EC.url_contains("/pulse"))
        assert_no_overflow(driver, "mobile-full-pulse", results)

        results["last_stage"] = "mobile-full-pulse"
        click(driver, wait, 'label[for="mood_hopeful"]')
        fill(driver, "#concern", "I want one calm next step for my learning plan.")
        click(driver, wait, '[data-pulse-form] button[type="submit"]')
        wait_text(wait, "[data-form-status]", "saved privately")
        click(driver, wait, '[data-feedback="true"]')

        results["last_stage"] = "mobile-full-bridge"
        driver.get(base + "/bridge")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-bridge-form]")))
        Select(driver.find_element(By.ID, "topic")).select_by_value("education")
        fill(driver, "#context", "I am choosing between two learning paths with different time commitments.")
        fill(driver, "#outcome", "A reversible learning experiment for this week.")
        fill(driver, "#questions", "What can I test before committing?\nWhich trade-off matters most?")
        Select(driver.find_element(By.ID, "mode")).select_by_value("chat")
        click(driver, wait, 'label[for="include_checkins"]')
        click(driver, wait, '[data-bridge-form] button[type="submit"]')
        wait.until(lambda browser: bool(browser.find_element(By.CSS_SELECTOR, "[data-bridge-form]").get_attribute("data-brief-id")))
        click(driver, wait, 'label[for="approve_brief"]')
        wait.until(lambda browser: browser.find_element(By.CSS_SELECTOR, "[data-book-cta]").get_attribute("aria-disabled") == "false")
        exercise_link_and_navigate(driver, wait, "[data-book-cta]", base)
        assert_no_overflow(driver, "mobile-full-booking", results)

        results["last_stage"] = "mobile-full-booking"
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-booking-form]")))
        Select(driver.find_element(By.ID, "booking_mode")).select_by_value("chat")
        click(driver, wait, '[data-booking-form] button[type="submit"]')
        wait.until(lambda browser: browser.find_element(By.CSS_SELECTOR, "[data-booking-confirmation]").is_displayed())

        results["last_stage"] = "mobile-full-console-follow-up"
        driver.get(base + "/console")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-console]")))
        assert "learning paths" in driver.find_element(By.TAG_NAME, "body").text.lower()
        driver.get(base + "/follow-up")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-followup-form]")))
        fill(driver, "#summary", "I will run a small learning experiment before deciding.")
        mobile_followup_date = (date.today() + timedelta(days=5)).isoformat()
        driver.execute_script(
            "const e=document.querySelector('#checkin_date');e.value=arguments[0];"
            "e.dispatchEvent(new Event('change',{bubbles:true}));", mobile_followup_date,
        )
        click(driver, wait, '#help_somewhat')
        assert driver.find_element(By.CSS_SELECTOR, '[data-helpfulness-input]').get_attribute("value") == "somewhat"
        click(driver, wait, 'label[for="approve_followup"]')
        click(driver, wait, '[data-followup-form] button[type="submit"]')
        wait_text(wait, "[data-form-status]", "saved to your journey")

        results["last_stage"] = "mobile-full-circle"
        driver.get(base + "/circle")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-circle]")))
        click(driver, wait, "[data-create-invite]")
        wait.until(lambda browser: browser.find_element(By.CSS_SELECTOR, "[data-share-url]").get_attribute("value").startswith(base + "/circle/"))
        mobile_invitation = driver.find_element(By.CSS_SELECTOR, "[data-share-url]").get_attribute("value")
        guest_options = chrome_options(binary, mobile_guest_profile, guest_downloads, headless)
        guest_driver = webdriver.Chrome(options=guest_options)
        set_exact_mobile_viewport(guest_driver)
        guest_wait = WebDriverWait(guest_driver, 15)
        guest_driver.get(mobile_invitation)
        guest_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-invite-form]")))
        Select(guest_driver.find_element(By.ID, "conversation_style")).select_by_value("space")
        click(guest_driver, guest_wait, 'label[for="guest_consent"]')
        click(guest_driver, guest_wait, '[data-invite-form] button[type="submit"]')
        guest_wait.until(lambda browser: browser.find_element(By.CSS_SELECTOR, "[data-mutual-insight]").is_displayed())
        assert_no_overflow(guest_driver, "mobile-full-independent-invitee", results)
        if browser_logs(guest_driver):
            raise AssertionError("Mobile invitee browser emitted console errors.")
        guest_driver.quit()
        guest_driver = None

        results["last_stage"] = "mobile-full-journey"
        driver.get(base + "/journey")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-journey]")))
        for action_selector in (
            '.completion-toggle[data-action-endpoint*="follow-up-actions"][aria-pressed="false"]',
            '.completion-toggle[data-action-endpoint*="/journey/actions/"][aria-pressed="false"]',
        ):
            action = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, action_selector)))
            driver.execute_script("arguments[0].scrollIntoView({block:'center',behavior:'instant'});", action)
            action.click()
            wait.until(lambda _browser, target=action: target.get_attribute("aria-pressed") == "true")
        click(driver, wait, '[data-consultation-feedback] [data-value="helpful"]')
        assert_no_overflow(driver, "mobile-full-journey", results)

        results["last_stage"] = "mobile-full-growth-experiments"
        driver.get(base + "/growth?period=90d&segment=all&focus=education")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-dashboard]")))
        assert_no_overflow(driver, "mobile-full-growth", results)
        driver.get(base + "/experiments")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-simulator]")))
        fill(driver, "#trials", "10000")
        click(driver, wait, '[data-simulator-form] button[type="submit"]')
        wait_text(wait, "[data-form-status]", "scenario complete")
        driver.get(base + "/privacy")
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "main")))
        assert_no_overflow(driver, "mobile-full-privacy", results)
        results["journey_steps"].append("complete interactive journey repeated at 360px")

        results["last_stage"] = "mobile-full-reset"
        driver.get(base + "/journey")
        click(driver, wait, "[data-reset]")
        wait.until(lambda browser: browser.find_element(By.CSS_SELECTOR, "[data-reset-dialog]").get_attribute("open") is not None)
        click(driver, wait, "[data-confirm-reset]")
        wait.until(EC.url_contains("/onboarding"))
        results["journey_steps"].append("360px journey deletion/reset")

        results["last_stage"] = "health-and-console"
        health = driver.execute_async_script(
            "const done=arguments[0];fetch('/api/health').then(r=>r.json()).then(done).catch(e=>done({error:String(e)}));"
        )
        if not health.get("ok") or health.get("data", {}).get("status") != "healthy":
            raise AssertionError(f"Health check failed: {health}")
        results["console_errors"] = browser_logs(driver)
        if results["console_errors"]:
            raise AssertionError(f"Browser console errors: {results['console_errors']}")
        published_screenshots.mkdir(parents=True, exist_ok=True)
        staged_names = {source.name for source in screenshots.glob("*.png")}
        for stale in published_screenshots.glob("*.png"):
            if stale.name not in staged_names:
                stale.unlink()
        for source in screenshots.glob("*.png"):
            shutil.copy2(source, published_screenshots / source.name)
        screenshot_evidence = []
        for raw_path in results["screenshots"]:
            path = ROOT / raw_path
            with Image.open(path) as capture:
                width, height = capture.size
            screenshot_evidence.append({
                "path": raw_path,
                "sha256": file_sha256(path),
                "width": width,
                "height": height,
            })
        results["evidence_schema"] = 2
        results["completed_at"] = datetime.now(timezone.utc).isoformat()
        results["source_sha256"] = browser_source_sha256()
        results["screenshot_evidence"] = screenshot_evidence
        results["ok"] = True
        return results
    except Exception as exc:
        raise RuntimeError(
            f"Browser smoke failed at {results.get('last_stage')}: {type(exc).__name__}: {exc}"
        ) from exc
    finally:
        if guest_driver is not None:
            try:
                guest_driver.quit()
            except Exception:
                pass
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        server.stop()
        server.join(timeout=10)
        time.sleep(0.3)
        shutil.rmtree(scratch, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true", help="Show Chrome instead of using headless mode")
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "browser_smoke_results.json")
    args = parser.parse_args()
    try:
        result = run_smoke(headless=not args.headed)
    except Exception as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        rendered = json.dumps(result, indent=2)
        print(rendered)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        return 1
    rendered = json.dumps(result, indent=2)
    print(rendered)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
