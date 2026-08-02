const BASE = `${import.meta.env.VITE_API_BASE || ""}/api`;

function getToken() {
  return localStorage.getItem("juditrack_token");
}

export function setToken(token) {
  if (token) localStorage.setItem("juditrack_token", token);
  else localStorage.removeItem("juditrack_token");
}

async function request(path, { method = "GET", body, isForm = false } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (!isForm && body) headers["Content-Type"] = "application/json";

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401) {
    setToken(null);
    window.dispatchEvent(new Event("juditrack:no-autenticado"));
  }

  if (!res.ok) {
    let mensaje = `Error ${res.status}`;
    try {
      const data = await res.json();
      mensaje = data.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : mensaje;
    } catch {
      /* respuesta sin cuerpo JSON */
    }
    throw new Error(mensaje);
  }

  if (res.status === 204 || res.status === 202) {
    try {
      return await res.json();
    } catch {
      return null;
    }
  }
  return res.json();
}

export const api = {
  registro: (payload) => request("/auth/registro", { method: "POST", body: payload }),
  login: (payload) => request("/auth/login", { method: "POST", body: payload }),
  iniciar2fa: () => request("/auth/2fa/iniciar", { method: "POST" }),
  confirmar2fa: (codigo) => request("/auth/2fa/confirmar", { method: "POST", body: { codigo } }),

  listarProcesos: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/procesos${qs ? `?${qs}` : ""}`);
  },
  obtenerProceso: (id) => request(`/procesos/${id}`),
  crearProceso: (payload) => request("/procesos", { method: "POST", body: payload }),
  listarActuaciones: (id) => request(`/procesos/${id}/actuaciones`),
  auditoriaProceso: (id) => request(`/procesos/${id}/auditoria`),
  archivarProceso: (id) => request(`/procesos/${id}/archivar`, { method: "POST" }),
  pausarProceso: (id) => request(`/procesos/${id}/pausar`, { method: "POST" }),
  reanudarProceso: (id) => request(`/procesos/${id}/reanudar`, { method: "POST" }),
  consultarAhora: (id) => request(`/procesos/${id}/consultar-ahora`, { method: "POST" }),
  importarCsv: (file) => {
    const form = new FormData();
    form.append("archivo", file);
    return request("/procesos/importar-csv", { method: "POST", body: form, isForm: true });
  },
};

export { getToken };
