# Referencia resumida de la API

Base: `http://localhost:8000` · Documentación OpenAPI interactiva: `/docs`.

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/health` | Estado del servicio |
| `GET` | `/api/dashboard` | Sesión activa, resumen, movimientos, historial y actividad |
| `GET` | `/api/sessions` | Lista de sesiones |
| `GET` | `/api/sessions/{sid}` | Detalle de una sesión |
| `POST` | `/api/reconcile` | Importa y compara dos CSV (`multipart/form-data`) |
| `POST` | `/api/sessions/{sid}/resolve` | Confirma/descarta un candidato de revisión |
| `GET` | `/api/sessions/{sid}/export` | CSV de diferencias y coincidencias |
| `GET` | `/api/activity` | Registro de auditoría |
| `GET` | `/api/demo/a` | CSV sintético del banco |
| `GET` | `/api/demo/b` | CSV sintético del ERP |

## Importación

`POST /api/reconcile` recibe campos de formulario `source_a` (archivo `.csv`), `source_b` (archivo `.csv`) y `title` (texto). Devuelve la sesión, indicadores y resultados. Error `422` para formato o columnas inválidas; `400` para extensión incorrecta.

## Resolución manual

`POST /api/sessions/{sid}/resolve`:

```json
{
  "entry_id": "ML-A-0014",
  "candidate_id": "B-0014",
  "action": "accept",
  "note": "Validado con comprobante"
}
```

`action` puede ser `accept` o `dismiss`. Para descartar, `candidate_id` puede ser `null`. Una operación solo se puede resolver mientras está en estado `review`. Los movimientos no emparejados tras revisión conservan clasificación `only_a`/`only_b`.

## Comprobaciones

Usar la terminal desde `backend`:

```bash
pytest -q
```

Los tests cubren importes locales, encabezados faltantes, un cruce representativo, salud/dashboard, carga de archivos, revisión y exportación.
