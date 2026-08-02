import { useEffect, useState } from "react";
import { supabase } from "./lib/supabase.js";
import Acceso from "./pages/Acceso.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import ProcesoDetalle from "./pages/ProcesoDetalle.jsx";

export default function App() {
  const [autenticado, setAutenticado] = useState(null); // null = cargando
  const [procesoAbierto, setProcesoAbierto] = useState(null);
  const [vista, setVista] = useState("activos"); // activos | archivados

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setAutenticado(!!data.session));
    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      setAutenticado(!!session);
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  async function salir() {
    await supabase.auth.signOut();
    setProcesoAbierto(null);
  }

  if (autenticado === null) return null; // evita parpadeo mientras carga la sesión

  if (!autenticado) {
    return <Acceso onAutenticado={() => setAutenticado(true)} />;
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-brand">
          <span className="sello">J</span>
          <span className="marca-texto">
            JudiTrack <span className="marca-radicado">RAMA JUDICIAL · TYBA · SAMAI</span>
          </span>
        </div>
        <div className="topbar-actions">
          <button className="btn btn-ghost" onClick={salir}>Salir</button>
        </div>
      </header>
      {!procesoAbierto && (
        <nav className="subnav">
          <button className={vista === "activos" ? "activo" : ""} onClick={() => setVista("activos")}>
            Procesos activos
          </button>
          <button className={vista === "archivados" ? "activo" : ""} onClick={() => setVista("archivados")}>
            Archivados
          </button>
        </nav>
      )}
      <main className="main-content" style={{ maxWidth: 1180 }}>
        {procesoAbierto ? (
          <ProcesoDetalle procesoId={procesoAbierto} onVolver={() => setProcesoAbierto(null)} />
        ) : (
          <Dashboard key={vista} archivado={vista === "archivados"} onAbrirProceso={setProcesoAbierto} />
        )}
      </main>
    </div>
  );
}
