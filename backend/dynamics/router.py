"""H-02: historical model B dynamics for a client."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from db import SessionLocal
from models import Client, DocumentSnapshot
from .service import present
router = APIRouter(tags=["dynamics"])

def get_db():
    with SessionLocal() as db:
        yield db

@router.get("/clients/{client_id}/dynamics")
def client_dynamics(client_id: int, db: Session = Depends(get_db)) -> dict:
    client = db.get(Client, client_id)
    if client is None: raise HTTPException(status_code=404, detail="Клиент не найден")
    rows = db.scalars(select(DocumentSnapshot).where(DocumentSnapshot.client_id == client_id).order_by(DocumentSnapshot.snapshot_date, DocumentSnapshot.id)).all()
    return {"client_id": client.id, "kcr_code":client.kcr_code,"first_appearance_date":client.first_appearance_date.isoformat() if client.first_appearance_date else None,"history": [present(s) for s in rows]}
