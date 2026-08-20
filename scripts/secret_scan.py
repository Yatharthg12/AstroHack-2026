"""Lightweight repository secret and unsafe-path scan for submission QA."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", ".test-tmp", "test-output", "instance", "tmp", "report/qa/pages"}
TEXT_SUFFIXES = {".py", ".html", ".css", ".js", ".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".ini", ".env", ""}
PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "absolute_user_path": re.compile(r"(?i)\b[A-Z]:\\Users\\(?!example\\|your-name\\)[^\s'\"<>]+"),
}


def scan() -> dict:
    findings: list[dict] = []
    scanned = 0
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > 2_000_000:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        relative = path.relative_to(ROOT).as_posix()
        for line_number, line in enumerate(content.splitlines(), 1):
            if "secret-not-for-production" in line or "replace-with-a-long-random-value" in line:
                continue
            for kind, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append({"file": relative, "line": line_number, "kind": kind})
    return {"ok": not findings, "files_scanned": scanned, "findings": findings}


if __name__ == "__main__":
    result = scan()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
