import { useEffect, useState } from "react";
import { api } from "../lib/api.js";

const ESTADO_LABEL = {
  ok: "Consulta exitosa, con novedades",
  sin_cambios: "Consulta exitosa, sin novedades",
  error_temporal: "Falló, se reintentará",
  error_permanente: "Falló, requiere atención",
};

export default function ProcesoDetalle({ procesoId, onVolver }) {
  const [proceso, setProceso] = useState(null);
  const [actuaciones, setActuaciones] = useState(null);
  const [auditoria, setAuditoria] = useState(null);
  const [pestaña, setPestaña] = useState("linea"); // linea | auditoria
  const [error, setError] = useState("");
  const [consultando, setConsultando] = useState(false);

  async function cargarTodo() {
    setError("");
    try {
      const [p, a] = await Promise.all([
        api.obtenerProceso(procesoId),
        api.listarActuaciones(procesoId),
      ]);
      setProceso(p);
      setActuaciones(a);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    cargarTodo();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [procesoId]);

  useEffect(() => {
    if (pestaña === "auditoria" && auditoria === null) {
      api.auditoriaProceso(procesoId).then(setAuditoria).catch((e) => setError(e.message));
    }
  }, [pestaña, procesoId, auditoria]);

  async function consultarAhora() {
    setConsultando(true);
    try {
      await api.consultarAhora(procesoId);
    } finally {
      setTimeout(() => setConsultando(false), 2000);
    }
  }

  async function alternarPausa() {
    if (proceso.activo) await api.pausarProceso(procesoId);
    else await api.reanudarProceso(procesoId);
    cargarTodo();
  }

  async function archivar() {
    if (!confirm("¿Archivar este proceso? Podrás seguir viendo su historial, pero dejará de monitorearse.")) return;
    await api.archivarProceso(procesoId);
    onVolver();
  }

  if (error) return <div className="alerta">{error}</div>;
  if (!proceso) return <p style={{ color: "var(--pizarra)" }}>Cargando…</p>;

  return (
    <div>
      <button className="link-boton" onClick={onVolver} style={{ marginBottom: 18 }}>
        ← Volver a tus procesos
      </button>

      <div className="encabezado-seccion">
        <div>
          <h1>{proceso.alias || "Proceso sin alias"}</h1>
          <div className="radicado" style={{ marginTop: 4 }}>{proceso.radicado}</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-outline" onClick={consultarAhora} disabled={consultando}>
            {consultando ? "Consultando…" : "Consultar ahora"}
          </button>
          <button className="btn btn-outline" onClick={alternarPausa}>
            {proceso.activo ? "Pausar" : "Reanudar"}
          </button>
          <button className="btn btn-danger" onClick={archivar}>Archivar</button>
        </div>
      </div>

      <div className="filtros">
        <button className={`filtro-chip ${pestaña === "linea" ? "activo" : ""}`} onClick={() => setPestaña("linea")}>
          Línea de tiempo
        </button>
        <button className={`filtro-chip ${pestaña === "auditoria" ? "activo" : ""}`} onClick={() => setPestaña("auditoria")}>
          Auditoría de consultas
        </button>
      </div>

      {pestaña === "linea" ? (
        actuaciones.length === 0 ? (
          <div className="estado-vacio">
            <h2>Sin actuaciones registradas todavía</h2>
            <p>En cuanto la primera consulta automática termine, aparecerán aquí.</p>
          </div>
        ) : (
          <div className="expediente">
            {[...actuaciones].reverse().map((a) => (
              <div key={a.id} className="actuacion">
                <div className="actuacion-fecha">{new Date(a.fecha_actuacion).toLocaleDateString("es-CO")}</div>
                <span className="actuacion-tipo">{a.tipo}</span>
                <p className="actuacion-anotacion">{a.anotacion}</p>
                {a.despacho && (
                  <p style={{ fontSize: 12.5, color: "var(--pizarra)", marginTop: 2 }}>{a.despacho}</p>
                )}
                {a.documento_url && (
                  <a href={a.documento_url} target="_blank" rel="noreferrer" style={{ fontSize: 13 }}>
                    Ver documento →
                  </a>
                )}
              </div>
            ))}
          </div>
        )
      ) : (
        <TablaAuditoria auditoria={auditoria} />
      )}
    </div>
  );
}

function TablaAuditoria({ auditoria }) {
  if (auditoria === null) return <p style={{ color: "var(--pizarra)" }}>Cargando…</p>;
  if (auditoria.length === 0) {
    return (
      <div className="estado-vacio">
        <h2>Todavía no hay corridas registradas</h2>
      </div>
    );
  }
  return (
    <div>
      {auditoria.map((run) => (
        <div key={run.id} className="tarjeta-proceso" style={{ cursor: "default" }}>
          <div className="tarjeta-proceso-top">
            <div>
              <div className="actuacion-fecha">{new Date(run.ejecutado_en).toLocaleString("es-CO")}</div>
              <p style={{ margin: "4px 0 0", fontSize: 14 }}>{ESTADO_LABEL[run.estado] || run.estado}</p>
            </div>
            {run.estado === "error_temporal" || run.estado === "error_permanente" ? (
              <span className="badge badge-novedad">Falló</span>
            ) : run.actuaciones_nuevas > 0 ? (
              <span className="badge badge-novedad">{run.actuaciones_nuevas} nueva(s)</span>
            ) : (
              <span className="badge badge-al-dia">Sin cambios</span>
            )}
          </div>
          {run.mensaje_error && (
            <p style={{ fontSize: 13, color: "var(--lacre)", marginTop: 8 }}>{run.mensaje_error}</p>
          )}
        </div>
      ))}
    </div>
  );
}
