"""Звонки и работа с клиентом: взять в работу, записать звонок, история.

Правила:
- у клиента не больше одного активного цикла (WC-01) — держит уникальный индекс;
- взятие в работу атомарно: при гонке двух операторов выигрывает один (H-09);
- забрать клиента у коллеги можно только явно (`takeover=True`);
- звонок пишет только тот, кто держит клиента;
- срок, который назвал клиент, обязателен (spec.md).

Модуль не знает про importer, dynamics и ai — только база и свои таблицы.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import AppUser, Client, Communication, WorkCycle

STAGE_FIRST_CALL = "Первый звонок"
STAGE_DETECTED = "Выявлены непереданные документы"
STAGE_CLOSED = "Работа завершена"
STAGES = (
    STAGE_DETECTED,
    STAGE_FIRST_CALL,
    "Ожидание срока",
    "Повторная проверка",
    "Претензия",
    STAGE_CLOSED,
)

CONTACT_CALL = "звонок"
CONTACT_TYPES = ("звонок", "письмо", "комментарий")


class CallsError(Exception):
    """Базовая ошибка модуля звонков."""


class ClientNotFound(CallsError):
    def __init__(self, client_id: int) -> None:
        super().__init__(f"Клиент {client_id} не найден")


class OperatorNotFound(CallsError):
    def __init__(self, operator_id: int) -> None:
        super().__init__(f"Пользователь {operator_id} не найден или отключён")


class AlreadyTaken(CallsError):
    def __init__(self, operator_id: int | None, operator_name: str | None) -> None:
        self.operator_id = operator_id
        self.operator_name = operator_name
        who = operator_name or "другой оператор"
        super().__init__(f"Клиента уже взял в работу {who} (id {operator_id})")


class NoActiveCycle(CallsError):
    def __init__(self) -> None:
        super().__init__("Сначала возьмите клиента в работу")


class NotOwner(CallsError):
    def __init__(self, operator_id: int | None, operator_name: str | None) -> None:
        self.operator_id = operator_id
        self.operator_name = operator_name
        who = operator_name or "другой оператор"
        super().__init__(f"Клиента ведёт {who} (id {operator_id})")


def _now() -> datetime:
    return datetime.now()


def _get_client(db: Session, client_id: int) -> Client:
    client = db.get(Client, client_id)
    if client is None:
        raise ClientNotFound(client_id)
    return client


def _get_operator(db: Session, operator_id: int) -> AppUser:
    user = db.get(AppUser, operator_id)
    if user is None or not user.is_active:
        raise OperatorNotFound(operator_id)
    return user


def _active_cycle(db: Session, client_id: int) -> WorkCycle | None:
    return db.scalar(
        select(WorkCycle)
        .where(WorkCycle.client_id == client_id, WorkCycle.closed_at.is_(None))
        .order_by(WorkCycle.id.desc())
    )


def operator_name(db: Session, operator_id: int | None) -> str | None:
    if operator_id is None:
        return None
    user = db.get(AppUser, operator_id)
    return user.full_name if user else None


def take_client(db: Session, client_id: int, operator_id: int,
                takeover: bool = False) -> tuple[WorkCycle, bool]:
    """Взять клиента в работу. Возвращает (цикл, был ли перехват)."""
    _get_client(db, client_id)
    _get_operator(db, operator_id)

    cycle = _active_cycle(db, client_id)
    if cycle is None:
        cycle = WorkCycle(
            client_id=client_id,
            operator_id=operator_id,
            stage=STAGE_FIRST_CALL,
            started_at=_now(),
        )
        db.add(cycle)
        try:
            db.commit()
        except IntegrityError:
            # Параллельный оператор успел первым: индекс WC-01 не дал создать второй
            # активный цикл. Перечитываем и разбираем владение ниже.
            db.rollback()
            cycle = _active_cycle(db, client_id)
            if cycle is None:
                raise CallsError("Не удалось взять клиента, повторите") from None
        else:
            db.refresh(cycle)
            return cycle, False

    if cycle.operator_id == operator_id:
        return cycle, False

    if not takeover:
        raise AlreadyTaken(cycle.operator_id, operator_name(db, cycle.operator_id))

    cycle.operator_id = operator_id
    db.commit()
    db.refresh(cycle)
    return cycle, True


def add_call(db: Session, client_id: int, operator_id: int, promised_date: date, *,
             result: str | None = None, comment: str | None = None,
             contact_type: str = CONTACT_CALL,
             called_at: datetime | None = None,
             stage: str | None = None) -> Communication:
    """Записать звонок. Срок клиента обязателен."""
    _get_client(db, client_id)
    _get_operator(db, operator_id)

    cycle = _active_cycle(db, client_id)
    if cycle is None:
        raise NoActiveCycle()
    if cycle.operator_id != operator_id:
        raise NotOwner(cycle.operator_id, operator_name(db, cycle.operator_id))
    if contact_type not in CONTACT_TYPES:
        raise CallsError(f"Неизвестный тип контакта: {contact_type}")
    if stage is not None and stage not in STAGES:
        raise CallsError(f"Неизвестный этап: {stage}")

    communication = Communication(
        client_id=client_id,
        cycle_id=cycle.id,
        user_id=operator_id,
        contact_type=contact_type,
        result=result,
        comment=comment,
        promised_date=promised_date,
        created_at=called_at or _now(),
    )
    db.add(communication)
    if stage == STAGE_CLOSED:
        cycle.stage = STAGE_CLOSED
        cycle.closed_at = _now()
        cycle.close_reason = STAGE_CLOSED
    elif stage is not None:
        cycle.stage = stage
    elif cycle.stage == STAGE_DETECTED:
        cycle.stage = STAGE_FIRST_CALL
    db.commit()
    db.refresh(communication)
    return communication


def list_calls(db: Session, client_id: int) -> list[tuple[Communication, str]]:
    """История коммуникаций по клиенту: новые сверху."""
    _get_client(db, client_id)
    rows = db.execute(
        select(Communication, AppUser.full_name)
        .join(AppUser, AppUser.id == Communication.user_id)
        .where(Communication.client_id == client_id)
        .order_by(Communication.created_at.desc(), Communication.id.desc())
    ).all()
    return [(communication, name) for communication, name in rows]


def get_work(db: Session, client_id: int) -> tuple[WorkCycle | None, str | None]:
    """Кто ведёт клиента сейчас и на каком этапе."""
    _get_client(db, client_id)
    cycle = _active_cycle(db, client_id)
    if cycle is None:
        return None, None
    return cycle, operator_name(db, cycle.operator_id)


def list_work(db: Session) -> list[dict]:
    """Все активные циклы: ответственный, этап и последний звонок."""
    cycles = db.scalars(
        select(WorkCycle)
        .where(WorkCycle.closed_at.is_(None))
        .order_by(WorkCycle.id)
    ).all()
    result: list[dict] = []
    for cycle in cycles:
        last_call = db.scalar(
            select(Communication)
            .where(Communication.client_id == cycle.client_id)
            .order_by(Communication.created_at.desc(), Communication.id.desc())
            .limit(1)
        )
        result.append({
            "client_id": cycle.client_id,
            "cycle_id": cycle.id,
            "operator_id": cycle.operator_id,
            "operator_name": operator_name(db, cycle.operator_id),
            "stage": cycle.stage,
            "started_at": cycle.started_at,
            "last_call": None if last_call is None else {
                "date": last_call.created_at.date(),
                "promised_date": last_call.promised_date,
                "result": last_call.result,
            },
        })
    return result


def list_users(db: Session) -> list[AppUser]:
    """Активные пользователи: до появления входа фронтенду нужен список."""
    return list(db.scalars(
        select(AppUser).where(AppUser.is_active.is_(True)).order_by(AppUser.id)
    ))


