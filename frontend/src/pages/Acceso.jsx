import { useState } from "react";
import { api } from "../lib/api.js";

export default function Acceso({ onAutenticado }) {
  const [modo, setModo] = useState("login"); // 'login' | 'registro'
  const [form, setForm] = useState({ email: "", password: "", codigo_2fa: "", nombre_firma: "", nombre_usuario: "" });
  const [pidiendo2fa, setPidiendo2fa] = useState(false);
  const [error, setError] = useState("");
  const [mensaje, setMensaje] = useState("");
  const [cargando, setCargando] = useState(false);

  function actualizar(campo, valor) {
    setForm((f) => ({ ...f, [campo]: valor }));
  }

  async function enviarLogin(e) {
    e.preventDefault();
    setError("");
    setCargando(true);
    try {
      await api.login({
        email: form.email,
        password: form.password,
        codigo_2fa: form.codigo_2fa || undefined,
      });
      onAutenticado();
    } catch (err) {
      if (err.message.toLowerCase().includes("dos pasos")) {
        setPidiendo2fa(true);
      } else {
        setError(err.message);
      }
    } finally {
      setCargando(false);
    }
  }

  async function enviarRegistro(e) {
    e.preventDefault();
    setError("");
    setMensaje("");
    setCargando(true);
    try {
      const resp = await api.registro({
        nombre_firma: form.nombre_firma,
        nombre_usuario: form.nombre_usuario,
        email: form.email,
        password: form.password,
      });
      if (resp.session) {
        onAutenticado();
      } else {
        setMensaje("Cuenta creada. Revisa tu correo y confirma tu cuenta antes de ingresar.");
        setModo("login");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
          <span className="sello" style={{ borderColor: "var(--ocre)", color: "var(--ink)", background: "var(--ink)" }}>J</span>
          <p className="titulo" style={{ margin: 0 }}>JudiTrack</p>
        </div>
        <p className="subtitulo">
          {modo === "login" ? "Ingresa a tu cuenta." : "Crea la cuenta de tu firma."}
        </p>

        {error && <div className="alerta">{error}</div>}
        {mensaje && (
          <div className="alerta" style={{ borderColor: "var(--verde-ok)", background: "var(--verde-ok-soft)", color: "var(--verde-ok)" }}>
            {mensaje}
          </div>
        )}

        {modo === "login" ? (
          <form onSubmit={enviarLogin}>
            <div className="field">
              <label>Correo</label>
              <input type="email" required value={form.email} onChange={(e) => actualizar("email", e.target.value)} />
            </div>
            <div className="field">
              <label>Contraseña</label>
              <input
                type="password"
                required
                value={form.password}
                onChange={(e) => actualizar("password", e.target.value)}
              />
            </div>
            {pidiendo2fa && (
              <div className="field">
                <label>Código de verificación (2FA)</label>
                <input
                  type="text"
                  inputMode="numeric"
                  autoFocus
                  value={form.codigo_2fa}
                  onChange={(e) => actualizar("codigo_2fa", e.target.value)}
                />
              </div>
            )}
            <button className="btn btn-primary" type="submit" disabled={cargando} style={{ width: "100%" }}>
              {cargando ? "Ingresando…" : "Ingresar"}
            </button>
            <p style={{ marginTop: 16, fontSize: 13.5 }}>
              ¿No tienes cuenta?{" "}
              <button type="button" className="link-boton" onClick={() => setModo("registro")}>
                Registra tu firma
              </button>
            </p>
          </form>
        ) : (
          <form onSubmit={enviarRegistro}>
            <div className="field">
              <label>Nombre de la firma</label>
              <input required value={form.nombre_firma} onChange={(e) => actualizar("nombre_firma", e.target.value)} />
            </div>
            <div className="field">
              <label>Tu nombre</label>
              <input required value={form.nombre_usuario} onChange={(e) => actualizar("nombre_usuario", e.target.value)} />
            </div>
            <div className="field">
              <label>Correo</label>
              <input type="email" required value={form.email} onChange={(e) => actualizar("email", e.target.value)} />
            </div>
            <div className="field">
              <label>Contraseña (mínimo 8 caracteres)</label>
              <input
                type="password"
                required
                minLength={8}
                value={form.password}
                onChange={(e) => actualizar("password", e.target.value)}
              />
            </div>
            <button className="btn btn-primary" type="submit" disabled={cargando} style={{ width: "100%" }}>
              {cargando ? "Creando…" : "Crear cuenta"}
            </button>
            <p style={{ marginTop: 16, fontSize: 13.5 }}>
              ¿Ya tienes cuenta?{" "}
              <button type="button" className="link-boton" onClick={() => setModo("login")}>
                Ingresa
              </button>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
