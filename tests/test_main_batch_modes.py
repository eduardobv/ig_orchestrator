from __future__ import annotations

from datetime import date
from pathlib import Path

from ig_orchestrator.db import (
    AccountRepository,
    BatchRepository,
    UrlJobRepository,
    connect,
    init_database,
)
from ig_orchestrator.main import _joined_batch_ids
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


def test_joined_batch_ids_supports_pending_before_and_after_new_batch(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orchestrator.db"
    init_database(db_path)

    with connect(db_path) as connection:
        batch_repo = BatchRepository(connection)
        pending = batch_repo.create(
            InputBatch(
                batch_name="pending",
                schema_version="1.0",
                status=InputBatchStatus.PARTIAL,
            )
        )
        new = batch_repo.create(
            InputBatch(
                batch_name="new",
                schema_version="1.0",
                status=InputBatchStatus.IMPORTED,
            )
        )
        account = AccountRepository(connection).create(
            Account(
                batch_id=pending.id,
                username="pending_user",
                start_now_date=date(2026, 6, 21),
                download_stories=False,
                status=AccountStatus.PARTIAL,
            )
        )
        UrlJobRepository(connection).create(
            UrlJob(
                account_id=account.id,
                url="https://www.instagram.com/reel/ABC123/",
                publication_type=PublicationType.REEL,
                source=UrlSource.INPUT_URL,
                status=UrlJobStatus.RETRY_PENDING,
            )
        )

        assert _joined_batch_ids(
            batch_repository=batch_repo,
            new_batch_id=new.id,
            join_after_pending_batch_id=pending.id,
            join_before_pending_batch_id=None,
        ) == [pending.id, new.id]
        assert _joined_batch_ids(
            batch_repository=batch_repo,
            new_batch_id=new.id,
            join_after_pending_batch_id=None,
            join_before_pending_batch_id=pending.id,
        ) == [new.id, pending.id]
