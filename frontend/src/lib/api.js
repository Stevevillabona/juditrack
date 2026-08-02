import { supabase } from "./supabase.js";

const GITHUB_REPO_URL = import.meta.env.VITE_GITHUB_REPO_URL || "";

function requireOk({ error }) {
  if (error) throw new Error(error.message);
}

// ---------------------------------------------------------------- auth

async function registro({ nombre_firma, nombre_usuario, email, password }) {
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: { data: { nombre_firma, nombre_usuario } },
  });
  if (error) throw new Error(error.message);
  return data;
}

async function login({ email, password, codigo_2fa }) {
  const { error: errorLogin } = await supabase.auth.signInWithPassword({ email, password });
  if (errorLogin) throw new Error(errorLogin.message);

  const { data: aal } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
  const requiereMfa = aal && aal.nextLevel === "aal2" && aal.nextLevel !== aal.currentLevel;

  if (requiereMfa) {
    if (!codigo_2fa) {
      throw new Error("Esta cuenta tiene verificación en dos pasos activa.");
    }
    const { data: factores, error: errorFactores } = await supabase.auth.mfa.listFactors();
    if (errorFactores) throw new Error(errorFactores.message);
    const factor = factores.totp[0];
    if (!factor) throw new Error("No se encontró el segundo factor configurado.");

    const { data: challenge, error: errorChallenge } = await supabase.auth.mfa.challenge({
      factorId: factor.id,
    });
    if (errorChallenge) throw new Error(errorChallenge.message);

    const { error: errorVerify } = await supabase.auth.mfa.verify({
      factorId: factor.id,
      challengeId: challenge.id,
      code: codigo_2fa,
    });
    if (errorVerify) throw new Error("Código de verificación incorrecto.");
  }
  return true;
}

async function logout() {
  await supabase.auth.signOut();
}

async function iniciar2fa() {
  const { data, error } = await supabase.auth.mfa.enroll({ factorType: "totp" });
  if (error) throw new Error(error.message);
  return { factorId: data.id, secret: data.totp.secret, otpauth_uri: data.totp.uri, qr: data.totp.qr_code };
}

async function confirmar2fa(factorId, codigo) {
  const { data: challenge, error: errorChallenge } = await supabase.auth.mfa.challenge({ factorId });
  if (errorChallenge) throw new Error(errorChallenge.message);
  const { error } = await supabase.auth.mfa.verify({ factorId, challengeId: challenge.id, code: codigo });
  if (error) throw new Error("Código incorrecto. Intenta de nuevo.");
}

// ---------------------------------------------------------------- procesos

function tieneNovedades(proceso) {
  const actuaciones = proceso.actuaciones || [];
  if (actuaciones.length === 0) return false;
  const ultima = actuaciones.reduce((max, a) => (a.detectada_en > max ? a.detectada_en : max), actuaciones[0].detectada_en);
  const marca = (proceso.procesos_vistos || [])[0];
  if (!marca) return true;
  return ultima > marca.visto_hasta;
}

function mapProceso(p) {
  const ultima = (p.actuaciones || [])[0] || null;
  return {
    id: p.id,
    radicado: p.radicado,
    fuente: p.fuente,
    alias: p.alias,
    cliente: p.cliente,
    jurisdiccion: p.jurisdiccion,
    activo: p.activo,
    archivado: p.archivado,
    tiene_novedades: tieneNovedades(p),
    ultima_actuacion: ultima
      ? { tipo: ultima.tipo, anotacion: ultima.anotacion, fecha: ultima.fecha_actuacion }
      : null,
  };
}

async function listarProcesos({ con_novedades, cliente, jurisdiccion, archivado } = {}) {
  let query = supabase
    .from("procesos")
    .select("*, actuaciones(tipo,anotacion,fecha_actuacion,detectada_en), procesos_vistos(visto_hasta)")
    .eq("archivado", archivado === "true" || archivado === true)
    .order("detectada_en", { foreignTable: "actuaciones", ascending: false })
    .limit(1, { foreignTable: "actuaciones" });
  if (cliente) query = query.eq("cliente", cliente);
  if (jurisdiccion) query = query.eq("jurisdiccion", jurisdiccion);

  const { data, error } = await query;
  if (error) throw new Error(error.message);

  let procesos = data.map((p) => mapProceso(p));
  if (con_novedades === "true" || con_novedades === true) {
    procesos = procesos.filter((p) => p.tiene_novedades);
  }
  return procesos;
}

