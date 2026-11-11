"""Deterministic synthetic merchant transactions for a realistic, privacy-safe demo."""
from __future__ import annotations
import csv
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from random import Random

PRODUCTS = [
    ('Pago POS • Terminal 04', 148.50), ('Transferencia interbancaria', 980.00),
    ('Venta mostrador • Sucursal Centro', 76.90), ('Cobro factura comercial', 1250.00),
    ('Venta POS • Tarjeta débito', 234.00), ('Abono pedido ecommerce', 189.90),
    ('Pago de proveedor', -435.20), ('Reembolso a cliente', -68.00),
    ('Suscripción de servicio', -119.90), ('Cobro transferencia Yape', 48.00),
    ('Pago de planilla', -720.00), ('Venta corporativa', 2460.00),
]


def generate(folder: Path) -> tuple[Path, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    rng = Random(202610)
    a = []
    for i in range(1, 141):
        desc, base = PRODUCTS[(i * 7 + i // 6) % len(PRODUCTS)]
        amount = Decimal(str(base)) + Decimal(rng.choice(['0', '0', '0', '2.50', '-1.00']))
        day = date(2026, 10, 1) + timedelta(days=(i * 13) % 31)
        a.append({'fecha': day.isoformat(), 'referencia': f'OP-{602500+i}', 'descripcion': desc, 'monto': f'{amount:.2f}'})
    b = []
    for i, row in enumerate(a):
        if i in [6, 24, 52, 83, 117, 132]:
            continue
        candidate = row.copy()
        if i in [13, 34, 68, 91, 108, 124, 135]:
            candidate['monto'] = f'{Decimal(row["monto"]) + Decimal("1.50"):.2f}'
        if i in [12, 44, 77, 105]:
            candidate['referencia'] = ''
        b.append(candidate)
    for i in [23, 53, 80]:
        b.append(a[i].copy())  # duplicate evidence
    for i in range(5):
        b.append({'fecha': f'2026-10-{14+i:02d}', 'referencia': f'EXT-{8800+i}',
                  'descripcion': ['Ajuste bancario', 'Comisión de mantenimiento', 'Depósito no registrado', 'Cargo extraordinario', 'Transferencia pendiente'][i],
                  'monto': f'{[19.90, -25.00, 450.00, -30.00, 89.00][i]:.2f}'})
    rng.shuffle(b)
    paths = []
    for filename, rows in [('banco_octubre_2026.csv', a), ('erp_octubre_2026.csv', b)]:
        path = folder / filename
        with path.open('w', newline='', encoding='utf-8-sig') as out:
            writer = csv.DictWriter(out, fieldnames=['fecha','referencia','descripcion','monto'])
            writer.writeheader(); writer.writerows(rows)
        paths.append(path)
    return tuple(paths)
