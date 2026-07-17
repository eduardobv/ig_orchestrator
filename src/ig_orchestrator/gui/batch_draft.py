from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AccountDraft:
    username: str
    download_stories: bool = False
    urls: list[str] = field(default_factory=list)
    start_now_date: str = ""
    is_new_account: bool = False
    owner_id: str = ""
    start_init_date: str = ""
    destination_path: str = ""


@dataclass(slots=True)
class BatchDraft:
    batch_name: str
    default_start_now_date: str
    accounts: list[AccountDraft] = field(default_factory=list)
    schema_version: str = "1.0"
