"""
Conector para la Consulta de Procesos Nacional Unificada (CPNU) de la
Rama Judicial: https://consultaprocesos.ramajudicial.gov.co

El portal es una SPA que requiere JavaScript (no hay API pública ni CORS
para terceros), así que este conector navega con Playwright headless,
exactamente como haría un usuario humano, y extrae los datos del DOM
renderizado. Corre en el servidor: nunca en el navegador del cliente.

Formato del radicado (23 dígitos), según el manual oficial del CPNU:
  DD  CCC  EE  EE  DDD  AAAA  NNNNN  II
  02  departamento | 03 ciudad | 02 entidad/corporación | 02 especialidad
  03 despacho | 04 año de radicación | 05 consecutivo | 02 instancia

Nota de mantenimiento: los selectores CSS/XPath de abajo son el punto más
frágil de este conector. Si la Rama Judicial cambia su HTML, este conector
debe fallar con ResultadoConsulta.FUENTE_CAMBIO_ESTRUCTURA (no con una
excepción cruda) para que el sistema de observabilidad lo detecte y alerte
al equipo antes de que lo note un usuario.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError, async_playwright

from app.connectors.base import (
    ActuacionCruda,
    ConectorFuente,
    MetadatosProceso,
    ResultadoConsulta,
    RespuestaConsulta,
)

URL_CONSULTA = "https://consultaprocesos.ramajudicial.gov.co/Procesos/NumeroRadicacion"
RADICADO_REGEX = re.compile(r"^\d{23}$")

# Selectores centralizados: si el portal cambia el HTML, se ajustan aquí y
# solo aquí. (Estos son representativos de la estructura típica de un
# formulario Angular/Blazor de este tipo de portal gubernamental; deben
# verificarse y ajustarse contra el DOM real antes de producción, idealmente
# con un test de "smoke" diario que compare contra un radicado de control.)
SEL_INPUT_RADICADO = "input#numero_radicado, input[formcontrolname='numeroRadicacion']"
SEL_BOTON_CONSULTAR = "button:has-text('Consultar')"
SEL_TABLA_RESULTADOS = "table.table-resultados, table:has-text('Actuación')"
SEL_FILA_ACTUACION = f"{SEL_TABLA_RESULTADOS} tbody tr"
SEL_MENSAJE_NO_ENCONTRADO = "text=/no se encontr(ó|aron) (información|resultados)/i"
SEL_CAPTCHA = "iframe[src*='recaptcha'], div.g-recaptcha"
SEL_PANEL_METADATOS = "div.datos-proceso, section#informacion-proceso"


def _fingerprint(tipo: str, fecha: str, anotacion: str) -> str:
    raw = f"{tipo}|{fecha}|{anotacion}".strip().lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_fecha(texto: str) -> datetime | None:
    texto = texto.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, fmt)
        except ValueError:
            continue
    return None


class ConectorRamaJudicial(ConectorFuente):
    nombre_fuente = "rama_judicial"

    def valida_radicado(self, radicado: str) -> bool:
        return bool(RADICADO_REGEX.match(radicado))

    async def consultar(self, radicado: str) -> RespuestaConsulta:
        if not self.valida_radicado(radicado):
            return RespuestaConsulta(
                resultado=ResultadoConsulta.RADICADO_NO_ENCONTRADO,
                mensaje=f"Radicado '{radicado}' no tiene el formato de 23 dígitos esperado.",
            )

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                ),
                locale="es-CO",
            )
            page = await context.new_page()
            try:
                return await self._consultar_en_pagina(page, radicado)
            except PlaywrightTimeoutError:
                return RespuestaConsulta(
                    resultado=ResultadoConsulta.ERROR_TEMPORAL,
                    mensaje="Timeout esperando respuesta del portal de la Rama Judicial.",
                )
            finally:
                await context.close()
                await browser.close()

    async def _consultar_en_pagina(self, page: Page, radicado: str) -> RespuestaConsulta:
        await page.goto(URL_CONSULTA, wait_until="networkidle", timeout=30_000)

        if await page.locator(SEL_CAPTCHA).count() > 0:
            return RespuestaConsulta(
                resultado=ResultadoConsulta.BLOQUEADO_O_CAPTCHA,
                mensaje="El portal presentó un captcha. Se reintentará más tarde con backoff.",
            )

        try:
            await page.wait_for_selector(SEL_INPUT_RADICADO, timeout=15_000)
        except PlaywrightTimeoutError:
            return RespuestaConsulta(
                resultado=ResultadoConsulta.FUENTE_CAMBIO_ESTRUCTURA,
                mensaje="No se encontró el campo de radicado esperado; el portal pudo haber cambiado su HTML.",
            )

        await page.fill(SEL_INPUT_RADICADO, radicado)
        await page.click(SEL_BOTON_CONSULTAR)

        # Esperamos a que aparezca la tabla de resultados O un mensaje de "no encontrado"
        try:
            await page.wait_for_selector(
                f"{SEL_TABLA_RESULTADOS}, {SEL_MENSAJE_NO_ENCONTRADO}", timeout=20_000
            )
        except PlaywrightTimeoutError:
            return RespuestaConsulta(
                resultado=ResultadoConsulta.ERROR_TEMPORAL,
                mensaje="El portal no respondió con resultados ni con mensaje de error en el tiempo esperado.",
            )

        if await page.locator(SEL_MENSAJE_NO_ENCONTRADO).count() > 0:
            return RespuestaConsulta(
                resultado=ResultadoConsulta.RADICADO_NO_ENCONTRADO,
                mensaje="El radicado no arrojó resultados en el CPNU.",
            )

        metadatos = await self._extraer_metadatos(page)
        actuaciones = await self._extraer_actuaciones(page)

        return RespuestaConsulta(
            resultado=ResultadoConsulta.OK,
            metadatos=metadatos,
            actuaciones=actuaciones,
        )

    async def _extraer_metadatos(self, page: Page) -> MetadatosProceso:
        panel = page.locator(SEL_PANEL_METADATOS)
        if await panel.count() == 0:
            return MetadatosProceso()

        texto_panel = await panel.first.inner_text()
        # Extracción por etiqueta:valor, tolerante a variaciones de layout.
        campos = dict(
            re.findall(r"([A-Za-zÁÉÍÓÚñÑ ]+):\s*([^\n]+)", texto_panel)
        )
        despacho = campos.get("Despacho") or campos.get("Despacho actual")
        tipo_proceso = campos.get("Tipo de proceso") or campos.get("Tipo Proceso")
        clase_proceso = campos.get("Clase de proceso") or campos.get("Clase Proceso")
        fecha_radicacion_txt = campos.get("Fecha de radicación") or campos.get("Fecha Radicación")

        partes: list[str] = []
        partes_locator = page.locator("div.partes-proceso li, section#partes li")
        for i in range(await partes_locator.count()):
            partes.append((await partes_locator.nth(i).inner_text()).strip())

        return MetadatosProceso(
            despacho=despacho.strip() if despacho else None,
            tipo_proceso=tipo_proceso.strip() if tipo_proceso else None,
            clase_proceso=clase_proceso.strip() if clase_proceso else None,
            partes=partes,
            fecha_radicacion=_parse_fecha(fecha_radicacion_txt) if fecha_radicacion_txt else None,
            extra=campos,
        )

    async def _extraer_actuaciones(self, page: Page) -> list[ActuacionCruda]:
        filas = page.locator(SEL_FILA_ACTUACION)
        n = await filas.count()
        actuaciones: list[ActuacionCruda] = []

        for i in range(n):
            fila = filas.nth(i)
            celdas = fila.locator("td")
            if await celdas.count() < 3:
                continue

            fecha_txt = (await celdas.nth(0).inner_text()).strip()
            tipo_txt = (await celdas.nth(1).inner_text()).strip()
            anotacion_txt = (await celdas.nth(2).inner_text()).strip()

            fecha = _parse_fecha(fecha_txt) or datetime.min
            despacho_txt = None
            if await celdas.count() > 3:
                despacho_txt = (await celdas.nth(3).inner_text()).strip()

            doc_url = None
            enlace = fila.locator("a[href]")
            if await enlace.count() > 0:
                doc_url = await enlace.first.get_attribute("href")

            actuaciones.append(
                ActuacionCruda(
                    tipo=tipo_txt,
                    fecha_actuacion=fecha,
                    anotacion=anotacion_txt,
                    despacho=despacho_txt,
                    documento_url=doc_url,
                )
            )

        return actuaciones
