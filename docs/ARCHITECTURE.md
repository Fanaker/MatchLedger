# Arquitectura de MatchLedger

## Diseño general

MatchLedger se ejecuta en dos procesos locales: una interfaz React que sirve archivos estáticos y una API FastAPI que acepta CSVs, aplica reglas de conciliación y persiste sesiones en SQLite. La interfaz nunca ejecuta SQL y la API nunca recibe contraseñas bancarias. El backend funciona sin internet.

```text
frontend/src/app.js  --HTTP/JSON--> backend/app/main.py
                                     ├── reconciliation.py (reglas y parseo)
                                     ├── demo.py (generador sintético)
                                     └── .data/matchledger.sqlite3
```

## Flujo de datos

1. El usuario proporciona dos archivos CSV con `fecha`, `referencia`, `descripcion` y `monto` (también se reconocen alias de encabezados).
2. `parse_csv` valida el tamaño, normaliza la codificación, fecha y monto, y reporta los errores con número de fila.
3. `reconcile` identifica duplicados por clave `(referencia normalizada, monto)`, y ejecuta comparación determinista uno a uno.
4. Se prioriza una coincidencia única por referencia+importe. Si existe una referencia sin igual importe, se marca para revisión.
5. Si falta coincidencia por referencia, se permite coincidencia por igual monto, fecha con tolerancia de 2 días y similitud de descripción de al menos 0.64. Si hay varios candidatos, el movimiento se marca para revisión.
6. Los registros no pareados se clasifican como presentes solo en A/B. Las parejas que requieren revisión conservan sus candidatos.
7. El payload de la sesión y sus datos resumidos se almacenan en SQLite, y cada revisión manual crea un evento de auditoría.
8. React consulta los resultados y permite filtrar, inspeccionar, resolver y descargar CSV.

## Estados

| Estado interno | Significado |
|---|---|
| `matched` | Existe una única contraparte aceptada automáticamente o aprobada manualmente |
| `review` | Hay una o más contrapartes posibles, pero necesitan validación |
| `only_a` | Movimiento sin contraparte disponible en A respecto de B |
| `only_b` | Movimiento sin contraparte disponible en B respecto de A |
| `duplicate` | La misma referencia e importe se repite dentro de un origen |

## Almacenamiento

SQLite emplea dos tablas: `sessions` (id, título, timestamp, nombres de origen, payload JSON), `audit_events` (id, sesión, fecha, evento, detalle). El archivo se crea al iniciar el backend y queda excluido del repositorio. La carpeta `sample-data/` sí contiene los dos CSV sintéticos para reproducir la demo.

## Limitaciones conscientes

- Sin autenticación, multiusuario ni controles para información financiera sensible en producción. Ejecutar localmente con datos de muestra o anonimizados.
- No existe comparación probabilística ni machine learning. El campo `score` representa una clasificación heurística de confianza, no una probabilidad calibrada.
- El algoritmo usa sumas sobre valores normalizados a dos decimales, basadas en tipos flotantes para el JSON final; para producción de alta exigencia se recomienda almacenar importes como `Decimal` o enteros de céntimos en la base de datos.
- Archivos de hasta 3000 registros: el algoritmo prioriza legibilidad y reglas explicables frente a optimización masiva. Una versión empresarial requeriría índices por referencia y monto.
- Revisión manual sin autenticación: se asume un único usuario en un entorno local.
- Frontend autocontenido con distribución React UMD; se puede migrar en el futuro a React moderno con empaquetado Vite y TypeScript.

## Capturas

Las imágenes de `docs/screenshots/` se obtuvieron al renderizar el frontend real en Chromium con los datos JSON de una sesión demo obtenidos de la API. No son pantallas pintadas independientemente del código.
