"""Security scanner: static analysis for dangerous patterns in generated code."""

from __future__ import annotations

import re
from typing import Sequence

import structlog

from app.models.schemas import SecurityFinding

logger = structlog.get_logger()

# Each pattern: (regex, severity, description)
BLOCKED_PATTERNS: list[tuple[str, str, str]] = [
    (r"\bfetch\s*\(", "blocker", "Network request via fetch()"),
    (r"\bXMLHttpRequest\b", "blocker", "Network request via XMLHttpRequest"),
    (r"\bnew\s+WebSocket\b", "blocker", "WebSocket connection attempt"),
    (r"\beval\s*\(", "blocker", "eval() usage - arbitrary code execution"),
    (r"\bnew\s+Function\s*\(", "blocker", "Function() constructor - arbitrary code execution"),
    (r"\bsetTimeout\s*\(\s*['\"]", "warning", "setTimeout with string argument (implicit eval)"),
    (r"\bsetInterval\s*\(\s*['\"]", "warning", "setInterval with string argument (implicit eval)"),
    (r"\bdocument\.cookie\b", "blocker", "Cookie access"),
    (r"\blocalStorage\b", "blocker", "localStorage access"),
    (r"\bsessionStorage\b", "blocker", "sessionStorage access"),
    (r"\bindexedDB\b", "blocker", "IndexedDB access"),
    (r"\b\.innerHTML\s*=", "warning", "innerHTML assignment - potential XSS"),
    (r"\bdocument\.write\s*\(", "warning", "document.write() usage"),
    (r"\bwindow\.open\s*\(", "blocker", "window.open() - popup attempt"),
    (r"\bwindow\.location\b", "blocker", "Location manipulation"),
    (r"\bpostMessage\s*\(", "warning", "postMessage usage"),
    (r"\bimportScripts\s*\(", "blocker", "importScripts() - worker script loading"),
    (r"\bnew\s+Worker\s*\(", "warning", "Web Worker creation"),
    (r"\bnavigator\.\w+", "warning", "Navigator API access"),
    (r"<script\s+[^>]*src\s*=\s*['\"]https?://", "blocker", "External script loading in HTML"),
    (r"<link\s+[^>]*href\s*=\s*['\"]https?://", "blocker", "External stylesheet loading"),
    (r"<iframe\b", "blocker", "Iframe inclusion"),
    (r"\balert\s*\(", "warning", "alert() call - poor UX"),
    (r"\bprompt\s*\(", "warning", "prompt() call - poor UX"),
    (r"\bconfirm\s*\(", "warning", "confirm() call - poor UX"),
]


def scan_generated_code(
    files: dict[str, str],
    extra_blocked: Sequence[tuple[str, str, str]] | None = None,
) -> list[SecurityFinding]:
    """Scan generated game files for blocked patterns."""
    patterns = list(BLOCKED_PATTERNS)
    if extra_blocked:
        patterns.extend(extra_blocked)

    findings: list[SecurityFinding] = []

    for filename, content in files.items():
        lines = content.split("\n")
        for line_no, line in enumerate(lines, 1):
            for pattern, severity, description in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append(
                        SecurityFinding(
                            file=filename,
                            line=line_no,
                            pattern=pattern,
                            severity=severity,
                            description=description,
                            snippet=line.strip()[:120],
                        )
                    )

    blocker_count = sum(1 for f in findings if f.severity == "blocker")
    warning_count = sum(1 for f in findings if f.severity == "warning")
    logger.info(
        "security_scan_complete",
        total_findings=len(findings),
        blockers=blocker_count,
        warnings=warning_count,
        files_scanned=len(files),
    )

    return findings


def has_blockers(findings: list[SecurityFinding]) -> bool:
    """True when there is at least one blocker severity finding."""
    return any(f.severity == "blocker" for f in findings)


def format_security_report(findings: list[SecurityFinding]) -> str:
    """Format findings as a human-readable report."""
    if not findings:
        return "Security scan: PASS - no issues found."

    lines = ["Security Scan Report", "=" * 40]
    blockers = [f for f in findings if f.severity == "blocker"]
    warnings = [f for f in findings if f.severity == "warning"]

    if blockers:
        lines.append(f"\nBLOCKERS ({len(blockers)}):")
        for finding in blockers:
            lines.append(f"  [{finding.file}:{finding.line}] {finding.description}")
            lines.append(f"    -> {finding.snippet}")

    if warnings:
        lines.append(f"\nWARNINGS ({len(warnings)}):")
        for finding in warnings:
            lines.append(f"  [{finding.file}:{finding.line}] {finding.description}")
            lines.append(f"    -> {finding.snippet}")

    return "\n".join(lines)
