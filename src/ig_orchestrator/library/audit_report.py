"""Data model and renderers (Markdown / CSV) for the library audit."""

from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    severity: Severity
    username: str = ""
    owner_id: str = ""
    paths: tuple[str, ...] = ()
    detail: str = ""


@dataclass(slots=True)
class AuditReport:
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    disk_checked: bool = False

    def summary(self) -> dict[str, int]:
        counts = Counter(finding.code for finding in self.findings)
        return dict(sorted(counts.items()))

    def by_code(self, code: str) -> list[Finding]:
        return [finding for finding in self.findings if finding.code == code]


def render_markdown(report: AuditReport) -> str:
    lines = ["# Auditoría de biblioteca", ""]
    for note in report.notes:
        lines.append(f"> {note}")
    if report.notes:
        lines.append("")
    lines += ["## Resumen", "", "| Código | Hallazgos |", "|---|---:|"]
    for code, count in report.summary().items():
        lines.append(f"| `{code}` | {count} |")
    if not report.findings:
        lines.append("| (sin hallazgos) | 0 |")
    for code in report.summary():
        lines += ["", f"## {code}", ""]
        for finding in report.by_code(code):
            who = finding.username or "-"
            owner = f" (owner {finding.owner_id})" if finding.owner_id else ""
            paths = "; ".join(f"`{p}`" for p in finding.paths)
            detail = f" — {finding.detail}" if finding.detail else ""
            lines.append(f"- **{who}**{owner} [{finding.severity}] {paths}{detail}")
    lines.append("")
    return "\n".join(lines)


def render_csv(report: AuditReport) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(["code", "severity", "username", "owner_id", "paths", "detail"])
    for finding in report.findings:
        writer.writerow(
            [
                finding.code,
                finding.severity.value,
                finding.username,
                finding.owner_id,
                " | ".join(finding.paths),
                finding.detail,
            ]
        )
    # BOM so Excel opens UTF-8 correctly.
    return "﻿" + buffer.getvalue()
