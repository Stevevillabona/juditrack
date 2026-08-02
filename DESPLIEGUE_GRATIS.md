# Cómo publicar JudiTrack gratis, para siempre — Supabase + GitHub

Esta es la versión sin costo mensual. Cambia cómo funciona por debajo (en
vez de un servidor siempre encendido, el monitoreo corre cada 2 horas vía
GitHub Actions), pero para ti, usarla es exactamente igual: abrir un link
en el navegador.

No necesitas tarjeta de crédito en ningún paso de esta guía.

## Paso 1 — Actualiza tu repositorio de GitHub

Ya tienes el repo `juditrack` creado. Ahora hay que subir los archivos
nuevos que agregamos (la carpeta `supabase/`, `scripts/`, `.github/` y los
cambios en `frontend/`). Es el mismo procedimiento de antes:

1. Descomprime el nuevo `.zip` que te compartí.
2. Ve a tu repositorio en GitHub → **Add file → Upload files**.
3. Arrastra **todo el contenido** de la carpeta `proyecto` otra vez (los
   archivos que ya existían se van a actualizar, y los nuevos se agregan).
4. **Commit changes**.

## Paso 2 — Crea tu proyecto en Supabase

1. Entra a **supabase.com** → **Start your project** → puedes registrarte
   con tu cuenta de GitHub (un clic, sin tarjeta).
2. Clic en **New Project**.
3. Elige un nombre (p. ej. `juditrack`), genera una contraseña para la
   base de datos con el botón **Generate a password** y **guárdala en un
   lugar seguro** (la vas a necesitar solo si algún día quieres conectarte
   directo a la base de datos; para el uso normal de la app no hace falta).
4. Elige la región más cercana (p. ej. **South America (São Paulo)**).
5. Plan: **Free**. Clic en **Create new project** y espera 1-2 minutos
   mientras se aprovisiona.

## Paso 3 — Crea las tablas

1. En el menú de la izquierda de tu proyecto Supabase, clic en **SQL
   Editor**.
2. Clic en **New query**.
3. Abre el archivo `supabase/schema.sql` (del zip) con cualquier editor de
   texto (o el Bloc de notas / TextEdit), selecciona todo el contenido,
   cópialo, y pégalo en el editor de Supabase.
4. Clic en **Run** (o `Cmd+Enter`). Deberías ver "Success. No rows
   returned".

## Paso 4 — Copia tus credenciales de Supabase

1. En el menú de la izquierda, clic en el ícono de engranaje
   **Project Settings** → **API**.
2. Vas a ver tres valores que necesitas copiar, uno por uno:
   - **Project URL** (algo como `https://xxxxx.supabase.co`)
   - **anon public** key (una clave larga, esta es pública y va en el
     frontend)
   - **service_role** key (otra clave larga — **esta es secreta**, dale
     clic a "Reveal" para verla. Nunca la compartas ni la pongas en el
     frontend, solo en el paso siguiente)

## Paso 5 — Configura los "Secrets" en GitHub

1. En tu repositorio de GitHub, ve a **Settings** (pestaña del repo, no la
   de tu cuenta) → en el menú izquierdo, **Secrets and variables** →
   **Actions**.
2. Clic en **New repository secret** y crea, uno por uno (nombre exacto a
   la izquierda, valor pegado a la derecha):

   | Nombre del secret | Valor |
   |---|---|
   | `SUPABASE_URL` | tu Project URL |
   | `SUPABASE_ANON_KEY` | tu clave "anon public" |
   | `SUPABASE_SERVICE_ROLE_KEY` | tu clave "service_role" |
   | `SMTP_HOST` | ver la sección de correo más abajo (opcional) |
   | `SMTP_PORT` | `587` |
   | `SMTP_USER` | tu correo |
   | `SMTP_PASSWORD` | tu contraseña de aplicación |

   Si todavía no tienes credenciales de correo, puedes crear igual
   `SMTP_HOST`, `SMTP_USER` y `SMTP_PASSWORD` vacíos o con cualquier texto
   — el sistema simplemente no va a poder enviar correos hasta que los
   rellenes de verdad (todo lo demás funciona igual).

## Paso 6 — Activa GitHub Pages

1. En el mismo repositorio, **Settings** → en el menú izquierdo,
   **Pages**.
2. En **Source**, elige **GitHub Actions** (no "Deploy from a branch").

## Paso 7 — Dispara el primer despliegue del sitio

1. Ve a la pestaña **Actions** de tu repositorio (arriba, junto a "Code",
   "Pull requests", etc.).
2. En la lista de la izquierda, clic en **"Publicar frontend en GitHub
   Pages"**.
3. Clic en **Run workflow** (botón a la derecha) → **Run workflow** de
   nuevo para confirmar.
4. Espera 1-2 minutos a que el círculo se ponga verde ✅.
5. Ve a **Settings → Pages** otra vez: ahí va a aparecer un link tipo
   `https://tu-usuario.github.io/juditrack/` — **esa es tu app**.

## Paso 8 — Pruébala

Abre esa URL. Regístrate, y añade tu primer radicado. El monitoreo
automático corre cada 2 horas en horario hábil colombiano — puedes ver
(y forzar) las corridas en la pestaña **Actions** → **"Monitoreo de
procesos"** → **Run workflow** en cualquier momento.

## Diferencias con la versión de pago

- **No es instantáneo.** El scraping corre cada 2 horas (configurable
  editando la línea `cron` en `.github/workflows/monitor.yml`), no al
  momento de añadir el proceso. Puedes forzar una corrida manual desde la
  pestaña Actions cuando quieras.
- **El botón "Forzar consulta"** dentro de la app te lleva a esa pantalla
  de GitHub en vez de consultar al instante — es la forma de tener
  "on-demand" sin pagar por un servidor siempre encendido.
- **El proyecto de Supabase se pausa solo si nadie lo usa por 7 días
  seguidos.** En la práctica esto casi nunca pasa, porque el propio
  monitoreo automático escribe en la base de datos cada vez que corre. Si
  alguna vez ves que la app no responde, entra al dashboard de Supabase:
  te va a mostrar un botón para "despertar" el proyecto.

## Cómo conseguir credenciales SMTP (opcional, para que lleguen los correos)

Igual que en la guía anterior: la forma más simple es una cuenta de Gmail
con una "contraseña de aplicación".

1. **myaccount.google.com/security** → activa la verificación en dos
   pasos si no la tienes.
2. Busca **"Contraseñas de aplicaciones"** → nombre cualquiera → **Crear**.
3. Copia la contraseña de 16 caracteres.
4. Úsala como `SMTP_PASSWORD` en los secrets de GitHub (Paso 5), con
   `SMTP_HOST=smtp.gmail.com`, `SMTP_USER=tu-correo@gmail.com`.

## Si algo no funciona

- **La app dice que faltan credenciales de Supabase**: revisa que
  `SUPABASE_URL` y `SUPABASE_ANON_KEY` estén bien copiados en los Secrets
  de GitHub, y vuelve a correr el workflow de "Publicar frontend" (Paso 7)
  para que tome los valores nuevos — los secrets solo se usan al compilar,
  no en tiempo real.
- **No aparecen actuaciones después de varias horas**: ve a la pestaña
  Actions → "Monitoreo de procesos" → abre la corrida más reciente y
  revisa el log línea por línea, ahí dice exactamente qué pasó con cada
  proceso.
- **No llegan los correos**: revisa que las 4 variables `SMTP_*` estén
  bien puestas en los Secrets, y mira el log de la corrida de "Monitoreo
  de procesos" — si el envío falla, va a aparecer el error ahí.
