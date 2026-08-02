"""
Conector para TYBA (Justicia XXI Web, antes "Siglo XXI Web"), el portal
alterno de consulta de procesos de la Rama Judicial:
https://procesojudicial.ramajudicial.gov.co

A diferencia del CPNU (consultaprocesos.ramajudicial.gov.co, ya cubierto
por rama_judicial.py), TYBA expone además las piezas procesales
(documentos del expediente) descargables directamente desde el resultado
de la consulta, que es justo lo que este conector aprovecha para llenar
`ActuacionCruda.documento_url`.

Igual que el conector de la CPNU, es una aplicación que requiere
JavaScript/postbacks (es una app clásica de ASP.NET WebForms), así que se
navega con Playwright headless.

⚠️ Nota de confianza de los selectores: al no tener acceso a internet en
el entorno donde se escribió este conector, los selectores de abajo son
el mejor estimado a partir de la estructura típica de formularios
ASP.NET WebForms de este tipo de portal gubernamental (inputs con
`id`/`name` con prefijo `ctl00$ContentPlaceHolder1$...`). Deben
verificarse y ajustarse contra el DOM real (Playwright Inspector) antes
de usarse en producción — exactamente la misma advertencia que aplica a
`rama_judicial.py`.
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

URL_CONSULTA = "https://procesojudicial.ramajudicial.gov.co/Justicia21/Administracion/Ciudadanos/frmConsulta.aspx"
RADICADO_REGEX = re.compile(r"^\d{23}$")

# Selectores a verificar contra el DOM real (ver advertencia en el docstring).
SEL_INPUT_RADICADO = "input[name*='txtCodProceso'], input[id*='CodProceso']"
SEL_BOTON_CONSULTAR = "input[type='submit'][value*='Consultar'], button:has-text('Consultar')"
SEL_TABLA_ACTUACIONES = "table[id*='GridActuaciones'], table:has-text('Fecha Actuación')"
SEL_FILA_ACTUACION = f"{SEL_TABLA_ACTUACIONES} tr"
SEL_TABLA_PIEZAS = "table[id*='GridDocumentos'], table:has-text('Documento')"
SEL_MENSAJE_NO_ENCONTRADO = "text=/no se encontraron registros|proceso no existe/i"
SEL_CAPTCHA = "iframe[src*='recaptcha'], div.g-recaptcha"
SEL_PANEL_METADATOS = "div[id*='PanelDatosProceso'], fieldset:has-text('Datos del proceso')"


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


class ConectorTyba(ConectorFuente):
    nombre_fuente = "tyba"

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
                    mensaje="Timeout esperando respuesta del portal TYBA.",
                )
            finally:
                await context.close()
                await browser.close()

    async def _consultar_en_pagina(self, page: Page, radicado: str) -> RespuestaConsulta:
        await page.goto(URL_CONSULTA, wait_until="networkidle", timeout=30_000)

        if await page.locator(SEL_CAPTCHA).count() > 0:
            return RespuestaConsulta(
                resultado=ResultadoConsulta.BLOQUEADO_O_CAPTCHA,
                mensaje="El portal TYBA presentó un captcha. Se reintentará más tarde con backoff.",
            )

        try:
            await page.wait_for_selector(SEL_INPUT_RADICADO, timeout=15_000)
        except PlaywrightTimeoutError:
            return RespuestaConsulta(
                resultado=ResultadoConsulta.FUENTE_CAMBIO_ESTRUCTURA,
                mensaje="No se encontró el campo de radicado esperado; TYBA pudo haber cambiado su HTML.",
            )

        await page.fill(SEL_INPUT_RADICADO, radicado)
        await page.click(SEL_BOTON_CONSULTAR)
        # TYBA es ASP.NET WebForms clásico: el submit hace un postback completo
        # de página, no una petición AJAX — esperamos a que la navegación termine.
        await page.wait_for_load_state("networkidle", timeout=20_000)

        try:
            await page.wait_for_selector(
                f"{SEL_TABLA_ACTUACIONES}, {SEL_MENSAJE_NO_ENCONTRADO}", timeout=20_000
            )
        except PlaywrightTimeoutError:
            return RespuestaConsulta(
                resultado=ResultadoConsulta.ERROR_TEMPORAL,
                mensaje="TYBA no respondió con resultados ni con mensaje de error en el tiempo esperado.",
            )

        if await page.locator(SEL_MENSAJE_NO_ENCONTRADO).count() > 0:
            return RespuestaConsulta(
                resultado=ResultadoConsulta.RADICADO_NO_ENCONTRADO,
                mensaje="El radicado no arrojó resultados en TYBA.",
            )

        metadatos = await self._extraer_metadatos(page)
        piezas = await self._extraer_piezas_procesales(page)
        actuaciones = await self._extraer_actuaciones(page, piezas)

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
        campos = dict(re.findall(r"([A-Za-zÁÉÍÓÚñÑ ]+):\s*([^\n]+)", texto_panel))

        return MetadatosProceso(
            despacho=(campos.get("Despacho") or "").strip() or None,
            tipo_proceso=(campos.get("Tipo de proceso") or "").strip() or None,
            clase_proceso=(campos.get("Clase de proceso") or "").strip() or None,
            extra=campos,
        )

    async def _extraer_piezas_procesales(self, page: Page) -> dict[str, str]:
        """Mapa aproximado {fecha o descripción -> url del documento}, para
        cruzarlo con la tabla de actuaciones y así poblar `documento_url`."""
        piezas: dict[str, str] = {}
        tabla = page.locator(SEL_TABLA_PIEZAS)
        if await tabla.count() == 0:
            return piezas

        filas = tabla.locator("tr")
        for i in range(await filas.count()):
            fila = filas.nth(i)
            enlace = fila.locator("a[href]")
            if await enlace.count() == 0:
                continue
            texto_fila = (await fila.inner_text()).strip()
            href = await enlace.first.get_attribute("href")
            if href:
                piezas[texto_fila] = href
        return piezas

    async def _extraer_actuaciones(self, page: Page, piezas: dict[str, str]) -> list[ActuacionCruda]:
        filas = page.locator(SEL_FILA_ACTUACION)
        n = await filas.count()
        actuaciones: list[ActuacionCruda] = []

        for i in range(n):
            fila = filas.nth(i)
            celdas = fila.locator("td")
            if await celdas.count() < 3:
                continue  # probablemente la fila de encabezado

            fecha_txt = (await celdas.nth(0).inner_text()).strip()
            tipo_txt = (await celdas.nth(1).inner_text()).strip()
            anotacion_txt = (await celdas.nth(2).inner_text()).strip()
            fecha = _parse_fecha(fecha_txt) or datetime.min

            # Cruce best-effort con las piezas procesales: si el texto de
            # alguna fila de la tabla de documentos contiene la misma fecha,
            # asumimos que es el documento asociado a esta actuación.
            doc_url = next((url for texto, url in piezas.items() if fecha_txt in texto), None)

            actuaciones.append(
                ActuacionCruda(
                    tipo=tipo_txt,
                    fecha_actuacion=fecha,
                    anotacion=anotacion_txt,
                    documento_url=doc_url,
                )
            )

        return actuaciones
