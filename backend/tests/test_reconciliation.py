import csv
import io
import os
import tempfile
from pathlib import Path
from decimal import Decimal

# Isolate CI test storage from local demo and working database.
os.environ['MATCHLEDGER_DATA'] = tempfile.mkdtemp(prefix='matchledger-tests-')

from fastapi.testclient import TestClient
from app.main import app
from app.reconciliation import parse_csv, reconcile, summarize, parse_amount


def csv_bytes(rows):
    s=io.StringIO()
    w=csv.DictWriter(s,fieldnames=['fecha','referencia','descripcion','monto'])
    w.writeheader();w.writerows(rows)
    return s.getvalue().encode('utf-8')


def test_amount_locales():
    assert parse_amount('S/ 1,234.50') == parse_amount('1234,50') == 1234.50
    assert parse_amount('-S/ 58,90') == Decimal('-58.90')


def test_reconcile_unique_and_exception():
    a=csv_bytes([
        dict(fecha='2026-10-08',referencia='OP-100',descripcion='Venta',monto='12.50'),
        dict(fecha='2026-10-09',referencia='OP-101',descripcion='Transferencia',monto='60.00'),
        dict(fecha='2026-10-10',referencia='OP-102',descripcion='Abono',monto='90.00'),
    ])
    b=csv_bytes([
        dict(fecha='08/10/2026',referencia='OP100',descripcion='Venta',monto='12,50'),
        dict(fecha='09/10/2026',referencia='OP-101',descripcion='Transferencia',monto='61.00'),
    ])
    r=reconcile(parse_csv(a,'A'),parse_csv(b,'B'))
    stats=summarize(r)
    assert stats['matched']==1
    assert stats['review']==1
    assert stats['only_a']==1
    assert stats['total_right']==2


def test_missing_column_error():
    try:
        parse_csv(b'fecha,descripcion,monto\n2026-10-01,pago,15', 'A')
    except ValueError as err:
        assert 'reference' in str(err)
    else:
        raise AssertionError('Expected missing column error')


def test_health_and_seeded_dashboard():
    client=TestClient(app)
    assert client.get('/api/health').json()['status']=='ok'
    data=client.get('/api/dashboard').json()
    assert data['summary']['matched'] > 100
    assert data['summary']['review'] > 0
    assert data['session']['id'].startswith('SES-')


def test_file_upload_resolution_and_export():
    client=TestClient(app)
    a=csv_bytes([dict(fecha='2026-10-10',referencia='A-100',descripcion='Pago ABC',monto='100')])
    b=csv_bytes([dict(fecha='2026-10-10',referencia='A-100',descripcion='Pago ABC',monto='101')])
    created=client.post('/api/reconcile',data={'title':'Caso de prueba'},files={'source_a':('bank.csv',a,'text/csv'),'source_b':('erp.csv',b,'text/csv')})
    assert created.status_code==200,created.text
    result=created.json(); assert result['summary']['review']==1
    record=result['entries'][0]
    candidate=record['candidates'][0]['id']
    done=client.post('/api/sessions/'+result['id']+'/resolve',json={'entry_id':record['id'],'candidate_id':candidate,'action':'accept','note':'Validado con comprobante'})
    assert done.status_code==200,done.text
    assert done.json()['summary']['matched']==1
    csv_result=client.get('/api/sessions/'+result['id']+'/export')
    assert csv_result.status_code==200
    assert 'Validado con comprobante' in csv_result.text
