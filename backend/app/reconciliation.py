"""CSV normalization and deterministic, one-to-one financial reconciliation."""
from __future__ import annotations
import csv
import io
import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from collections import Counter

MAX_BYTES = 5 * 1024 * 1024
ALIASES = {
    'date': ('fecha', 'fecha_operacion', 'fecha_movimiento', 'date', 'transaction_date'),
    'reference': ('referencia', 'numero_operacion', 'numero', 'operacion', 'ref', 'reference', 'transaction_id', 'id'),
    'description': ('descripcion', 'detalle', 'concepto', 'description', 'memo', 'glosa'),
    'amount': ('monto', 'importe', 'total', 'amount', 'valor', 'importe_pen'),
}


def clean(value: str) -> str:
    value = unicodedata.normalize('NFKD', str(value))
    return re.sub(r'[^a-z0-9]+', '_', ''.join(c for c in value if not unicodedata.combining(c)).lower()).strip('_')


def parse_amount(value: str) -> Decimal:
    s = re.sub(r'[^0-9,.-]', '', str(value).strip())
    if not s or s in ('-', '.', ','):
        raise ValueError('monto vacío')
    if ',' in s and '.' in s:
        s = s.replace(',', '') if s.rfind('.') > s.rfind(',') else s.replace('.', '').replace(',', '.')
    elif ',' in s:
        bits = s.split(',')
        s = s.replace(',', '') if len(bits[-1]) == 3 else s.replace(',', '.')
    try:
        return Decimal(s).quantize(Decimal('0.01'))
    except InvalidOperation:
        raise ValueError('monto inválido') from None


def parse_date(value: str) -> str:
    raw = str(value).strip().split(' ')[0]
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(raw, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    raise ValueError('fecha inválida (AAAA-MM-DD o DD/MM/AAAA)')


def parse_csv(content: bytes, source: str) -> list[dict]:
    if len(content) > MAX_BYTES:
        raise ValueError('Archivo demasiado grande (máximo 5 MB).')
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = content.decode('latin-1')
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t')
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    except csv.Error:
        # Sniffer can fail on perfectly valid, short CSVs with locale decimals.
        header = text.splitlines()[0] if text.splitlines() else ''
        sep = max([',', ';', '\t'], key=lambda x: header.count(x))
        reader = csv.DictReader(io.StringIO(text), delimiter=sep)
    if not reader.fieldnames:
        raise ValueError('El archivo no tiene encabezados.')
    fields = {clean(name): name for name in reader.fieldnames}
    column_map = {}
    for target, aliases in ALIASES.items():
        found = next((fields[x] for x in aliases if x in fields), None)
        if not found:
            raise ValueError(f'Falta la columna requerida: {target}. Encabezados permitidos: {", ".join(aliases)}.')
        column_map[target] = found
    output = []
    for idx, raw in enumerate(reader, 2):
        if not any(str(v or '').strip() for v in raw.values()):
            continue
        try:
            amount = parse_amount(raw[column_map['amount']])
            item = {
                'id': f'{source}-{idx-1:04d}',
                'source': source,
                'date': parse_date(raw[column_map['date']]),
                'reference': str(raw[column_map['reference']] or '').strip(),
                'description': str(raw[column_map['description']] or '').strip()[:180],
                'amount': float(amount),
            }
            if not item['description']:
                item['description'] = 'Sin descripción'
            output.append(item)
        except (ValueError, TypeError) as exc:
            raise ValueError(f'Fila {idx}: {exc}') from None
    if not output:
        raise ValueError('El archivo no contiene movimientos.')
    if len(output) > 3000:
        raise ValueError('Se permiten hasta 3000 registros por archivo.')
    return output


def ref_key(ref: str) -> str:
    return re.sub(r'[^A-Z0-9]', '', str(ref).upper())


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, clean(a), clean(b)).ratio()


def day_distance(a: str, b: str) -> int:
    return abs((datetime.fromisoformat(a) - datetime.fromisoformat(b)).days)


