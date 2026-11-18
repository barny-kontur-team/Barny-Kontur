"""Правила фильтра ИИ-помощника: модель подбирает условия, код отбирает клиентов.

Тесты не ходят в сеть и не зависят от Excel — только логика отбора.
"""
from datetime import date

import pytest

from ai.schemas import (
    ALL_PASSED,
    DECREASING,
    NO_PREVIOUS,
    NOT_DECREASING,
    RECURRED,
    ClientFilter,
    ClientView,
    FilterError,
    SnapshotView,
    apply_filter,
    matches,
)


def snap(slice_id: str, day: str, missing: int, total: int | None, change: str,
         *, novice: bool = False, chronic: bool = False, pool: bool = False) -> SnapshotView:
    return SnapshotView(
        slice_id=slice_id, period="III кв. 2026", date=date.fromisoformat(day),
        missing=missing, total=total, change=change, is_novice=novice,
        is_chronic=chronic, category=change, in_pool=pool,
    )


def client(code: str = "1000001", *, snapshots=None, last_call: str | None = "2026-05-12",
           do_not_call: bool = False, stage: str | None = None,
           connected: str | None = None) -> ClientView:
    return ClientView(
        code=code, name=f"ООО «Тест-{code}»", inn="7701000001",
        connected_at=date.fromisoformat(connected) if connected else None,
        do_not_call=do_not_call, stage=stage,
        last_call_date=date.fromisoformat(last_call) if last_call else None,
        snapshots=snapshots or [],
    )


def test_unknown_filter_field_is_error():
    with pytest.raises(FilterError):
        ClientFilter.from_dict({"unknown_field": 1})


def test_bad_change_value_is_error():
    with pytest.raises(FilterError):
        ClientFilter.from_dict({"last_change_equals": "Растёт"})


def test_bad_date_is_error():
    with pytest.raises(FilterError):
        ClientFilter.from_dict({"last_call_before": "01.10.2026"})


def test_share_threshold_is_strict():
    flt = ClientFilter.from_dict({"share_last_gt": 25})
    exact = client(snapshots=[snap("S1", "2026-10-27", 25, 100, NOT_DECREASING)])
    above = client("1000002", snapshots=[snap("S1", "2026-10-27", 26, 100, NOT_DECREASING)])
    assert not matches(exact, flt)
    assert matches(above, flt)


def test_zero_total_has_no_share():
    item = client(snapshots=[snap("S1", "2026-10-27", 0, 0, ALL_PASSED)])
    assert item.last.share is None
    assert matches(item, ClientFilter.from_dict({"total_zero_last": True}))
    assert not matches(item, ClientFilter.from_dict({"share_last_gt": 0}))


def test_last_call_before_counts_client_without_calls():
    flt = ClientFilter.from_dict({"last_call_before": "2026-10-01"})
    never_called = client("1000006", last_call=None)
    old_call = client("1000007", last_call="2026-06-12")
    recent_call = client("1000010", last_call="2026-08-25")
    assert matches(never_called, flt)
    assert matches(old_call, flt)
    assert matches(recent_call, flt)  # август раньше октября
    assert not matches(client("1000011", last_call="2026-10-05"), flt)


def test_no_recurrence_ever():
    flt = ClientFilter.from_dict({"no_recurrence_ever": True})
    quiet = client(snapshots=[
        snap("S1", "2026-04-20", 5, 20, NO_PREVIOUS),
        snap("S2", "2026-05-18", 0, 20, ALL_PASSED),
    ])
    returned = client("1000002", snapshots=[
        snap("S1", "2026-04-20", 2, 20, NO_PREVIOUS),
        snap("S2", "2026-05-18", 0, 20, ALL_PASSED),
        snap("S3", "2026-07-20", 2, 20, RECURRED),
    ])
    assert matches(quiet, flt)
    assert not matches(returned, flt)


def test_last_two_changes_equal():
    flt = ClientFilter.from_dict({"last_two_changes_equal": "Уменьшается"})
    two_slices = client(snapshots=[
        snap("S5", "2026-10-20", 5, 26, DECREASING),
        snap("S6", "2026-10-27", 4, 26, DECREASING),
    ])
    broke = client("1000002", snapshots=[
        snap("S5", "2026-10-20", 4, 25, DECREASING),
        snap("S6", "2026-10-27", 4, 25, NOT_DECREASING),
    ])
    only_one = client("1000003", snapshots=[snap("S6", "2026-10-27", 4, 25, DECREASING)])
    assert matches(two_slices, flt)
    assert not matches(broke, flt)
    assert not matches(only_one, flt)


def test_novice_last_differs_from_novice_with_missing_ever():
    novice_now = client(snapshots=[
        snap("S5", "2026-10-20", 0, 100, ALL_PASSED, novice=True),
        snap("S6", "2026-10-27", 0, 100, ALL_PASSED, novice=True),
    ])
    assert matches(novice_now, ClientFilter.from_dict({"novice_last": True}))
    assert not matches(novice_now, ClientFilter.from_dict({"novice_with_missing_ever": True}))

    had_missing = client("1000002", snapshots=[
        snap("S3", "2026-07-20", 2, 100, NO_PREVIOUS, novice=True),
        snap("S6", "2026-10-27", 0, 100, ALL_PASSED, novice=False),
    ])
    assert not matches(had_missing, ClientFilter.from_dict({"novice_last": True}))
    assert matches(had_missing, ClientFilter.from_dict({"novice_with_missing_ever": True}))


def test_do_not_call_is_independent_of_pool():
    blocked = client(snapshots=[snap("S6", "2026-10-27", 8, 50, NOT_DECREASING, pool=False)],
                     do_not_call=True)
    assert matches(blocked, ClientFilter.from_dict({"do_not_call": True}))
    assert not matches(blocked, ClientFilter.from_dict({"in_pool_last": True}))


def test_apply_filter_returns_sorted_codes():
    clients = [
        client("1000003", snapshots=[snap("S6", "2026-10-27", 1, 10, DECREASING, pool=True)]),
        client("1000001", snapshots=[snap("S6", "2026-10-27", 0, 10, ALL_PASSED, pool=False)]),
        client("1000002", snapshots=[snap("S6", "2026-10-27", 3, 10, DECREASING, pool=True)]),
    ]
    found = apply_filter(clients, ClientFilter.from_dict({"in_pool_last": True}))
    assert [c.code for c in found] == ["1000002", "1000003"]


def test_empty_filter_matches_everyone_but_is_flagged():
    flt = ClientFilter.from_dict({})
    assert flt.is_empty()
    assert matches(client(snapshots=[]), flt)
