"""DS-02, manually labeled H-02, negative imports and persisted API history."""
from datetime import date
from io import BytesIO
from pathlib import Path
import importlib.util
import sys

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/h02'))
from features import Client as ReferenceClient, FeatureCalculator as ReferenceCalculator, RawSlice as ReferenceSlice
from dynamics.features import FeatureCalculator, Client, RawSlice
from importer.validation import parse_workbook, ImportValidationError
from models import Client as DbClient, DocumentSnapshot, ImportBatch
from db import Base
from main import app
from dynamics.router import get_db as dynamic_db
from importer.router import get_db as importer_db

BASE = ROOT/'data/test/h02'

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name,path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def test_86_ds02_oracle_matches_backend_model():
    script=load_module('ds02_reference',ROOT/'scripts/h02/run_h02_check.py')
    wb=openpyxl.load_workbook(script.BOOK,data_only=True)
    clients=script.load_clients(wb)
    raw=script.load_raw_slices(wb)
    oracle=script.load_oracle(wb)
    results=FeatureCalculator({k:Client(code=v.code,connect_date=v.connect_date,do_not_call=v.do_not_call,stage=v.stage) for k,v in clients.items()}).process(raw)
    r=script.check_4_oracle(results,clients,oracle)
    assert r['checked']==86
    assert r['mismatches']==[]

def test_51_client_markup_matches_with_display_convention():
    mod=load_module('markup_reference',ROOT/'scripts/h02/run_h02_markup.py')
    clients,raw,errors=mod.load_markup(mod.MARKUP)
    # reference comparison uses model B, which is now ported unchanged
    r=mod.compare(clients,raw,errors)
    assert r['n_clients']==51
    assert r['n_rows']==187
    assert r['ok_rows_mc']==187
    assert r['ok_clients_mc']==51
    assert len(r['novice_conv'])==6

@pytest.mark.parametrize('filename',sorted((BASE/'02_Ошибочные_импорты').glob('*.xlsx')),ids=lambda x:x.name)
def test_bad_workbooks_rejected(filename):
    typ='clients' if 'Клиенты' in filename.name else 'snapshots'
    with pytest.raises(ImportValidationError,match=r'(Строка|Повтор|Отсутствуют)'):
        parse_workbook(filename.read_bytes(),typ,{'1000001'} if typ=='snapshots' else None)

def test_persisted_history_endpoint_and_duplicate_import():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Local=sessionmaker(engine,expire_on_commit=False)
    def override():
        with Local() as db:yield db
    app.dependency_overrides[dynamic_db]=override
    app.dependency_overrides[importer_db]=override
    try:
        folder=BASE/'01_Корректные_импорты'
        cfile=folder/'00_Клиенты.xlsx'
        with TestClient(app) as client:
            r=client.post('/api/imports/clients',files={'file':(cfile.name,cfile.read_bytes(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
            assert r.status_code==200,r.text
            with Local() as db:
                c=db.scalar(select(DbClient).where(DbClient.kcr_code=='1000001'))
                cid=c.id
            snapshots=sorted(folder.glob('S*.xlsx'))
            for n, path in enumerate(snapshots):
                sid=path.name.split('_')[0]
                # all snapshots have dates encoded in their names
                datepart=path.stem.rsplit('_',1)[-1]
                period=('I кв. 2026' if n<2 else 'II кв. 2026' if n<4 else 'III кв. 2026')
                r=client.post('/api/imports/snapshots',data={'reporting_period':period,'snapshot_date':datepart},files={'file':(path.name,path.read_bytes(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
                assert r.status_code==200,(path.name,r.text)
            r=client.get(f'/api/clients/{cid}/dynamics')
            assert r.status_code==200,r.text
            body=r.json();history=body['history']
            assert len(history)==6
            assert [h['snapshot_date'] for h in history]==sorted(h['snapshot_date'] for h in history)
            assert all('show_novice_badge' in h for h in history)
            before = [(h['snapshot_id'],h['snapshot_date'],h['missing_documents'],h['total_documents']) for h in history]
            with Local() as db:
                stored=db.scalars(select(DocumentSnapshot).where(DocumentSnapshot.client_id==cid)).all()
                assert len(stored)==6
                assert all(s.dynamics_code for s in stored)
            path=snapshots[0]
            r=client.post('/api/imports/snapshots',data={'reporting_period':'I кв. 2026','snapshot_date':path.stem.rsplit('_',1)[-1]},files={'file':(path.name,path.read_bytes(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
            assert r.status_code==409
            after = client.get(f'/api/clients/{cid}/dynamics').json()['history']
            assert len(after)==6
            assert before == [(h['snapshot_id'],h['snapshot_date'],h['missing_documents'],h['total_documents']) for h in after]
            assert client.get('/api/clients/999999/dynamics').status_code==404
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

def test_novice_flag_independent_from_badge():
    from dynamics.service import present
    from types import SimpleNamespace
    s=SimpleNamespace(id=1,reporting_period='2026-Q1',snapshot_date=date(2026,4,20),total_documents=20,missing_documents=0,missing_percent=0.0,dynamics_code='ALL_TRANSFERRED',is_novice=True,is_chronic=False)
    response=present(s)
    assert response['is_novice'] is True
    assert response['show_novice_badge'] is False
    assert response['category']=='Все переданы'