def reconcile(left: list[dict], right: list[dict]) -> dict:
    """Priority: unique reference+amount, unique ref mismatch as review, fuzzy amount/date, then unmatched.

    Duplicate keys on either side are explicitly excluded from automatic matching.
    """
    left_keys = Counter((ref_key(x['reference']), x['amount']) for x in left if ref_key(x['reference']))
    right_keys = Counter((ref_key(x['reference']), x['amount']) for x in right if ref_key(x['reference']))
    ldup = {x['id'] for x in left if ref_key(x['reference']) and left_keys[(ref_key(x['reference']), x['amount'])] > 1}
    rdup = {x['id'] for x in right if ref_key(x['reference']) and right_keys[(ref_key(x['reference']), x['amount'])] > 1}
    used_r = set()
    reserved_r = set()
    entries = []
    for a in left:
        if a['id'] in ldup:
            entries.append({'id': 'ML-' + a['id'], 'status': 'duplicate', 'left': a, 'right': None, 'candidates': [], 'reason': 'Referencia y monto duplicados en origen A', 'score': None})
            continue
        pool = [b for b in right if b['id'] not in used_r and b['id'] not in rdup and b['id'] not in reserved_r]
        refs = [b for b in pool if ref_key(a['reference']) and ref_key(b['reference']) == ref_key(a['reference'])]
        exact = [b for b in refs if b['amount'] == a['amount']]
        if len(exact) == 1:
            b = exact[0]
            used_r.add(b['id'])
            entries.append({'id': 'ML-' + a['id'], 'status': 'matched', 'left': a, 'right': b, 'candidates': [], 'reason': 'Referencia y monto coinciden', 'score': 100})
            continue
        if refs:
            reserved_r.update(b['id'] for b in refs)
            entries.append({'id': 'ML-' + a['id'], 'status': 'review', 'left': a, 'right': None, 'candidates': refs[:6], 'reason': 'Referencia coincidente con diferencia de monto o posibles duplicados', 'score': 82})
            continue
        fuzzy = [b for b in pool if b['amount'] == a['amount'] and day_distance(a['date'], b['date']) <= 2 and similarity(a['description'], b['description']) >= 0.64]
        if len(fuzzy) == 1:
            b = fuzzy[0]
            used_r.add(b['id'])
            entries.append({'id': 'ML-' + a['id'], 'status': 'matched', 'left': a, 'right': b, 'candidates': [], 'reason': 'Coincidencia por monto, fecha y descripción', 'score': 91})
        elif len(fuzzy) > 1:
            reserved_r.update(b['id'] for b in fuzzy)
            entries.append({'id': 'ML-' + a['id'], 'status': 'review', 'left': a, 'right': None, 'candidates': fuzzy[:6], 'reason': 'Varias coincidencias posibles', 'score': 75})
        else:
            entries.append({'id': 'ML-' + a['id'], 'status': 'only_a', 'left': a, 'right': None, 'candidates': [], 'reason': 'Sin contraparte en origen B', 'score': None})
    candidate_ids = {c['id'] for e in entries if e['status'] == 'review' for c in e['candidates']}
    for b in right:
        if b['id'] in used_r or b['id'] in candidate_ids:
            continue
        status = 'duplicate' if b['id'] in rdup else 'only_b'
        entries.append({'id': 'ML-' + b['id'], 'status': status, 'left': None, 'right': b, 'candidates': [], 'reason': 'Registro duplicado en origen B' if status == 'duplicate' else 'Sin contraparte en origen A', 'score': None})
    return {'entries': entries, 'left_count': len(left), 'right_count': len(right)}


def summarize(data: dict) -> dict:
    counts = Counter(e['status'] for e in data['entries'])
    matched_amount = sum(abs(e['left']['amount']) for e in data['entries'] if e['status'] == 'matched' and e['left'])
    total_amount = sum(abs(e['left']['amount']) for e in data['entries'] if e['left'])
    return {
        'matched': counts['matched'], 'review': counts['review'],
        'only_a': counts['only_a'], 'only_b': counts['only_b'], 'duplicate': counts['duplicate'],
        'total_left': data['left_count'], 'total_right': data['right_count'],
        'matched_amount': round(matched_amount, 2), 'total_amount': round(total_amount, 2),
        'rate': round(100 * counts['matched'] / max(1, data['left_count']), 1),
        'issues': counts['review'] + counts['only_a'] + counts['only_b'] + counts['duplicate'],
    }
