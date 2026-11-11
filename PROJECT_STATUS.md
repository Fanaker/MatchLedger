# MatchLedger 1.0.0 — estado de entrega

## Entregado
- API FastAPI y motor de conciliación CSV.
- Almacenamiento local SQLite con historial y auditoría.
- Interfaz React: resumen, conciliaciones, carga, revisión, informes, historial y configuración informativa.
- Dos archivos CSV sintéticos reproducibles.
- Exportación de conciliaciones y resolución de candidatos.
- Capturas de seis vistas del frontend obtenidas a partir del código ejecutado; README y documentación técnica.
- Workflow de CI para verificación automática.

## Comprobado en la sesión de entrega
- `pytest -q`: 5 pruebas superadas.
- `npm run check`: validación sintáctica JS y generación de `frontend/dist` superadas.
- Chromium: las seis vistas se renderizaron sin errores de ejecución de JavaScript con datos de la API.

## Fuera del alcance
- Despliegue público, autenticación, multiusuario, conexión bancaria directa, Excel nativo, procesamiento masivo y certificaciones contables.
- No se ha verificado instalación en un equipo Windows ajeno al entorno de desarrollo.

## Para continuar
1. Ejecutar localmente backend y frontend (README).
2. Realizar una carga de CSV y revisar resultados en el navegador.
3. Subir el contenido de la carpeta a un repositorio GitHub sin incluir `.data`, `.venv` ni archivos privados.
