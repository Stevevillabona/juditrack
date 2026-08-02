"""
Pruebas de la lógica que no depende de FastAPI/SQLAlchemy/Celery, para
poder correrlas con `python -m unittest` sin instalar nada más.

Ejecutar desde backend/:  python -m unittest tests.test_diff_engine -v
"""
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.connectors.base import ActuacionCruda, MetadatosProceso  # noqa: E402
from app.connectors.rama_judicial import RADICADO_REGEX  # noqa: E402
from app.services.diff_engine import calcular_diff, fingerprint_actuacion  # noqa: E402


class TestValidacionRadicado(unittest.TestCase):
    def test_radicado_valido_23_digitos(self):
        self.assertTrue(RADICADO_REGEX.match("11001310300120230012300"))

    def test_radicado_invalido_pocos_digitos(self):
        self.assertFalse(RADICADO_REGEX.match("1234567890"))

    def test_radicado_invalido_con_letras(self):
        self.assertFalse(RADICADO_REGEX.match("1100131030012023001230A"))


class TestDiffEngine(unittest.TestCase):
    def _actuacion(self, tipo="auto", dia=1, anotacion="Se admite la demanda"):
        return ActuacionCruda(tipo=tipo, fecha_actuacion=datetime(2026, 1, dia), anotacion=anotacion)

    def test_actuacion_nueva_se_detecta(self):
        a1 = self._actuacion(dia=1)
        resultado = calcular_diff(set(), [a1], None, None)
        self.assertEqual(len(resultado.actuaciones_nuevas), 1)
        self.assertTrue(resultado.hay_novedades)

    def test_actuacion_ya_conocida_no_se_reporta(self):
        a1 = self._actuacion(dia=1)
        fp_existente = {fingerprint_actuacion(a1)}
        resultado = calcular_diff(fp_existente, [a1], None, None)
        self.assertEqual(len(resultado.actuaciones_nuevas), 0)
        self.assertFalse(resultado.hay_novedades)

    def test_mezcla_de_conocidas_y_nuevas(self):
        a1 = self._actuacion(dia=1, anotacion="Primera actuación")
        a2 = self._actuacion(dia=2, anotacion="Segunda actuación, es nueva")
        fp_existente = {fingerprint_actuacion(a1)}
        resultado = calcular_diff(fp_existente, [a1, a2], None, None)
        self.assertEqual(len(resultado.actuaciones_nuevas), 1)
        self.assertEqual(resultado.actuaciones_nuevas[0].anotacion, "Segunda actuación, es nueva")

    def test_cambio_de_despacho_se_detecta(self):
        previos = MetadatosProceso(despacho="Juzgado 1 Civil del Circuito de Bogotá")
        actuales = MetadatosProceso(despacho="Juzgado 5 Civil del Circuito de Bogotá")
        resultado = calcular_diff(set(), [], previos, actuales)
        tipos = [c.tipo for c in resultado.cambios]
        self.assertIn("cambio_despacho", tipos)

    def test_mismo_despacho_no_genera_cambio(self):
        previos = MetadatosProceso(despacho="Juzgado 1 Civil del Circuito de Bogotá")
        actuales = MetadatosProceso(despacho="Juzgado 1 Civil del Circuito de Bogotá")
        resultado = calcular_diff(set(), [], previos, actuales)
        self.assertFalse(resultado.hay_novedades)

    def test_nueva_audiencia_genera_cambio_especial(self):
        a1 = self._actuacion(dia=1)
        a1.fecha_audiencia = datetime(2026, 3, 15, 9, 0)
        resultado = calcular_diff(set(), [a1], None, None)
        tipos = [c.tipo for c in resultado.cambios]
        self.assertIn("nueva_audiencia", tipos)

    def test_fingerprint_es_estable_y_determinista(self):
        a1 = self._actuacion()
        a2 = self._actuacion()  # mismos valores, instancia distinta
        self.assertEqual(fingerprint_actuacion(a1), fingerprint_actuacion(a2))

    def test_fingerprint_cambia_si_cambia_la_anotacion(self):
        a1 = self._actuacion(anotacion="Texto A")
        a2 = self._actuacion(anotacion="Texto B")
        self.assertNotEqual(fingerprint_actuacion(a1), fingerprint_actuacion(a2))


if __name__ == "__main__":
    unittest.main()
