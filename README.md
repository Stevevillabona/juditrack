# JudiTrack — Monitoreo automático de procesos judiciales (Colombia)

Backend-first, tal como exige el requisito no negociable: **toda consulta a
fuentes oficiales corre en el servidor** (Playwright headless o HTTP directo),
nunca en el navegador del usuario.

## Estado: extremo a extremo conectado y verificado

A diferencia de la primera entrega (solo esqueleto/arquitectura), esta
versión tiene el flujo completo cableado: crear un proceso desde el
frontend → se persiste en Postgres → se encola una consulta en Celery →
el conector navega el portal real con Playwright → el diff engine detecta
qué cambió → se guarda el historial insert-only → se notifica por email →
el usuario lo ve en el dashboard y en el log de auditoría.

### Qué se verificó realmente en este entorno (sin acceso a red)

No hay red disponible en este entorno, así que no pude correr
`pip install` / `npm install` reales ni tocar el portal en vivo. Lo que sí
hice, con herramientas ya presentes en el sistema:

- **`python3 -m py_compile`** sobre los ~20 archivos `.py` del backend: sin
  errores de sintaxis.
- **`python3 -m unittest`** sobre `tests/test_diff_engine.py`: **11/11
  pruebas pasan**, incluyendo importar de verdad `app/connectors/rama_judicial.py`
  (con Playwright real instalado en este entorno) y ejercitar la validación
  de radicado y el motor de diff con casos reales (actuación nueva,
  actuación ya conocida, cambio de despacho, nueva audiencia, estabilidad
  del fingerprint).
- **`esbuild`** (encontrado empaquetado con una herramienta ya instalada)
  sobre los 6 archivos `.jsx`/`.js` del frontend: compilan y resuelven sus
  imports cruzados sin errores.
- Revisión manual cruzada de cada `from app.X import Y` contra la
  definición real de `Y`, para atrapar lo que las pruebas de sintaxis no
  detectan.
- En el proceso encontré y corregí dos bugs reales:
  1. `Proceso.actuaciones` se accedía como lazy-load normal, lo cual
     **rompe** en SQLAlchemy async (`MissingGreenlet`). Corregido con
     `lazy="selectin"`.
  2. `celery_app.autodiscover_tasks(["app.tasks"])` no registraba las
     tareas porque por convención busca `app/tasks/tasks.py`, y las
     nuestras viven en `app/tasks/scheduler.py`. Corregido con un import
     explícito.

Lo único que **no pude verificar** por falta de red: que los selectores CSS
de `rama_judicial.py` coincidan exactamente con el HTML actual del portal
(son representativos de la estructura típica de ese tipo de sitio, pero
deben confirmarse en vivo antes de producción), y una instalación real de
dependencias de Python/Node.

## Qué está implementado

**Backend**
- Auth completa: registro de firma (tenant), login, JWT, verificación en
  dos pasos (TOTP compatible con Google Authenticator/Authy).
- Modelo de datos con historial insert-only (`Actuacion`), log de
  auditoría por corrida (`ConsultaRun`), marca de lectura por usuario
  (`ProcesoVisto`) y trazabilidad de accesos (`AccessLog`).
- Arquitectura de conectores desacoplada + rate limiter global por fuente.
- Conector #1 completo: Rama Judicial / CPNU vía Playwright headless.
- Motor de diff por fingerprint de actuación individual.
- Notificador multi-canal (email funcional vía SMTP; web push y SMS/WhatsApp
  con la interfaz lista, integración de proveedor pendiente).
- Cola de trabajos Celery + Redis: ventana horaria configurable, intervalo
  por plan, reintentos con backoff exponencial, resumen diario.
- API REST: procesos (CRUD, importar CSV, archivar/pausar, forzar consulta,
  auditoría), auth (registro, login, 2FA).

**Frontend**
- React + Vite, PWA instalable (manifest + service worker vía
  `vite-plugin-pwa`, `/api/*` siempre en `NetworkOnly` para no servir
  datos viejos offline como si fueran actuales).
- Diseño propio: paleta tinta/pergamino/lacre, tipografía serif (títulos) +
  mono (radicados, fechas) + sans (UI), línea de tiempo estilo expediente
  judicial como elemento distintivo.
- Pantallas: acceso (login + registro + 2FA), dashboard (filtros, alta de
  proceso individual y por CSV), detalle de proceso (línea de tiempo +
  pestaña de auditoría).

## Qué falta para producción

1. **Verificar los selectores reales** de `rama_judicial.py` contra el DOM
   en vivo (recomendado: Playwright Inspector + un smoke test diario contra
   un radicado de control).
2. **Conectores 2–6** (SAMAI, SPOA, Superfinanciera, SIC, despachos): mismo
   patrón que `rama_judicial.py`, se registran en `connectors/registry.py`.
3. **Migraciones con Alembic** en vez de `create_all` (que es solo para
   dev/demo rápida).
4. **Integrar `pywebpush`** (claves VAPID ya en `config.py`) y un proveedor
   de SMS/WhatsApp para planes premium.
5. **Permisos granulares por rol** más allá de admin/abogado/asistente
   (p. ej. "cada abogado solo ve lo suyo" a nivel de query, no solo de UI).
6. **Política de tratamiento de datos y endpoint de derecho de supresión**
   (Ley 1581 de 2012).

## Cómo correrlo

```bash
cp .env.example .env          # ajustar credenciales SMTP y JWT_SECRET
docker compose up --build
```

Esto levanta Postgres, Redis, la API (con las tablas creándose solas al
arrancar), el worker y el beat de Celery, y el frontend en modo desarrollo
en `http://localhost:5173`.

### Correr las pruebas del backend

```bash
cd backend
pip install -r requirements.txt --break-system-packages
python -m unittest tests.test_diff_engine -v
```

### Decisión de diseño clave a defender ante el equipo/cliente

El rate limiter (`connectors/registry.py`) es **global por fuente**, no por
usuario ni por proceso: si mañana hay 5,000 procesos monitoreados, seguimos
respetando un único techo de peticiones concurrentes hacia cada portal
oficial. Esto protege el acceso de todos los usuarios de la plataforma y
reduce el riesgo de bloqueo por parte de la Rama Judicial u otras fuentes.
