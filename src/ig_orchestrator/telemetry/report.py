"""Execution report of a batch, built from the telemetry tables (feat-run-36).

Pure functions over an SQLite connection: no GUI, no writes. The report is
deterministic, so the recommendations are plain rules over the measured data.
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass, field
from datetime import datetime
from sqlite3 import Connection

# Default first-response timeouts (seconds) by publication type, used to judge
# whether the measured delays fit (orchestration/run_settings.py).
DEFAULT_FIRST_RESPONSE_SECONDS = {
    "REEL": 30,
    "STORY": 30,
    "POST": 75,
    "HIGHLIGHTS": 75,
}
PHASES = (
    ("bot", "Respuesta del bot"),
    ("download", "Descarga"),
    ("end_wait", "Fin de espera"),
    ("flood", "FloodWait"),
    ("backoff", "Espera de reintento"),
    ("move", "Movimiento de ficheros"),
    ("other", "Otros"),
)
SLOWEST_LIMIT = 20


@dataclass(frozen=True, slots=True)
class AttemptRow:
    id: int
    url_job_id: int
    account: str
    url: str
    attempt_no: int
    publication_type: str
    bucket: str
    expected_items: int | None
    exit_reason: str
    outcome: str
    error_code: str
    total_ms: int
    first_response_ms: int | None
    files_count: int
    bytes_downloaded: int
    aes_backend: str
    phases: dict[str, int]

    @property
    def dominant_phase(self) -> str:
        phase = max(self.phases, key=lambda name: self.phases[name])
        return phase if self.phases[phase] > 0 else "other"


@dataclass(frozen=True, slots=True)
class TypeStats:
    label: str
    count: int
    first_p50: float | None
    first_p90: float | None
    first_max: float | None
    total_p50: float | None
    total_p90: float | None
    total_max: float | None


@dataclass(frozen=True, slots=True)
class ErrorStats:
    code: str
    count: int
    avg_first_response_ms: float | None
    retries_used: int
    lost_ms: int


@dataclass(frozen=True, slots=True)
class RetryStats:
    attempt_no: int
    attempts: int
    completed: int


@dataclass(frozen=True, slots=True)
class BatchReport:
    batch_id: int
    batch_name: str
    attempts: tuple[AttemptRow, ...] = ()
    urls: int = 0
    accounts: int = 0
    wall_seconds: float = 0.0
    active_seconds: float = 0.0
    bytes_downloaded: int = 0
    phase_ms: dict[str, int] = field(default_factory=dict)
    slowest: tuple[AttemptRow, ...] = ()
    by_type: tuple[TypeStats, ...] = ()
    errors: tuple[ErrorStats, ...] = ()
    retries: tuple[RetryStats, ...] = ()
    recommendations: tuple[str, ...] = ()

    @property
    def urls_per_hour(self) -> float | None:
        if self.wall_seconds <= 0:
            return None
        return self.urls * 3600 / self.wall_seconds

    def phase_percent(self) -> dict[str, float]:
        total = sum(self.phase_ms.values())
        if total <= 0:
            return {name: 0.0 for name, _ in PHASES}
        return {name: 100 * self.phase_ms.get(name, 0) / total for name, _ in PHASES}


def has_report_data(connection: Connection, batch_id: int) -> bool:
    try:
        row = connection.execute(
            "SELECT 1 FROM url_job_attempts WHERE batch_id = ? LIMIT 1", (batch_id,)
        ).fetchone()
    except Exception:
        return False
    return row is not None


def build_batch_report(connection: Connection, batch_id: int) -> BatchReport:
    """Build the report of one batch; empty report when it has no telemetry."""

    batch_name = _batch_name(connection, batch_id)
    attempts = _load_attempts(connection, batch_id)
    if not attempts:
        return BatchReport(batch_id=batch_id, batch_name=batch_name)

    phase_ms = {name: 0 for name, _ in PHASES}
    for attempt in attempts:
        for name, value in attempt.phases.items():
            phase_ms[name] += value

    starts = [_parse(row[0]) for row in _bounds(connection, batch_id)]
    wall = 0.0
    if starts and starts[0] and starts[1]:
        wall = max((starts[1] - starts[0]).total_seconds(), 0.0)
    active = sum(a.total_ms for a in attempts) / 1000
    urls = len({a.url_job_id for a in attempts})
    report = BatchReport(
        batch_id=batch_id,
        batch_name=batch_name,
        attempts=tuple(attempts),
        urls=urls,
        accounts=len({a.account for a in attempts}),
        wall_seconds=max(wall, active),
        active_seconds=active,
        bytes_downloaded=sum(a.bytes_downloaded for a in attempts),
        phase_ms=phase_ms,
        slowest=tuple(sorted(attempts, key=lambda a: a.total_ms, reverse=True)[:SLOWEST_LIMIT]),
        by_type=tuple(_type_stats(attempts)),
        errors=tuple(_error_stats(attempts)),
        retries=tuple(_retry_stats(attempts)),
    )
    return _with_recommendations(report)


def explain(attempt: AttemptRow) -> str:
    """One-line reason why an attempt was slow: dominant phase + exit reason."""

    labels = dict(PHASES)
    total = max(attempt.total_ms, 1)
    dominant = attempt.dominant_phase
    share = 100 * attempt.phases.get(dominant, 0) / total
    text = f"{labels[dominant]} {share:.0f} %"
    if attempt.exit_reason:
        text += f"; salida {attempt.exit_reason}"
    if attempt.error_code:
        text += f"; error {attempt.error_code}"
    if attempt.attempt_no > 1:
        text += f"; intento {attempt.attempt_no}"
    return text


def report_to_markdown(report: BatchReport) -> str:
    lines = [f"# Informe de ejecución — {report.batch_name} (lote {report.batch_id})", ""]
    if not report.attempts:
        lines.append("Sin telemetría para este lote (¿telemetría desactivada o purgada?).")
        return "\n".join(lines) + "\n"
    per_hour = report.urls_per_hour
    lines += [
        "## Resumen",
        "",
        f"* Cuentas: {report.accounts} · URLs: {report.urls} · intentos: {len(report.attempts)}",
        f"* Duración: {_fmt_seconds(report.wall_seconds)} · tiempo activo: "
        f"{_fmt_seconds(report.active_seconds)}"
        + (f" · {per_hour:.0f} URLs/h" if per_hour else ""),
        f"* Descargado: {_fmt_bytes(report.bytes_downloaded)}",
        "",
        "| Fase | % | Tiempo |",
        "|---|---:|---:|",
    ]
    percents = report.phase_percent()
    for name, label in PHASES:
        lines.append(
            f"| {label} | {percents[name]:.0f} | {_fmt_seconds(report.phase_ms[name] / 1000)} |"
        )
    lines += ["", f"## Más lentos (top {len(report.slowest)})", ""]
    lines += ["| # | Cuenta | Tipo | Total | Por qué |", "|---:|---|---|---:|---|"]
    for index, attempt in enumerate(report.slowest, start=1):
        lines.append(
            f"| {index} | {attempt.account} | {attempt.publication_type} "
            f"| {_fmt_seconds(attempt.total_ms / 1000)} | {explain(attempt)} |"
        )
    lines += ["", "## Por tipo y tamaño (segundos)", ""]
    lines += [
        "| Tipo | N | 1ª resp. p50 | p90 | máx | Total p50 | p90 | máx |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for stat in report.by_type:
        lines.append(
            f"| {stat.label} | {stat.count} | {_n(stat.first_p50)} | {_n(stat.first_p90)} "
            f"| {_n(stat.first_max)} | {_n(stat.total_p50)} | {_n(stat.total_p90)} "
            f"| {_n(stat.total_max)} |"
        )
    lines += ["", "## Errores", ""]
    if report.errors:
        lines += ["| Código | N | Tiempo hasta mensaje (s) | Reintentos | Tiempo perdido |",
                  "|---|---:|---:|---:|---:|"]
        for error in report.errors:
            lines.append(
                f"| {error.code} | {error.count} | "
                f"{_n(error.avg_first_response_ms and error.avg_first_response_ms / 1000)} "
                f"| {error.retries_used} | {_fmt_seconds(error.lost_ms / 1000)} |"
            )
    else:
        lines.append("Sin errores.")
    lines += ["", "## Reintentos", ""]
    lines += ["| Intento | Intentos | Completados | Éxito |", "|---:|---:|---:|---:|"]
    for retry in report.retries:
        rate = 100 * retry.completed / retry.attempts if retry.attempts else 0
        lines.append(f"| {retry.attempt_no} | {retry.attempts} | {retry.completed} | {rate:.0f} % |")
    lines += ["", "## Recomendaciones", ""]
    lines += [f"* {text}" for text in report.recommendations] or ["Sin recomendaciones."]
    return "\n".join(lines) + "\n"


def attempts_to_csv(report: BatchReport) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["attempt_id", "account", "url", "attempt_no", "type", "bucket", "expected_items",
         "files", "exit_reason", "outcome", "error_code", "total_ms", "first_response_ms",
         "bytes", "aes_backend", *[name + "_ms" for name, _ in PHASES]]
    )
    for a in report.attempts:
        writer.writerow(
            [a.id, a.account, a.url, a.attempt_no, a.publication_type, a.bucket,
             a.expected_items, a.files_count, a.exit_reason, a.outcome, a.error_code,
             a.total_ms, a.first_response_ms, a.bytes_downloaded, a.aes_backend,
             *[a.phases[name] for name, _ in PHASES]]
        )
    return buffer.getvalue()


# --- data loading -------------------------------------------------------------


def _batch_name(connection: Connection, batch_id: int) -> str:
    try:
        row = connection.execute(
            "SELECT batch_name FROM input_batches WHERE id = ?", (batch_id,)
        ).fetchone()
    except Exception:
        row = None
    return str(row[0]) if row else f"lote {batch_id}"


def _bounds(connection: Connection, batch_id: int) -> list[tuple[str | None]]:
    row = connection.execute(
        "SELECT MIN(started_at), MAX(finished_at) FROM url_job_attempts WHERE batch_id = ?",
        (batch_id,),
    ).fetchone()
    return [(row[0],), (row[1],)]


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _load_attempts(connection: Connection, batch_id: int) -> list[AttemptRow]:
    try:
        rows = connection.execute(
            """
            SELECT a.id, a.url_job_id, COALESCE(acc.username, '?') AS username,
                   COALESCE(j.url, '') AS url, a.attempt_no, a.publication_type,
                   a.album_size_bucket, a.expected_items, a.exit_reason, a.outcome,
                   a.error_code, a.t_total_ms, a.t_first_response_ms, a.t_download_ms,
                   a.t_end_wait_ms, a.t_move_ms, a.flood_wait_ms, a.retry_wait_ms,
                   a.files_count, a.bytes_downloaded, a.aes_backend
            FROM url_job_attempts a
            LEFT JOIN url_jobs j ON j.id = a.url_job_id
            LEFT JOIN accounts acc ON acc.id = a.account_id
            WHERE a.batch_id = ?
            ORDER BY a.started_at, a.id
            """,
            (batch_id,),
        ).fetchall()
    except Exception:
        return []
    result: list[AttemptRow] = []
    for row in rows:
        total = int(row[11] or 0)
        phases = {
            "bot": int(row[12] or 0),
            "download": int(row[13] or 0),
            "end_wait": int(row[14] or 0),
            "move": int(row[15] or 0),
            "flood": int(row[16] or 0),
            "backoff": int(row[17] or 0),
        }
        phases["other"] = max(total - sum(phases.values()), 0)
        result.append(
            AttemptRow(
                id=row[0], url_job_id=row[1], account=str(row[2]), url=str(row[3]),
                attempt_no=int(row[4] or 1), publication_type=str(row[5] or "?"),
                bucket=str(row[6] or ""), expected_items=row[7],
                exit_reason=str(row[8] or ""), outcome=str(row[9] or ""),
                error_code=str(row[10] or ""), total_ms=total,
                first_response_ms=row[12], files_count=int(row[18] or 0),
                bytes_downloaded=int(row[19] or 0), aes_backend=str(row[20] or ""),
                phases=phases,
            )
        )
    return result


# --- aggregation --------------------------------------------------------------


def percentile(values: list[float], fraction: float) -> float | None:
    """Nearest-rank percentile; ``None`` for an empty list."""

    if not values:
        return None
    ordered = sorted(values)
    rank = max(math.ceil(fraction * len(ordered)), 1)
    return ordered[rank - 1]


def _type_stats(attempts: list[AttemptRow]) -> list[TypeStats]:
    groups: dict[str, list[AttemptRow]] = {}
    for attempt in attempts:
        label = attempt.publication_type
        if label in ("POST", "REEL") and attempt.bucket:
            label = f"{label} ({attempt.bucket})"
        groups.setdefault(label, []).append(attempt)
    stats = []
    for label in sorted(groups):
        rows = groups[label]
        first = [r.first_response_ms / 1000 for r in rows if r.first_response_ms is not None]
        total = [r.total_ms / 1000 for r in rows]
        stats.append(
            TypeStats(
                label=label, count=len(rows),
                first_p50=percentile(first, 0.5), first_p90=percentile(first, 0.9),
                first_max=max(first) if first else None,
                total_p50=percentile(total, 0.5), total_p90=percentile(total, 0.9),
                total_max=max(total) if total else None,
            )
        )
    return stats


def _error_stats(attempts: list[AttemptRow]) -> list[ErrorStats]:
    groups: dict[str, list[AttemptRow]] = {}
    for attempt in attempts:
        if attempt.error_code:
            groups.setdefault(attempt.error_code, []).append(attempt)
    stats = []
    for code, rows in groups.items():
        firsts = [r.first_response_ms for r in rows if r.first_response_ms is not None]
        stats.append(
            ErrorStats(
                code=code, count=len(rows),
                avg_first_response_ms=sum(firsts) / len(firsts) if firsts else None,
                retries_used=sum(1 for r in rows if r.attempt_no > 1),
                lost_ms=sum(r.total_ms for r in rows),
            )
        )
    return sorted(stats, key=lambda s: s.lost_ms, reverse=True)


def _retry_stats(attempts: list[AttemptRow]) -> list[RetryStats]:
    groups: dict[int, list[AttemptRow]] = {}
    for attempt in attempts:
        groups.setdefault(attempt.attempt_no, []).append(attempt)
    return [
        RetryStats(
            attempt_no=number, attempts=len(rows),
            completed=sum(1 for r in rows if r.outcome == "COMPLETED"),
        )
        for number, rows in sorted(groups.items())
    ]


# --- recommendations ----------------------------------------------------------


def _with_recommendations(report: BatchReport) -> BatchReport:
    from dataclasses import replace

    return replace(report, recommendations=tuple(_recommendations(report)))


def _recommendations(report: BatchReport) -> list[str]:
    attempts = report.attempts
    count = len(attempts)
    advice: list[str] = []
    percents = report.phase_percent()

    pyaes = sum(1 for a in attempts if a.aes_backend == "pyaes")
    if pyaes and pyaes / count >= 0.5:
        advice.append(
            f"El cifrado fue `pyaes` en {100 * pyaes / count:.0f} % de los intentos: "
            "instala `cryptg` (pip install cryptg) para acelerar las descargas."
        )

    for stat in report.by_type:
        kind = stat.label.split(" ")[0]
        limit = DEFAULT_FIRST_RESPONSE_SECONDS.get(kind)
        if limit and stat.first_max is not None and stat.first_max > 0.8 * limit:
            advice.append(
                f"{stat.label}: la primera respuesta llegó a {stat.first_max:.0f} s con un "
                f"plazo de {limit} s; sube el plazo de primera respuesta de ese tipo "
                "(Configuración > Ejecución > Bot y descargas)."
            )

    if percents["flood"] > 5:
        advice.append(
            f"FloodWait supone {percents['flood']:.0f} % del tiempo: reduce las descargas "
            "simultáneas o espacia las URLs."
        )
    if percents["end_wait"] > 15:
        advice.append(
            f"El fin de espera supone {percents['end_wait']:.0f} % del tiempo: comprueba que "
            "el modo de fin es EXPECTED_COUNT y no STABLE."
        )
    if percents["backoff"] > 15:
        advice.append(
            f"Las esperas de reintento suponen {percents['backoff']:.0f} % del tiempo: activa "
            "la cola global de reintentos o reduce la espera base."
        )

    deadline = sum(1 for a in attempts if a.exit_reason == "DEADLINE_FIRST")
    if deadline and deadline / count > 0.10:
        advice.append(
            f"{100 * deadline / count:.0f} % de los intentos no recibió respuesta del bot "
            "(DEADLINE_FIRST): el bot puede estar saturado o los plazos son cortos."
        )
    short_grace = sum(
        1 for a in attempts
        if a.exit_reason == "GRACE" and a.expected_items and a.files_count < a.expected_items
    )
    if short_grace:
        advice.append(
            f"{short_grace} intento(s) terminaron por silencio breve con menos ficheros de los "
            "anunciados: sube «Silencio breve (ms)»."
        )
    slow_move = percents["move"] > 10
    if slow_move:
        advice.append(
            f"El movimiento de ficheros supone {percents['move']:.0f} % del tiempo: revisa "
            "la velocidad del disco de destino."
        )
    return advice


# --- formatting ---------------------------------------------------------------


def _n(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}"


def _fmt_seconds(seconds: float) -> str:
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes:02d} min"
    if minutes:
        return f"{minutes} min {secs:02d} s"
    return f"{secs} s"


def _fmt_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


__all__ = [
    "AttemptRow",
    "BatchReport",
    "attempts_to_csv",
    "build_batch_report",
    "explain",
    "has_report_data",
    "percentile",
    "report_to_markdown",
]