async function crearProceso({ radicado, fuente, alias, cliente, jurisdiccion }) {
  const { data, error } = await supabase
    .from("procesos")
    .insert({ radicado, fuente, alias: alias || null, cliente: cliente || null, jurisdiccion: jurisdiccion || null })
    .select()
    .single();
  if (error) throw new Error(error.message);
  return mapProceso({ ...data, actuaciones: [], procesos_vistos: [] });
}

async function obtenerProceso(id) {
  const { data, error } = await supabase
    .from("procesos")
    .select("*, actuaciones(detectada_en), procesos_vistos(visto_hasta)")
    .eq("id", id)
    .single();
  if (error) throw new Error(error.message);

  const proceso = mapProceso(data);

  // Marca de "visto" al abrir el detalle.
  const { data: userData } = await supabase.auth.getUser();
  const ahora = new Date().toISOString();
  await supabase
    .from("procesos_vistos")
    .upsert({ proceso_id: id, usuario_id: userData.user.id, visto_hasta: ahora }, { onConflict: "proceso_id,usuario_id" });

  return proceso;
}

async function listarActuaciones(id) {
  const { data, error } = await supabase
    .from("actuaciones")
    .select("*")
    .eq("proceso_id", id)
    .order("fecha_actuacion", { ascending: true });
  if (error) throw new Error(error.message);
  return data;
}

async function auditoriaProceso(id) {
  const { data, error } = await supabase
    .from("consulta_runs")
    .select("*")
    .eq("proceso_id", id)
    .order("ejecutado_en", { ascending: false })
    .limit(100);
  if (error) throw new Error(error.message);
  return data;
}

async function archivarProceso(id) {
  requireOk(await supabase.from("procesos").update({ archivado: true, activo: false }).eq("id", id));
}

async function pausarProceso(id) {
  requireOk(await supabase.from("procesos").update({ activo: false }).eq("id", id));
}

async function reanudarProceso(id) {
  requireOk(await supabase.from("procesos").update({ activo: true }).eq("id", id));
}

// No hay un backend permanente que "encole" una consulta inmediata en esta
// arquitectura gratuita: el scraping corre por GitHub Actions cada 2 horas.
// Esta función devuelve el link para que el usuario, si quiere, dispare una
// corrida manual él mismo desde GitHub (sigue siendo solo navegador).
function urlConsultaManual(procesoId) {
  if (!GITHUB_REPO_URL) return null;
  return { url: `${GITHUB_REPO_URL}/actions/workflows/monitor.yml`, procesoId };
}

async function importarCsv(file) {
  const texto = await file.text();
  const [encabezado, ...filas] = texto.trim().split(/\r?\n/);
  const columnas = encabezado.split(",").map((c) => c.trim().toLowerCase());

  const registros = filas
    .filter(Boolean)
    .map((linea) => {
      const valores = linea.split(",");
      const fila = {};
      columnas.forEach((col, i) => (fila[col] = (valores[i] || "").trim()));
      return fila;
    })
    .filter((f) => /^\d{23}$/.test(f.radicado || ""))
    .map((f) => ({
      radicado: f.radicado,
      fuente: f.fuente || "rama_judicial",
      alias: f.alias || null,
      cliente: f.cliente || null,
      jurisdiccion: f.jurisdiccion || null,
    }));

  if (registros.length === 0) {
    return { creados: 0, errores: [{ error: "Ningún radicado válido de 23 dígitos en el archivo." }] };
  }

  const { data, error } = await supabase.from("procesos").insert(registros).select();
  if (error) return { creados: 0, errores: [{ error: error.message }] };
  return { creados: data.length, errores: [] };
}

export const api = {
  registro,
  login,
  logout,
  iniciar2fa,
  confirmar2fa,
  listarProcesos,
  crearProceso,
  obtenerProceso,
  listarActuaciones,
  auditoriaProceso,
  archivarProceso,
  pausarProceso,
  reanudarProceso,
  urlConsultaManual,
  importarCsv,
};
