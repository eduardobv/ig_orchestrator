from datetime import date
from pathlib import Path
import time

from ig_orchestrator.db import (
    AccountHistoryRepository,
    AccountRepository,
    BatchRepository,
    UrlJobRepository,
    connect,
    init_gui_database,
)
from ig_orchestrator.gui.batch_draft import AccountDraft, BatchDraft
from ig_orchestrator.gui.batch_draft_service import save_batch_draft
from ig_orchestrator.gui.batch_resume_service import load_batch_draft
from ig_orchestrator.models import (
    Account,
    AccountStatus,
    InputBatch,
    InputBatchStatus,
    PublicationType,
    UrlJob,
    UrlJobStatus,
    UrlSource,
)


def test_gui_repositories_round_trip_account_and_urls(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator_gui.sqlite"
    init_gui_database(db_path)
    with connect(db_path) as connection:
        history = AccountHistoryRepository(connection)
        stored = history.create_or_get("lidieblush")
        history.update_rename_metadata(
            "lidieblush",
            owner_id="abc",
            destination_path=r"G:\4K Stogram\00.MODELS-A\Lidiia-Filippova",
            start_init_date="2026-01-01",
        )
        reloaded = history.get_by_user_name("lidieblush")
        assert reloaded is not None
        assert reloaded.id == stored.id
        assert reloaded.field1 == r"G:\4K Stogram\00.MODELS-A\Lidiia-Filippova"
        assert reloaded.field2 == "2026-01-01"

        batch = BatchRepository(connection).create(
            InputBatch(
                batch_name="gui_round_trip",
                schema_version="1.0",
                status=InputBatchStatus.DRAFT,
            )
        )
        account = AccountRepository(connection).create(
            Account(
                batch_id=batch.id,
                username="lidieblush",
                start_now_date=date.today(),
                download_stories=True,
                status=AccountStatus.PENDING,
            )
        )
        job = UrlJobRepository(connection).create(
            UrlJob(
                account_id=account.id,
                url="https://www.instagram.com/p/DRnU6pdjoXg/?img_index=1",
                publication_type=PublicationType.POST,
                source=UrlSource.INPUT_URL,
                status=UrlJobStatus.PENDING,
            )
        )
        listed = AccountRepository(connection).list_by_batch(batch.id)
        jobs = UrlJobRepository(connection).list_by_account(account.id)
        assert listed[0].username == "lidieblush"
        assert listed[0].generated_story_url == (
            "https://www.instagram.com/stories/lidieblush/"
        )
        assert jobs[0].id == job.id
        assert jobs[0].publication_type is PublicationType.POST


def test_save_batch_draft_on_gui_schema_is_fast_and_loadable(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator_gui.sqlite"
    init_gui_database(db_path)
    urls = [
        f"https://www.instagram.com/p/URL{index:04d}/?img_index=1"
        for index in range(40)
    ]
    draft = BatchDraft(
        batch_name="gui_bulk_batch",
        default_start_now_date=date.today().isoformat(),
        accounts=[
            AccountDraft(
                username="bulk_user",
                download_stories=True,
                urls=urls,
                start_now_date=date.today().isoformat(),
            )
        ],
    )
    with connect(db_path) as connection:
        started = time.perf_counter()
        result = save_batch_draft(draft, connection)
        elapsed = time.perf_counter() - started
        loaded = load_batch_draft(connection, result.batch.id)
        compat_count = int(
            connection.execute("SELECT COUNT(*) FROM url_jobs").fetchone()[0]
        )
        real_count = int(
            connection.execute("SELECT COUNT(*) FROM batch_urls").fetchone()[0]
        )

    assert result.batch.id is not None
    assert elapsed < 1.0
    assert loaded.batch_name == "gui_bulk_batch"
    assert loaded.accounts[0].username == "bulk_user"
    assert len(loaded.accounts[0].urls) == 40
    assert loaded.accounts[0].download_stories is True
    assert compat_count == real_count == 41  # 40 posts + generated story


def test_compat_view_updates_batch_status(tmp_path: Path) -> None:
    db_path = tmp_path / "orchestrator_gui.sqlite"
    init_gui_database(db_path)
    with connect(db_path) as connection:
        batch = BatchRepository(connection).create(
            InputBatch(
                batch_name="compat_status",
                schema_version="1.0",
                status=InputBatchStatus.DRAFT,
            )
        )
        connection.execute(
            "UPDATE input_batches SET status = 'IMPORTED' WHERE id = ?",
            (batch.id,),
        )
        connection.commit()
        stored = BatchRepository(connection).get_by_id(batch.id)
        row = connection.execute(
            "SELECT status FROM input_batches WHERE id = ?",
            (batch.id,),
        ).fetchone()

    assert stored is not None
    assert stored.status is InputBatchStatus.IMPORTED
    assert row["status"] == "IMPORTED"
