import { useEffect, useState } from "react";
import { api } from "../lib/api.js";

const FUENTES = [
  { value: "rama_judicial", label: "Rama Judicial (CPNU)" },
  { value: "samai", label: "SAMAI — Consejo de Estado (próximamente)" },
  { value: "spoa", label: "SPOA — Fiscalía (próximamente)" },
];

export default function Dashboard({ onAbrirProceso }) {
  const [procesos, setProcesos] = useState(null);
  const [filtro, setFiltro] = useState("todos"); // todos | con_novedades
  const [error, setError] = useState("");
  const [mostrarForm, setMostrarForm] = useState(false);

  async function cargar() {
    setError("");
    try {
      const params = filtro === "con_novedades" ? { con_novedades: "true" } : {};
      const data = await api.listarProcesos(params);
      setProcesos(data);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    cargar();
    const intervalo = setInterval(cargar, 60_000); // refresco pasivo, no dispara consultas nuevas
    return () => clearInterval(intervalo);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtro]);

  return (
    <div>
      <div className="encabezado-seccion">
        <h1>Tus procesos</h1>
        <button className="btn btn-primary" onClick={() => setMostrarForm((v) => !v)}>
          {mostrarForm ? "Cancelar" : "+ Añadir proceso"}
        </button>
      </div>

      {error && <div className="alerta">{error}</div>}

      {mostrarForm && <FormularioNuevoProceso onCreado={() => { setMostrarForm(false); cargar(); }} />}

      <div className="filtros">
        <button
          className={`filtro-chip ${filtro === "todos" ? "activo" : ""}`}
          onClick={() => setFiltro("todos")}
        >
          Todos
        </button>
        <button
          className={`filtro-chip ${filtro === "con_novedades" ? "activo" : ""}`}
          onClick={() => setFiltro("con_novedades")}
        >
          Con novedades
        </button>
      </div>

      {procesos === null ? (
        <p style={{ color: "var(--pizarra)" }}>Cargando…</p>
      ) : procesos.length === 0 ? (
        <div className="estado-vacio">
          <h2>Todavía no hay procesos aquí</h2>
          <p>Añade un radicado de 23 dígitos para empezar a monitorearlo automáticamente.</p>
        </div>
      ) : (
        procesos.map((p) => (
          <button key={p.id} className="tarjeta-proceso" onClick={() => onAbrirProceso(p.id)}>
            <div className="tarjeta-proceso-top">
              <div>
                <h3>{p.alias || "Proceso sin alias"}</h3>
                <div className="radicado">{p.radicado}</div>
              </div>
              {p.tiene_novedades ? (
                <span className="badge badge-novedad">Novedad</span>
              ) : !p.activo ? (
                <span className="badge badge-pausado">Pausado</span>
              ) : (
                <span className="badge badge-al-dia">Al día</span>
              )}
            </div>
            <div className="meta">
              {p.cliente && <>Cliente: {p.cliente} · </>}
              {p.jurisdiccion && <>{p.jurisdiccion} · </>}
              Fuente: {FUENTES.find((f) => f.value === p.fuente)?.label || p.fuente}
            </div>
          </button>
        ))
      )}
    </div>
  );
}

function FormularioNuevoProceso({ onCreado }) {
  const [radicado, setRadicado] = useState("");
  const [alias, setAlias] = useState("");
  const [cliente, setCliente] = useState("");
  const [jurisdiccion, setJurisdiccion] = useState("");
  const [fuente, setFuente] = useState("rama_judicial");
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);

  async function enviar(e) {
    e.preventDefault();
    setError("");
    const limpio = radicado.replace(/\s|-/g, "");
    if (!/^\d{23}$/.test(limpio)) {
      setError("El radicado debe tener exactamente 23 dígitos.");
      return;
    }
    setCargando(true);
    try {
      await api.crearProceso({ radicado: limpio, alias, cliente, jurisdiccion, fuente });
      onCreado();
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }

  async function subirCsv(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setCargando(true);
    setError("");
    try {
      const resp = await api.importarCsv(file);
      if (resp.errores?.length) {
        setError(`${resp.creados} procesos importados. ${resp.errores.length} filas con error (ver consola).`);
        console.warn("Errores de importación CSV:", resp.errores);
      }
      onCreado();
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }

  return (
    <div className="tarjeta-proceso" style={{ cursor: "default" }}>
      <h3 style={{ marginBottom: 14 }}>Nuevo proceso</h3>
      {error && <div className="alerta">{error}</div>}
      <form onSubmit={enviar}>
        <div className="field mono">
          <label>Radicado (23 dígitos)</label>
          <input
            required
            value={radicado}
            onChange={(e) => setRadicado(e.target.value)}
            placeholder="11001310300120230012300"
          />
        </div>
        <div className="field">
          <label>Fuente</label>
          <select value={fuente} onChange={(e) => setFuente(e.target.value)}>
            {FUENTES.map((f) => (
              <option key={f.value} value={f.value} disabled={f.value !== "rama_judicial"}>
                {f.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Alias (opcional)</label>
          <input value={alias} onChange={(e) => setAlias(e.target.value)} />
        </div>
        <div className="field">
          <label>Cliente (opcional)</label>
          <input value={cliente} onChange={(e) => setCliente(e.target.value)} />
        </div>
        <div className="field">
          <label>Jurisdicción (opcional)</label>
          <input value={jurisdiccion} onChange={(e) => setJurisdiccion(e.target.value)} />
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <button className="btn btn-primary" type="submit" disabled={cargando}>
            {cargando ? "Guardando…" : "Guardar y monitorear"}
          </button>
          <label className="btn btn-outline" style={{ cursor: "pointer" }}>
            Importar CSV
            <input type="file" accept=".csv" onChange={subirCsv} style={{ display: "none" }} />
          </label>
        </div>
      </form>
    </div>
  );
}
