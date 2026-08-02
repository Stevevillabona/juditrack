-- =====================================================================
-- Esquema de JudiTrack para Supabase.
--
-- Cómo usarlo: pega este archivo completo en el "SQL Editor" del panel
-- de Supabase (Supabase → tu proyecto → SQL Editor → New query) y dale
-- a "Run". Crea todas las tablas, la seguridad por fila (RLS) y los
-- disparadores necesarios en un solo paso.
--
-- Diseño: cada persona que se registra crea automáticamente su propia
-- "firma" (tenant) y queda como admin de ella. RLS asegura que cada
-- usuario solo vea los procesos de su propia firma, directamente a nivel
-- de base de datos — no hace falta un backend que lo revise a mano.
-- =====================================================================

-- ---------- Firmas (tenants) ----------
create table public.firmas (
  id uuid primary key default gen_random_uuid(),
  nombre text not null,
  plan text not null default 'free',
  created_at timestamptz not null default now()
);

-- ---------- Perfiles (un perfil por usuario de Supabase Auth) ----------
create table public.perfiles (
  id uuid primary key references auth.users(id) on delete cascade,
  firma_id uuid not null references public.firmas(id) on delete cascade,
  nombre text not null,
  email text not null,
  rol text not null default 'admin' check (rol in ('admin', 'abogado', 'asistente')),
  created_at timestamptz not null default now()
);

-- Cuando alguien se registra en Supabase Auth, esto crea su firma y su
-- perfil automáticamente, leyendo los datos que mandamos en el registro
-- (ver metadata `nombre_firma` / `nombre_usuario` en el frontend).
create function public.manejar_nuevo_usuario()
returns trigger
language plpgsql
security definer set search_path = public
as $$
declare
  nueva_firma_id uuid;
begin
  insert into public.firmas (nombre)
  values (coalesce(new.raw_user_meta_data->>'nombre_firma', 'Mi firma'))
  returning id into nueva_firma_id;

  insert into public.perfiles (id, firma_id, nombre, email, rol)
  values (
    new.id,
    nueva_firma_id,
    coalesce(new.raw_user_meta_data->>'nombre_usuario', new.email),
    new.email,
    'admin'
  );
  return new;
end;
$$;

create trigger al_crear_usuario
  after insert on auth.users
  for each row execute procedure public.manejar_nuevo_usuario();

-- ---------- Procesos ----------
create table public.procesos (
  id uuid primary key default gen_random_uuid(),
  firma_id uuid not null references public.firmas(id) on delete cascade,
  radicado text not null check (radicado ~ '^[0-9]{23}$'),
  fuente text not null default 'rama_judicial',
  alias text,
  cliente text,
  jurisdiccion text,
  apoderado_id uuid references public.perfiles(id),
  tags jsonb not null default '[]',
  metadatos jsonb not null default '{}',
  notificar_canales jsonb not null default '["email"]',
  avisar_todo boolean not null default true,
  tipos_permitidos jsonb not null default '[]',
  estado_hash text,
  archivado boolean not null default false,
  activo boolean not null default true,
  created_at timestamptz not null default now(),
  unique (firma_id, radicado, fuente)
);

-- El frontend nunca envía firma_id: se asigna aquí automáticamente a
-- partir de la sesión del usuario, así no puede falsificarse desde el
-- navegador ni hace falta que el cliente lo conozca de antemano.
create function public.asignar_firma_id_proceso()
returns trigger
language plpgsql security definer set search_path = public
as $$
begin
  new.firma_id := public.mi_firma_id();
  return new;
end;
$$;

create trigger antes_de_insertar_proceso
  before insert on public.procesos
  for each row execute procedure public.asignar_firma_id_proceso();

-- ---------- Actuaciones (historial inmutable, insert-only) ----------
create table public.actuaciones (
  id uuid primary key default gen_random_uuid(),
  proceso_id uuid not null references public.procesos(id) on delete cascade,
  fingerprint text not null,
  tipo text not null,
  fecha_actuacion timestamptz not null,
  anotacion text not null,
  despacho text,
  ponente text,
  fecha_audiencia timestamptz,
  documento_url text,
  detectada_en timestamptz not null default now(),
  unique (proceso_id, fingerprint)
);

-- ---------- Marca de "visto" por usuario ----------
create table public.procesos_vistos (
  id uuid primary key default gen_random_uuid(),
  proceso_id uuid not null references public.procesos(id) on delete cascade,
  usuario_id uuid not null references public.perfiles(id) on delete cascade,
  visto_hasta timestamptz not null,
  unique (proceso_id, usuario_id)
);

-- ---------- Auditoría de cada corrida contra la fuente ----------
create table public.consulta_runs (
  id uuid primary key default gen_random_uuid(),
  proceso_id uuid not null references public.procesos(id) on delete cascade,
  fuente text not null,
  estado text not null check (estado in ('ok', 'sin_cambios', 'error_temporal', 'error_permanente')),
  intento_numero int not null default 1,
  actuaciones_nuevas int not null default 0,
  mensaje_error text,
  duracion_ms int,
  ejecutado_en timestamptz not null default now()
);

-- =====================================================================
-- Seguridad por fila (RLS): cada usuario solo ve/edita lo de su firma.
-- =====================================================================

alter table public.firmas enable row level security;
alter table public.perfiles enable row level security;
alter table public.procesos enable row level security;
alter table public.actuaciones enable row level security;
alter table public.procesos_vistos enable row level security;
alter table public.consulta_runs enable row level security;

-- Función auxiliar: firma_id del usuario autenticado actual.
create function public.mi_firma_id()
returns uuid
language sql stable security definer set search_path = public
as $$
  select firma_id from public.perfiles where id = auth.uid();
$$;

create policy "ver mi firma" on public.firmas
  for select using (id = public.mi_firma_id());

create policy "ver perfiles de mi firma" on public.perfiles
  for select using (firma_id = public.mi_firma_id());

create policy "gestionar procesos de mi firma" on public.procesos
  for all using (firma_id = public.mi_firma_id())
  with check (firma_id = public.mi_firma_id());

create policy "ver actuaciones de mi firma" on public.actuaciones
  for select using (
    proceso_id in (select id from public.procesos where firma_id = public.mi_firma_id())
  );

create policy "gestionar mis marcas de visto" on public.procesos_vistos
  for all using (usuario_id = auth.uid())
  with check (usuario_id = auth.uid());

create policy "ver auditoria de mi firma" on public.consulta_runs
  for select using (
    proceso_id in (select id from public.procesos where firma_id = public.mi_firma_id())
  );

-- El script de GitHub Actions usa la "service role key" (no la anon key),
-- que por diseño de Supabase se salta RLS por completo — así puede leer y
-- escribir en todas las firmas para hacer el monitoreo de todos los
-- usuarios. Esa llave NUNCA debe usarse en el frontend, solo en el
-- secreto de GitHub Actions (ver DESPLIEGUE_GRATIS.md).
