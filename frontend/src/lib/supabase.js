import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!url || !anonKey) {
  // Esto solo debería pasar si alguien olvidó configurar los secrets de
  // GitHub (SUPABASE_URL / SUPABASE_ANON_KEY) antes de compilar. Falla
  // rápido y claro en vez de dar errores raros de red más adelante.
  console.error(
    "Falta VITE_SUPABASE_URL o VITE_SUPABASE_ANON_KEY. Revisa los secrets del repositorio en GitHub."
  );
}

export const supabase = createClient(url, anonKey);
