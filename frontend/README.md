# Frontend MatchLedger

Interfaz React con recursos empaquetados y sin llamadas a un CDN. Requisitos: Node.js 18+ y backend en `http://localhost:8000`.

- `npm run check`: verifica sintaxis y construye `dist/`.
- `npm run build`: copia `public/` y `src/` al directorio `dist/`.
- `npm run dev`: inicia un servidor estático local en el puerto 5173.

Se utiliza React UMD v16.0.0 incluido con su aviso de licencia MIT en `public/vendor/LICENSE.txt`. Este diseño autocontenido facilita la ejecución local y la demostración del flujo. Para un despliegue productivo se recomienda actualizar la versión de React y migrar a un bundler moderno.
