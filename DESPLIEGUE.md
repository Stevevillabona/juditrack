# Cómo publicar JudiTrack sin instalar nada — solo con el navegador

Hay **un solo paso manual inevitable**: subir el código a GitHub (nadie
puede hacerlo por ti, alguien tiene que "hostear" el código antes de que
cualquier botón pueda desplegarlo). Toma ~2 minutos y es arrastrar una
carpeta. Después de eso, todo el resto es hacerle clic a un botón.

## Paso 1 — Sube el código a GitHub (arrastrar y soltar, sin terminal)

1. Entra a **github.com** y crea una cuenta gratis (si no tienes una).
2. Arriba a la derecha, clic en el **+** → **New repository**.
3. Nómbralo `juditrack`, márcalo **Public** (tiene que ser público para
   que el botón de despliegue automático de más abajo funcione — no vas a
   subir contraseñas ni secretos, esos se configuran aparte en Render),
   y clic en **Create repository**.
4. En la página del repo, busca **"uploading an existing file"** (o
   **Add file → Upload files**).
5. Descomprime el `.zip` que te di y **arrastra la carpeta `proyecto`
   completa** (o todo su contenido) a esa página.
6. Baja hasta el final y clic en **Commit changes**.
7. Copia la URL de tu repositorio, algo como
   `https://github.com/tu-usuario/juditrack`.

## Paso 2 — Un clic para desplegar todo

Pega tu URL de GitHub del paso anterior donde dice `TU-USUARIO` en este
link y ábrelo (o simplemente entra a render.com/deploy y pega ahí la URL
de tu repo cuando te la pida):

```
https://render.com/deploy?repo=https://github.com/TU-USUARIO/juditrack
```

Eso abre Render ya con los 6 servicios detectados desde `render.yaml`
(API, worker, beat, Redis, base de datos y el sitio). Si es tu primera vez
en Render, te pide crear cuenta (puedes usar tu cuenta de GitHub, un clic)
y autorizar el acceso al repo.

Te va a pedir rellenar unos campos antes de continuar — puedes dejar
`SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `CORS_ORIGINS` y
`VITE_API_BASE` en blanco por ahora (se completan después, ver Paso 3).
Clic en **Apply** y espera — la primera vez tarda varios minutos porque
instala un navegador Chromium real para el scraper.

## Paso 3 — Conecta el frontend con el API (dos copiar-y-pegar)

Render no puede saber la URL de un servicio antes de crearlo, así que este
paso manual es inevitable, pero es solo copiar y pegar:

1. En el dashboard, entra al servicio **juditrack-api** y copia su URL
   (algo como `https://juditrack-api-xxxx.onrender.com`).
2. Entra al servicio **juditrack-frontend** → pestaña **Environment** →
   edita la variable `VITE_API_BASE` → pega ahí la URL del API (sin `/` al
   final) → **Save Changes**. Esto dispara un redeploy automático del
   frontend.
3. Ahora copia la URL de **juditrack-frontend** (algo como
   `https://juditrack-frontend-xxxx.onrender.com`).
4. Entra a **juditrack-api** → **Environment** → edita `CORS_ORIGINS` →
   pega ahí la URL del frontend (sin `/` al final) → **Save Changes**.

De aquí en adelante, la URL de `juditrack-frontend` **es tu app** — la
guardas en favoritos o la instalas como app desde el navegador, y ya no
vuelves a tocar Render ni GitHub para nada del uso diario.

## Costo esperado

Render cobra por servicio activo. Con la configuración de `render.yaml`:

- `juditrack-api`, `juditrack-worker`, `juditrack-beat`: plan "Starter",
  ~$7 USD/mes cada uno → **~$21 USD/mes**. `juditrack-worker` y
  `juditrack-beat` son servicios tipo "worker", y Render no ofrece plan
  gratis para ese tipo — el mínimo ahí es Starter sin excepción. Solo
  `juditrack-api` sí se puede bajar a plan gratis (ver más abajo).
- Base de datos y Redis: quedan en plan gratis para empezar. **La base de
  datos gratis se borra sola a los 30 días** si no la subes a un plan pago
  (~$6 USD/mes) antes de esa fecha — Render te avisa por correo.
