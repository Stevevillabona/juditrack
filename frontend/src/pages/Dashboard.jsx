import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api.js";

const FUENTES = [
  { value: "rama_judicial", label: "Rama Judicial (CPNU)" },
  { value: "tyba", label: "TYBA (Justicia XXI Web)" },
  { value: "samai", label: "SAMAI — Consejo de Estado (próximamente)" },
  { value: "spoa", label: "SPOA — Fiscalía (próximamente)" },
];

export default function Dashboard({ archivado = false, onAbrirProceso }) {
  const [procesos, setProcesos] = useState(null);
  const [soloNovedades, setSoloNovedades] = useState(false);
  const [busqueda, setBusqueda] = useState("");
  const [error, setError] = useState("");
  const [mostrarForm, setMostrarForm] = useState(false);

  async function cargar() {
    setError("");
    try {
      const params = { archivado };
      if (soloNovedades) params.con_novedades = "true";
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
  }, [soloNovedades, archivado]);

  const filtrados = useMemo(() => {
    if (!procesos) return null;
    const q = busqueda.trim().toLowerCase();
    if (!q) return procesos;
    return procesos.filter(
      (p) =>
        p.radicado.includes(q) ||
        (p.alias || "").toLowerCase().includes(q) ||
        (p.cliente || "").toLowerCase().includes(q)
    );
  }, [procesos, busqueda]);

  function exportarCsv() {
    if (!filtrados || filtrados.length === 0) return;
    const filas = [
      ["Radicado", "Alias", "Cliente", "Jurisdicción", "Última actuación", "Anotación", "Fecha"],
      ...filtrados.map((p) => [
        p.radicado,
        p.alias || "",
        p.cliente || "",
        p.jurisdiccion || "",
        p.ultima_actuacion?.tipo || "",
        (p.ultima_actuacion?.anotacion || "").replace(/[\n,]/g, " "),
        p.ultima_actuacion?.fecha ? new Date(p.ultima_actuacion.fecha).toLocaleDateString("es-CO") : "",
      ]),
    ];
    const csv = filas.map((f) => f.map((c) => `"${c}"`).join(",")).join("\n");
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "procesos.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

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

      <div className="tabla-toolbar">
        <input
          type="search"
          placeholder="Buscar por radicado, alias o cliente…"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
        />
        <label className="toolbar-check">
          <input type="checkbox" checked={soloNovedades} onChange={(e) => setSoloNovedades(e.target.checked)} />
          Solo con novedades
        </label>
        <div className="toolbar-divider" />
        <button className="btn btn-outline" onClick={exportarCsv}>Exportar a CSV</button>
      </div>

      <div className="leyenda-verde">
        Las filas en <b>verde</b> tienen actuaciones nuevas desde la última vez que las revisaste.
      </div>

      {filtrados === null ? (
        <p style={{ color: "var(--pizarra)" }}>Cargando…</p>
      ) : filtrados.length === 0 ? (
        <div className="estado-vacio">
          <h2>No hay procesos que coincidan</h2>
          <p>Añade un radicado de 23 dígitos para empezar a monitorearlo automáticamente.</p>
        </div>
      ) : (
        <div className="tabla-scroll">
          <table className="tabla-procesos">
            <thead>
              <tr>
                <th></th>
                <th>Radicado</th>
                <th>Alias / Cliente</th>
                <th>Última actuación</th>
                <th>Anotación</th>
                <th>Fecha</th>
                <th>Fuente</th>
              </tr>
            </thead>
            <tbody>
              {filtrados.map((p) => (
                <tr
                  key={p.id}
                  className={p.tiene_novedades ? "fila-novedad" : ""}
                  onClick={() => onAbrirProceso(p.id)}
                >
                  <td>
                    <span
                      className={`indicador-estado ${
                        p.tiene_novedades ? "novedad" : !p.activo ? "pausado" : "al-dia"
                      }`}
                      title={p.tiene_novedades ? "Con novedad" : !p.activo ? "Pausado" : "Al día"}
                    >
                      {p.tiene_novedades ? "!" : !p.activo ? "❚❚" : "✓"}
                    </span>
                  </td>
                  <td className="col-radicado">{p.radicado}</td>
                  <td className="col-alias">
                    {p.alias || "Sin alias"}
                    {p.cliente && <div style={{ fontWeight: 400, fontSize: 12.5, color: "var(--pizarra)" }}>{p.cliente}</div>}
                  </td>
                  <td>{p.ultima_actuacion?.tipo || "—"}</td>
                  <td style={{ maxWidth: 320 }}>
                    {p.ultima_actuacion?.anotacion ? p.ultima_actuacion.anotacion.slice(0, 140) : "—"}
                  </td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    {p.ultima_actuacion?.fecha ? new Date(p.ultima_actuacion.fecha).toLocaleDateString("es-CO") : "—"}
                  </td>
                  <td>{FUENTES.find((f) => f.value === p.fuente)?.label.split(" (")[0] || p.fuente}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
              <option key={f.value} value={f.value} disabled={f.value === "samai" || f.value === "spoa"}>
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
