"""Persist model B per snapshot; existing snapshot rows are never deleted/replaced."""
from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session
from models import Client as DbClient, DocumentSnapshot, WorkCycle
from .features import Client, FeatureCalculator, RawSlice, NO_PREVIOUS, ALL_PASSED, FIRST_TIME, DECREASING, NOT_DECREASING, RECURRED

TO_CODE = {NO_PREVIOUS:"NO_COMPARISON", ALL_PASSED:"ALL_TRANSFERRED", FIRST_TIME:"FIRST_APPEARED", DECREASING:"DECREASING", NOT_DECREASING:"FLAT_OR_GROWING", RECURRED:"REAPPEARED"}
TO_NAME = {v:k for k,v in TO_CODE.items()}

def period_for_model(p: str) -> str:
    if "-Q" in p:
        year, q = p.split("-Q")
        return f"{('I','II','III','IV')[int(q)-1]} кв. {year}"
    return p

def recalculate_client(db: Session, client_id: int) -> int:
    client = db.get(DbClient, client_id)
    if client is None:
        raise ValueError(f"Клиент {client_id} не найден")
    snapshots = list(db.scalars(select(DocumentSnapshot).where(DocumentSnapshot.client_id == client_id).order_by(DocumentSnapshot.snapshot_date, DocumentSnapshot.id)))
    cycle = db.scalar(select(WorkCycle).where(WorkCycle.client_id == client_id, WorkCycle.closed_at.is_(None)).order_by(WorkCycle.id.desc()))
    stage = cycle.stage if cycle else None
    model_client = Client(code=client.kcr_code, connect_date=client.connection_date, do_not_call=bool(client.is_do_not_work), stage=stage)
    calculator = FeatureCalculator({client.kcr_code: model_client})
    raw = []
    for s in snapshots:
        raw.append(RawSlice(slice_id=str(s.id), period=period_for_model(s.reporting_period), slice_date=s.snapshot_date, code=client.kcr_code, total=s.total_documents, not_transferred=s.missing_documents, stage=stage))
    result = calculator.process(raw)
    for s, r in zip(snapshots, result):
        s.dynamics_code = TO_CODE[r.change]
        s.is_novice = r.is_novice  # independent client attribute; UI badge when missing > 0
        s.is_chronic = r.is_chronic
        s.missing_percent = round(100 * r.not_transferred / r.total_ref, 6) if r.total_ref else None
    client.first_appearance_date = snapshots[0].snapshot_date if snapshots else None
    db.flush()
    return len(result)

def present(s: DocumentSnapshot) -> dict:
    name = TO_NAME.get(s.dynamics_code, NO_PREVIOUS)
    if s.dynamics_code == "NO_COMPARISON": category = "Нет сравнения"
    elif s.missing_percent is None: category = "Нет данных"
    elif s.is_chronic: category = "Хронический"
    elif s.is_novice and s.missing_documents > 0: category = "Новичок"
    else: category = name
    return {"snapshot_id":s.id,"reporting_period":s.reporting_period,"snapshot_date":s.snapshot_date.isoformat(),"total_documents":s.total_documents,"missing_documents":s.missing_documents,"missing_percent":s.missing_percent,"dynamics_code":s.dynamics_code,"dynamics_name":name,"is_novice":s.is_novice,"show_novice_badge":bool(s.is_novice and s.missing_documents>0),"is_chronic":s.is_chronic,"category":category}
