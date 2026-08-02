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
  const [pestaña, setPestaña] = useState("linea"); // linea | documentos | auditoria
  const [error, setError] = useState("");

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
    const info = api.urlConsultaManual(procesoId);
    if (!info) {
      alert("El monitoreo corre automáticamente cada 2 horas en horario hábil. No hay un link de GitHub configurado para forzar una corrida manual.");
      return;
    }
    try {
      await navigator.clipboard.writeText(procesoId);
    } catch {
      /* portapapeles no disponible, no es crítico */
    }
    alert(
      "Copié el ID de este proceso al portapapeles. Se va a abrir la pestaña de GitHub Actions: haz clic en 'Run workflow', pega el ID en el campo 'proceso_id', y dale a 'Run workflow' otra vez."
    );
    window.open(info.url, "_blank");
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
          <button className="btn btn-outline" onClick={consultarAhora}>
            Forzar consulta (vía GitHub)
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
        <button className={`filtro-chip ${pestaña === "documentos" ? "activo" : ""}`} onClick={() => setPestaña("documentos")}>
          Documentos {actuaciones.filter((a) => a.documento_url).length > 0 && `(${actuaciones.filter((a) => a.documento_url).length})`}
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
      ) : pestaña === "documentos" ? (
        <ListaDocumentos actuaciones={actuaciones} />
      ) : (
        <TablaAuditoria auditoria={auditoria} />
      )}
    </div>
  );
}

function ListaDocumentos({ actuaciones }) {
  const conDocumento = actuaciones.filter((a) => a.documento_url);

  if (conDocumento.length === 0) {
    return (
      <div className="estado-vacio">
        <h2>No hay documentos disponibles todavía</h2>
        <p>
          Algunas fuentes (como TYBA) publican piezas procesales descargables; en cuanto la fuente
          exponga un documento para una actuación, aparecerá aquí.
        </p>
      </div>
    );
  }

  return (
    <div>
      {[...conDocumento].reverse().map((a) => (
        <a
          key={a.id}
          href={a.documento_url}
          target="_blank"
          rel="noreferrer"
          className="tarjeta-proceso"
          style={{ display: "flex", justifyContent: "space-between", alignItems: "center", textDecoration: "none" }}
        >
          <div>
            <span className="actuacion-tipo">{a.tipo}</span>
            <p style={{ margin: "6px 0 0", fontSize: 14, color: "var(--ink)" }}>{a.anotacion.slice(0, 140)}</p>
            <p className="actuacion-fecha" style={{ marginTop: 4 }}>
              {new Date(a.fecha_actuacion).toLocaleDateString("es-CO")}
            </p>
          </div>
          <span style={{ fontSize: 13, whiteSpace: "nowrap", marginLeft: 12 }}>Descargar →</span>
        </a>
      ))}
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
