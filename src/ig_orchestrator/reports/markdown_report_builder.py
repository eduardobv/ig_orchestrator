from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from sqlite3 import Connection, Row

from ig_orchestrator.db import RunRepository
from ig_orchestrator.db._mapping import dump_path, load_datetime
from ig_orchestrator.logging_config import configure_app_logging, get_logger
from ig_orchestrator.models import PublicationType


logger = get_logger()


@dataclass(frozen=True, slots=True)
class MarkdownReportFile:
    filename: str
    directory: str


@dataclass(frozen=True, slots=True)
class MarkdownReportRow:
    url_job_id: int
    username: str
    publication_type: PublicationType
    url: str
    status: str
    files: tuple[MarkdownReportFile, ...] = ()


@dataclass(frozen=True, slots=True)
class MarkdownReportSummaryRow:
    username: str
    analyzed_urls: int
    unprocessed_urls: int
    duplicate_urls: int
    downloaded_files: int


@dataclass(frozen=True, slots=True)
class MarkdownReportDuplicateRow:
    username: str
    publication_type: PublicationType
    url: str


@dataclass(frozen=True, slots=True)
class MarkdownReport:
    run_id: int
    executed_at: datetime
    rows: tuple[MarkdownReportRow, ...]
    summary_rows: tuple[MarkdownReportSummaryRow, ...] = ()
    duplicate_rows: tuple[MarkdownReportDuplicateRow, ...] = ()


class MarkdownReportBuilder:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection
        self._run_repository = RunRepository(connection)

    def build(self, run_id: int) -> MarkdownReport:
        if run_id <= 0:
            raise ValueError("run_id must be positive")

        run = self._run_repository.get_by_id(run_id)
        if run is None:
            raise ValueError(f"Run not found: {run_id}")

        rows = _fetch_report_rows(self.connection, run_id)
        summary_rows = _fetch_summary_rows(self.connection, run_id)
        duplicate_rows = _fetch_duplicate_rows(self.connection, run_id)
        return MarkdownReport(
            run_id=run.id,
            executed_at=run.started_at,
            rows=tuple(rows),
            summary_rows=tuple(summary_rows),
            duplicate_rows=tuple(duplicate_rows),
        )

    def render(self, run_id: int) -> str:
        return render_markdown_report(self.build(run_id))

    def write(self, run_id: int, reports_folder: Path) -> Path:
        if not isinstance(reports_folder, Path):
            raise ValueError("reports_folder must be a pathlib.Path")

        report = self.build(run_id)
        reports_folder.mkdir(parents=True, exist_ok=True)
        report_path = _unique_report_path(reports_folder, report)
        report_path.write_text(render_markdown_report(report), encoding="utf-8")
        self.connection.execute(
            "UPDATE runs SET report_path = ? WHERE id = ?",
            (dump_path(report_path), run_id),
        )
        self.connection.commit()
        configure_app_logging()
        logger.info("Markdown report generated: run_id={} path={}", run_id, report_path)
        return report_path


