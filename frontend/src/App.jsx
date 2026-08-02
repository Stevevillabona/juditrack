import { useEffect, useState } from "react";
import { getToken, setToken } from "./lib/api.js";
import Acceso from "./pages/Acceso.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import ProcesoDetalle from "./pages/ProcesoDetalle.jsx";

export default function App() {
  const [autenticado, setAutenticado] = useState(!!getToken());
  const [procesoAbierto, setProcesoAbierto] = useState(null);

  useEffect(() => {
    const handler = () => setAutenticado(false);
    window.addEventListener("juditrack:no-autenticado", handler);
    return () => window.removeEventListener("juditrack:no-autenticado", handler);
  }, []);

  function salir() {
    setToken(null);
    setAutenticado(false);
    setProcesoAbierto(null);
  }

  if (!autenticado) {
    return <Acceso onAutenticado={() => setAutenticado(true)} />;
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-brand">
          JudiTrack <span className="marca-radicado">RAMA JUDICIAL · SAMAI · SPOA</span>
        </div>
        <div className="topbar-actions">
          <button className="btn btn-ghost" onClick={salir}>Salir</button>
        </div>
      </header>
      <main className="main-content">
        {procesoAbierto ? (
          <ProcesoDetalle procesoId={procesoAbierto} onVolver={() => setProcesoAbierto(null)} />
        ) : (
          <Dashboard onAbrirProceso={setProcesoAbierto} />
        )}
      </main>
    </div>
  );
}