- Frontend (sitio estático): gratis, siempre.

Si quieres bajar el costo inicial, puedes cambiar `plan: starter` por
`plan: free` **solo en `juditrack-api`** dentro de `render.yaml` (hace que
ese servicio se duerma tras 15 min sin uso y tarde ~1 min en despertar en
la siguiente visita). `juditrack-worker` y `juditrack-beat` son de tipo
"worker" en Render, y **Render no ofrece plan gratis para ese tipo de
servicio** — el mínimo ahí es Starter (~$7/mes cada uno), sin excepción.

Verifica los precios actuales antes de empezar en render.com/pricing,
porque pueden cambiar.

## Paso extra — Consigue credenciales SMTP para que lleguen los correos

Sin esto, la app funciona igual (puedes ver todo en el dashboard), pero no
te va a llegar el correo de "hay novedad en tu proceso". La forma más
rápida si no tienes un proveedor de correo transaccional es usar una
cuenta de Gmail con una "contraseña de aplicación" (no tu contraseña
normal):

1. Entra a **myaccount.google.com/security** con la cuenta de Gmail que
   quieras usar para enviar las notificaciones.
2. Activa la **verificación en dos pasos** si no la tienes activa (Google
   lo exige para poder generar contraseñas de aplicación).
3. Busca **"Contraseñas de aplicaciones"** (search bar de esa misma
   página) → elige un nombre cualquiera, p. ej. "JudiTrack" → **Crear**.
4. Google te muestra una contraseña de 16 caracteres — cópiala, es la
   única vez que la ves.
5. En Render, entra a **juditrack-api** → **Environment** y llena:
   - `SMTP_HOST` = `smtp.gmail.com`
   - `SMTP_PORT` = `587`
   - `SMTP_USER` = tu correo de Gmail completo
   - `SMTP_PASSWORD` = la contraseña de 16 caracteres del paso 4
6. Repite exactamente lo mismo en **juditrack-worker** (es el que de
   verdad envía el correo cuando detecta una novedad).
7. Guarda los cambios en ambos — cada uno se redespliega solo.

Si prefieres no usar tu Gmail personal, cualquier proveedor tipo
**Resend**, **SendGrid** o **Brevo** tiene un plan gratis pensado
justamente para esto y te dan host/usuario/contraseña SMTP en su panel,
también sin usar terminal.

## Primeros pasos dentro de la app, una vez publicada

1. Abre la URL de `juditrack-frontend`. Vas a ver la pantalla de acceso.
2. Clic en **"Registra tu firma"**, llena el formulario — esto crea tu
   cuenta como administrador.
3. (Recomendado) Activa la verificación en dos pasos con la app
   Google Authenticator o Authy en tu celular.
4. Clic en **"+ Añadir proceso"**, pega un radicado de 23 dígitos, ponle
   un alias para reconocerlo fácil, y guarda.
5. La primera consulta se dispara automáticamente en segundo plano — puede
   tardar uno o dos minutos la primera vez mientras el worker arranca el
   navegador. Actualiza la página o usa el botón **"Consultar ahora"**
   dentro del proceso para forzarla.
6. De ahí en adelante, el sistema revisa solo, en el horario configurado
   (por defecto cada 2 horas en días hábiles), y te avisa por correo
   cuando haya novedades.

## Si algo no funciona

- **El worker se cae o reinicia solo**: probablemente le falta memoria
  para Chromium. Sube su plan de "Starter" a "Standard" desde su página
  en Render → **Settings** → **Instance Type**.
- **"Failed to fetch" en el navegador**: revisa que `VITE_API_BASE` y
  `CORS_ORIGINS` tengan exactamente la URL del otro servicio, sin `/` al
  final, y que hayas guardado los cambios (esto redespliega solo, espera
  a que termine).
- **No llegan los correos de notificación**: rellena `SMTP_HOST`,
  `SMTP_USER`, `SMTP_PASSWORD` en el servicio `juditrack-api` **y** en
  `juditrack-worker` (son los que envían el correo) con los datos de tu
  proveedor de correo (p. ej. una cuenta de Gmail con "contraseña de
  aplicación", o un servicio como SendGrid/Resend).