def render_markdown_report(report: MarkdownReport) -> str:
    lines = [
        f"# Run {report.run_id} report",
        "",
        f"Fecha y hora de ejecucion: {_format_datetime(report.executed_at)}",
        "",
        "## Resumen por username",
        "",
        "| Numero | Username | Urls Analizadas | Urls no procesadas | Urls duplicadas | Files descargados |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for index, row in enumerate(report.summary_rows, start=1):
        lines.append(
            "| "
            + " | ".join(
                (
                    str(index),
                    _escape_cell(row.username),
                    str(row.analyzed_urls),
                    str(row.unprocessed_urls),
                    str(row.duplicate_urls),
                    str(row.downloaded_files),
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Detalle",
            "",
        "| N | Id Job | Username | Tipo | Urls | Fichero | Cantidad | Estado | Directory |",
        "|---:|---:|---|---|---|---|---:|---|---|",
        ]
    )
    for index, row in enumerate(report.rows, start=1):
        lines.append(
            "| "
            + " | ".join(
                (
                    str(index),
                    str(row.url_job_id),
                    _escape_cell(row.username),
                    _escape_cell(_format_publication_type(row.publication_type)),
                    _escape_cell(row.url),
                    _format_files_cell(row.files),
                    str(len(row.files)),
                    _escape_cell(row.status),
                    _format_directories_cell(row.files),
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## URLs duplicadas",
            "",
            "| Username | Tipo | Urls |",
            "|---|---|---|",
        ]
    )
    if report.duplicate_rows:
        for row in report.duplicate_rows:
            lines.append(
                "| "
                + " | ".join(
                    (
                        _escape_cell(row.username),
                        _escape_cell(_format_publication_type(row.publication_type)),
                        _escape_cell(row.url),
                    )
                )
                + " |"
            )
    else:
        lines.append("| 0 duplicates |  |  |")
    return "\n".join(lines) + "\n"


def _fetch_report_rows(
    connection: Connection,
    run_id: int,
) -> list[MarkdownReportRow]:
    rows = connection.execute(
        """
        SELECT
            url_jobs.id AS url_job_id,
            accounts.username AS username,
            url_jobs.publication_type AS publication_type,
            url_jobs.url AS url,
            url_jobs.status AS status,
            download_files.original_path AS original_path,
            download_files.working_path AS working_path,
            download_files.final_path AS final_path
        FROM runs
        JOIN accounts
            ON (
                (runs.account_id IS NOT NULL AND accounts.id = runs.account_id)
                OR (
                    runs.account_id IS NULL
                    AND runs.batch_id IS NOT NULL
                    AND accounts.batch_id = runs.batch_id
                )
            )
        JOIN url_jobs ON url_jobs.account_id = accounts.id
        LEFT JOIN download_files ON download_files.url_job_id = url_jobs.id
        WHERE runs.id = ?
            AND (url_jobs.run_id IS NULL OR url_jobs.run_id = runs.id)
        ORDER BY accounts.id, url_jobs.id, download_files.id
        """,
        (run_id,),
    ).fetchall()

    grouped: dict[int, MarkdownReportRow] = {}
    files_by_job: dict[int, list[MarkdownReportFile]] = {}
    for row in rows:
        job_id = row["url_job_id"]
        if job_id not in grouped:
            grouped[job_id] = MarkdownReportRow(
                url_job_id=job_id,
                username=row["username"],
                publication_type=PublicationType(row["publication_type"]),
                url=row["url"],
                status=row["status"],
            )
            files_by_job[job_id] = []
        file_info = _row_to_report_file(row)
        if file_info is not None:
            files_by_job[job_id].append(file_info)

    return [
        MarkdownReportRow(
            url_job_id=row.url_job_id,
            username=row.username,
            publication_type=row.publication_type,
            url=row.url,
            status=row.status,
            files=tuple(files_by_job[job_id]),
        )
        for job_id, row in grouped.items()
    ]


def _fetch_summary_rows(
    connection: Connection,
    run_id: int,
) -> list[MarkdownReportSummaryRow]:
    account_rows = _fetch_run_accounts(connection, run_id)
    summary_rows: list[MarkdownReportSummaryRow] = []
    for account_row in account_rows:
        account_id = account_row["account_id"]
        analyzed_urls = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM url_jobs
            WHERE account_id = ?
              AND (run_id IS NULL OR run_id = ?)
            """,
            (account_id, run_id),
        ).fetchone()["count"]
        unprocessed_urls = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM url_jobs
            WHERE account_id = ?
              AND (run_id IS NULL OR run_id = ?)
              AND status NOT IN ('COMPLETED', 'FAILED_FINAL')
            """,
            (account_id, run_id),
        ).fetchone()["count"]
        duplicate_urls = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM duplicate_url_jobs
            WHERE account_id = ?
              AND (run_id IS NULL OR run_id = ?)
            """,
            (account_id, run_id),
        ).fetchone()["count"]
        downloaded_files = connection.execute(
            """
            SELECT COUNT(download_files.id) AS count
            FROM url_jobs
            JOIN download_files ON download_files.url_job_id = url_jobs.id
            WHERE url_jobs.account_id = ?
              AND (url_jobs.run_id IS NULL OR url_jobs.run_id = ?)
            """,
            (account_id, run_id),
        ).fetchone()["count"]
        summary_rows.append(
            MarkdownReportSummaryRow(
                username=account_row["username"],
                analyzed_urls=analyzed_urls,
                unprocessed_urls=unprocessed_urls,
                duplicate_urls=duplicate_urls,
                downloaded_files=downloaded_files,
            )
        )
    return summary_rows


def _fetch_duplicate_rows(
    connection: Connection,
    run_id: int,
) -> list[MarkdownReportDuplicateRow]:
    rows = connection.execute(
        """
        SELECT
            accounts.username AS username,
            duplicate_url_jobs.publication_type AS publication_type,
            duplicate_url_jobs.url AS url
        FROM duplicate_url_jobs
        JOIN accounts ON accounts.id = duplicate_url_jobs.account_id
        JOIN runs
            ON (
                (runs.account_id IS NOT NULL AND accounts.id = runs.account_id)
                OR (
                    runs.account_id IS NULL
                    AND runs.batch_id IS NOT NULL
                    AND accounts.batch_id = runs.batch_id
                )
            )
        WHERE runs.id = ?
          AND (
              duplicate_url_jobs.run_id IS NULL
              OR duplicate_url_jobs.run_id = runs.id
          )
        ORDER BY accounts.id, duplicate_url_jobs.id
        """,
        (run_id,),
    ).fetchall()
    return [
        MarkdownReportDuplicateRow(
            username=row["username"],
            publication_type=PublicationType(row["publication_type"]),
            url=row["url"],
        )
        for row in rows
    ]


def _fetch_run_accounts(connection: Connection, run_id: int) -> list[Row]:
    return connection.execute(
        """
        SELECT accounts.id AS account_id, accounts.username AS username
        FROM runs
        JOIN accounts
            ON (
                (runs.account_id IS NOT NULL AND accounts.id = runs.account_id)
                OR (
                    runs.account_id IS NULL
                    AND runs.batch_id IS NOT NULL
                    AND accounts.batch_id = runs.batch_id
                )
            )
        WHERE runs.id = ?
        ORDER BY accounts.id
        """,
        (run_id,),
    ).fetchall()


def _row_to_report_file(row: Row) -> MarkdownReportFile | None:
    path_text = row["final_path"] or row["working_path"] or row["original_path"]
    if path_text is None:
        return None
    path = Path(path_text)
    return MarkdownReportFile(filename=path.name, directory=str(path.parent))


def _format_files_cell(files: tuple[MarkdownReportFile, ...]) -> str:
    if not files:
        return "0 files"
    return "<br>" + "<br>".join(f"- {_escape_cell(file.filename)}" for file in files)


def _format_directories_cell(files: tuple[MarkdownReportFile, ...]) -> str:
    if not files:
        return ""
    directories = []
    for file in files:
        if file.directory not in directories:
            directories.append(file.directory)
    if len(directories) == 1:
        return _escape_cell(directories[0])
    return "<br>" + "<br>".join(f"- {_escape_cell(directory)}" for directory in directories)


def _format_publication_type(publication_type: PublicationType) -> str:
    return publication_type.value.title()


def _format_datetime(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _escape_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def _unique_report_path(reports_folder: Path, report: MarkdownReport) -> Path:
    timestamp = report.executed_at.strftime("%Y%m%d_%H%M%S")
    base_path = reports_folder / f"run_{timestamp}.md"
    if not base_path.exists():
        return base_path

    counter = 2
    while True:
        candidate = reports_folder / f"run_{timestamp}_{counter}.md"
        if not candidate.exists():
            return candidate
        counter += 1


__all__ = [
    "MarkdownReport",
    "MarkdownReportBuilder",
    "MarkdownReportDuplicateRow",
    "MarkdownReportFile",
    "MarkdownReportRow",
    "MarkdownReportSummaryRow",
    "render_markdown_report",
]
