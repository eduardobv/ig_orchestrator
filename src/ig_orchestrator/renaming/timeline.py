"""Date assignment for downloaded files (port of ``sc2`` ``timeline_builder.py``).

Behaviour is kept identical to ``sc2`` **including the order of the calls to the random generator**,
so that with the same seed both engines produce the same names. Randomness and "now" are injected.

Vocabulary: ``num_id`` is the Instagram media id (int), an *entry* (piece) is either a ``consult`` file
(already in the library, has a date) or a ``manual`` block (downloaded files whose ids share the first 6 digits).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ig_orchestrator.renaming.files import ConsultItem


@dataclass(slots=True)
class TimelineContext:
    rng: random.Random
    now: datetime
    forced_user_id: str = ""  # only for new accounts (``flagNew`` + owner id)
    flag_new: bool = False
    extra: dict = field(default_factory=dict)


def consult_dict(item: ConsultItem) -> dict:
    return {
        "filename": item.filename,
        "date": item.date,
        "num_id": item.num_id,
        "user_id": item.user_id,
        "ext": item.ext,
        "rest": item.rest,
    }


def build_combined_timeline(consult_files: list[ConsultItem], manual_groups: list[list[dict]]) -> list[dict]:
    combined = []
    combined.extend(create_consult_pieces(consult_files))
    combined.extend(create_manual_pieces(manual_groups))
    combined.sort(key=lambda entry: entry["min_id"])
    return combined


def create_consult_pieces(consult_files: list[ConsultItem]) -> list[dict]:
    pieces = []
    for item in consult_files:
        data = consult_dict(item)
        pieces.append(
            {"source": "consult", "items": [data], "min_id": data["num_id"], "max_id": data["num_id"], "fecha": data["date"]}
        )
    return pieces


def create_manual_pieces(manual_groups: list[list[dict]]) -> list[dict]:
    pieces = []
    for group in manual_groups:
        if not group:
            continue
        pieces.append(
            {
                "source": "manual",
                "items": group,
                "min_id": min(f["num_id"] for f in group),
                "max_id": max(f["num_id"] for f in group),
                "fecha": None,
            }
        )
    return pieces


def assign_dates_to_manual_tuples(entries: list[dict], ctx: TimelineContext) -> None:
    propagate_user_id_forward(entries, ctx)
    propagate_user_id_backward(entries, ctx)
    now = ctx.now
    last_consult_date = find_last_consult_date(entries)
    bands = find_manual_bands_above_last_consult(entries, last_consult_date)
    assign_dates_to_bands_above(entries, bands, last_consult_date, now, ctx.rng)
    assign_dates_to_other_manual_blocks(entries, now, ctx.rng)


def propagate_user_id_forward(entries: list[dict], ctx: TimelineContext) -> None:
    if ctx.forced_user_id:
        for entry in entries:
            if entry["source"] == "manual":
                assign_user_id_to_items(entry["items"], ctx.forced_user_id)
        return
    last_known = None
    for entry in entries:
        if entry["source"] == "consult":
            last_known = entry["items"][0]["user_id"]
        elif entry["source"] == "manual" and last_known is not None:
            assign_user_id_to_items(entry["items"], last_known)


def propagate_user_id_backward(entries: list[dict], ctx: TimelineContext) -> None:
    if ctx.forced_user_id:
        for entry in entries:
            if entry["source"] == "manual":
                assign_user_id_to_items(entry["items"], ctx.forced_user_id)
        return
    next_known = None
    for entry in reversed(entries):
        if entry["source"] == "consult":
            next_known = entry["items"][0]["user_id"]
        elif entry["source"] == "manual" and next_known is not None:
            assign_user_id_if_missing(entry["items"], next_known)


def assign_user_id_to_items(items: list[dict], user_id: str) -> None:
    for item in items:
        item["user_id"] = user_id


def assign_user_id_if_missing(items: list[dict], user_id: str) -> None:
    for item in items:
        if "user_id" not in item or not item["user_id"] or item["user_id"] == "unknown":
            item["user_id"] = user_id


def find_last_consult_date(entries: list[dict]) -> datetime | None:
    dates = [e["fecha"] for e in entries if e["source"] == "consult"]
    return max(dates) if dates else None


def find_manual_bands_above_last_consult(entries: list[dict], last_consult_date) -> list[tuple[int, int]]:
    bands = []
    n = len(entries)
    last_indices = [i for i, e in enumerate(entries) if e["source"] == "consult" and e["fecha"] == last_consult_date]
    last_idx = max(last_indices) if last_indices else -1
    i = 0
    while i < n:
        if entries[i]["source"] != "manual":
            i += 1
            continue
        end = find_manual_block_end(entries, i)
        if last_idx != -1 and i > last_idx:
            bands.append((i, end))
        i = end + 1
    return bands


def find_manual_block_end(entries: list[dict], start_idx: int) -> int:
    end = start_idx
    n = len(entries)
    while end + 1 < n and entries[end + 1]["source"] == "manual":
        end += 1
    return end


def assign_dates_to_bands_above(entries, bands, last_consult_date, now, rng: random.Random) -> None:
    for start, end in bands:
        count = end - start + 1
        total_seconds = (now - last_consult_date).total_seconds()
        if count == 1:
            fechas = [now]
        else:
            fechas = [
                safe_replace_minutes_seconds(
                    last_consult_date + timedelta(seconds=total_seconds * (k + 1) / count), rng
                )
                for k in range(count)
            ]
        assign_dates_to_block(entries, start, end, fechas)


def safe_replace_minutes_seconds(value: datetime, rng: random.Random) -> datetime:
    extra_minutes = rng.randint(0, 59)
    extra_seconds = rng.randint(0, 59)
    try:
        return value.replace(minute=extra_minutes, second=extra_seconds)
    except ValueError:
        return value


def assign_dates_to_block(entries: list[dict], start_idx: int, end_idx: int, fechas: list[datetime]) -> None:
    for offset, fecha in enumerate(fechas):
        entries[start_idx + offset]["fecha"] = fecha


def assign_dates_to_other_manual_blocks(entries: list[dict], now: datetime, rng: random.Random) -> None:
    n = len(entries)
    idx = 0
    while idx < n:
        entry = entries[idx]
        if entry["source"] != "manual" or ("fecha" in entry and entry["fecha"] is not None):
            idx += 1
            continue
        before_idx = find_previous_consult_or_manual(entries, idx)
        after_idx = find_next_consult_or_manual(entries, idx)
        before_date = entries[before_idx]["fecha"] if before_idx is not None else None
        after_date = entries[after_idx]["fecha"] if after_idx is not None else None
        stretch_start = idx
        stretch_end = find_manual_block_end(entries, idx)
        num_tuples = stretch_end - stretch_start + 1
        fechas = calculate_dates_for_manual_block(before_date, after_date, num_tuples, now, rng)
        assign_dates_to_block(entries, stretch_start, stretch_end, fechas)
        idx = stretch_end + 1


def find_previous_consult_or_manual(entries: list[dict], start_idx: int) -> int | None:
    idx = start_idx - 1
    while idx >= 0:
        if entries[idx]["source"] in ("consult", "manual") and entries[idx].get("fecha") is not None:
            return idx
        idx -= 1
    return None


def find_next_consult_or_manual(entries: list[dict], start_idx: int) -> int | None:
    idx = start_idx + 1
    n = len(entries)
    while idx < n:
        if entries[idx]["source"] in ("consult", "manual") and entries[idx].get("fecha") is not None:
            return idx
        idx += 1
    return None


def calculate_dates_for_manual_block(before_date, after_date, num_tuples: int, now: datetime, rng: random.Random):
    if before_date and after_date:
        delta = (after_date - before_date).total_seconds() / (num_tuples + 1)
        return [before_date + timedelta(seconds=delta * (k + 1)) for k in range(num_tuples)]
    if before_date and not after_date:
        return [
            before_date
            - timedelta(hours=num_tuples - k, minutes=rng.randint(0, 59), seconds=rng.randint(0, 59))
            for k in range(num_tuples)
        ]
    return [
        now - timedelta(hours=num_tuples - k, minutes=rng.randint(0, 59), seconds=rng.randint(0, 59))
        for k in range(num_tuples)
    ]


def generate_descending_times(base: datetime, count: int) -> list[datetime]:
    """Same date, each next item one hour (or minute, or second) earlier, to keep the id order."""

    times = []
    current = base
    for _ in range(count):
        times.append(current)
        if current.hour > 0:
            current = current.replace(hour=current.hour - 1)
        elif current.minute > 0:
            current = current.replace(minute=current.minute - 1)
        elif current.second > 0:
            current = current.replace(second=current.second - 1)
    return times


def assign_dates_for_new_entries(entries: list[dict], start_date: datetime, end_date: datetime) -> None:
    """New account: manual blocks evenly spread between its start date and the run date."""

    blocks = [entry for entry in entries if entry["source"] == "manual"]
    count = len(blocks)
    if count == 0:
        return
    if count == 1:
        blocks[0]["fecha"] = start_date
        return
    for idx, entry in enumerate(blocks):
        entry["fecha"] = start_date + (end_date - start_date) * (idx / (count - 1))


def user_id_of_entry(entry: dict, ctx: TimelineContext) -> str:
    for item in entry["items"]:
        if "user_id" in item and item["user_id"]:
            return item["user_id"]
    if ctx.flag_new and ctx.forced_user_id:
        return ctx.forced_user_id
    return "unknown"


def build_new_basename(date_str: str, num_id: int, user_id: str, ext: str) -> str:
    return f"{date_str} {num_id}_{user_id}_manual.{ext}"
