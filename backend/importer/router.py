"""Excel import of test clients and snapshots with H-02 recalculation."""
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.orm import Session
from db import SessionLocal
from models import Client, DocumentSnapshot, ImportBatch
from .validation import parse_workbook, ImportValidationError
from dynamics.service import recalculate_client
router = APIRouter(tags=["importer"])

def get_db():
    with SessionLocal() as db: yield db

def as_date(value):
    if value is None or str(value).strip() == "": return None
    if isinstance(value, datetime): return value.date()
    if isinstance(value,date): return value
    return date.fromisoformat(str(value).strip()[:10])

@router.post("/imports/clients")
async def import_clients(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    try: records = parse_workbook(await file.read(),"clients")
    except ImportValidationError as e: raise HTTPException(422,detail=str(e)) from e
    existing = {x.kcr_code for x in db.scalars(select(Client)).all()}
    duplicates = sorted({x['Код КЦР'] for x in records}&existing)
    if duplicates: raise HTTPException(409,detail="Клиенты уже существуют: "+", ".join(duplicates))
    batch = ImportBatch(file_name=file.filename or "clients.xlsx",import_type="CLIENTS",status="OK",created_count=len(records),error_count=0)
    db.add(batch)
    for r in records:
        db.add(Client(kcr_code=r['Код КЦР'],inn=str(r['ИНН']),kpp=str(r.get('КПП') or '') or None,organization_name=str(r['Название организации']),client_type=str(r.get('Тип клиента') or '') or None,connection_date=as_date(r.get('Дата подключения')),is_do_not_work=str(r.get('Не включать в работу') or '').lower() in ('да','true','1')))
    db.commit()
    return {"created":len(records),"status":"OK"}

@router.post("/imports/snapshots")
async def import_snapshots(file: UploadFile = File(...), reporting_period: str = Form(...), snapshot_date: date = Form(...), db: Session = Depends(get_db)) -> dict:
    clients = {c.kcr_code:c for c in db.scalars(select(Client)).all()}
    existing_period_codes = set(db.scalars(select(Client.kcr_code).join(DocumentSnapshot, Client.id == DocumentSnapshot.client_id).where(DocumentSnapshot.reporting_period == reporting_period)).all())
    try: records = parse_workbook(await file.read(),"snapshots",set(clients),existing_period_codes)
    except ImportValidationError as e: raise HTTPException(422,detail=str(e)) from e
    if not (reporting_period.startswith(('I кв.','II кв.','III кв.','IV кв.')) or '-Q' in reporting_period):
        raise HTTPException(422,detail="Неизвестный формат отчётного периода")
    existing = set(db.execute(select(DocumentSnapshot.client_id,DocumentSnapshot.reporting_period,DocumentSnapshot.snapshot_date)).all())
    dup = [r['Код КЦР'] for r in records if (clients[r['Код КЦР']].id,reporting_period,snapshot_date) in existing]
    if dup: raise HTTPException(409,detail="Срез на эту дату уже сохранён для клиентов: "+", ".join(dup))
    batch = ImportBatch(file_name=file.filename or 'snapshot.xlsx',import_type='SNAPSHOTS',status='OK',created_count=len(records),error_count=0)
    db.add(batch);db.flush()
    touched=set()
    for r in records:
        c=clients[r['Код КЦР']]
        db.add(DocumentSnapshot(client_id=c.id,import_batch_id=batch.id,reporting_period=reporting_period,snapshot_date=snapshot_date,total_documents=int(r['Документов всего']) if r.get('Документов всего') is not None else None,missing_documents=int(r['Не передано документов']),is_novice=False,is_chronic=False))
        touched.add(c.id)
    db.flush()
    for cid in touched: recalculate_client(db,cid)
    db.commit()
    return {"created":len(records),"recalculated_clients":len(touched),"status":"OK"}
