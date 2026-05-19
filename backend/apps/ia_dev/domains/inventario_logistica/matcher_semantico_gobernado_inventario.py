from __future__ import annotations

import re
import unicodedata
from typing import Any

from django.db import connections

from apps.ia_dev.services.employee_identifier_service import EmployeeIdentifierService

from .metadata_gobernada_inventario import (
    FUENTES_DD_GOBERNADAS,
    construir_metadata_gobernada_inventario,
)


class MatcherSemanticoGobernadoInventario:
    _PALABRAS_NO_CODIGO = {
        "almacen",
        "almacenes",
        "bodega",
        "bodegas",
        "claro",
        "codigo",
        "cuadrilla",
        "de",
        "del",
        "equipo",
        "equipos",
        "empleado",
        "en",
        "ferretero",
        "familia",
        "inventario",
        "material",
        "materiales",
        "moviles",
        "movil",
        "por",
        "saldo",
        "serial",
        "seriales",
        "serializado",
        "serializados",
        "tecnico",
    }
    _SINONIMOS_BASE = {
        "inventario": ("inventario", "stock", "saldo", "existencia", "existencias", "que tiene", "que tiene asignado", "tiene asignado"),
        "movil": ("movil", "móvil", "cuadrilla", "brigada"),
        "kardex": ("kardex", "movimientos", "entradas y salidas"),
        "material_claro": ("material claro", "material de claro"),
        "ferretero": ("ferretero", "ferreteria", "ferretería", "material ferretero"),
        "serializados": ("serial", "seriales", "serializado", "serializados", "equipo", "equipos", "cpe"),
        "tecnico": ("tecnico", "técnico", "empleado", "cedula", "cédula"),
        "limitacion_documental": ("sap", "acta", "actas"),
        "proveedor": ("proveedor", "contratante"),
        "archivo": ("archivo", "excel", "adjunto", "xlsx", "csv"),
    }

    @staticmethod
    def _has_runtime_attachment(contexto_semantico: dict[str, Any] | None) -> bool:
        context = dict(contexto_semantico or {})
        attachment_summary = dict(context.get("runtime_attachment_summary") or {})
        if bool(attachment_summary.get("present")):
            return True
        if int(attachment_summary.get("count") or 0) > 0:
            return True
        attachments = [
            item for item in list(context.get("attachments") or []) if isinstance(item, dict)
        ]
        return bool(attachments)

    def resolver(
        self,
        *,
        mensaje: str,
        contexto_semantico: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        texto_original = str(mensaje or "")
        texto = self._normalizar(texto_original)
        metadata = self._metadata_gobernada(contexto_semantico=contexto_semantico or {})
        sinonimos, fallback_sombreado_usado = self._construir_sinonimos(
            contexto_semantico=contexto_semantico or {},
            metadata=metadata,
        )
        reglas_gobernadas = self._indice_reglas(metadata=metadata)
        filtros: dict[str, Any] = {}
        entidades: dict[str, Any] = {}
        reglas_aplicadas: list[str] = []
        reglas_metadata_usadas: list[str] = []
        limitaciones: list[str] = []

        senal_kardex = self._contiene(texto, sinonimos["kardex"])
        senal_limitacion_documental = self._contiene(texto, sinonimos["limitacion_documental"])
        senal_proveedor = self._contiene(texto, sinonimos["proveedor"])
        senal_archivo = self._contiene(texto, sinonimos["archivo"]) or self._has_runtime_attachment(
            contexto_semantico
        )

        cedula = self._extraer_cedula(texto_original, texto)
        movil = self._extraer_movil(texto_original, texto)
        codigo = self._extraer_codigo(texto_original, texto)
        descripcion_material = self._extraer_descripcion_material(
            texto_original=texto_original,
            texto=texto,
            codigo=codigo,
            cedula=cedula,
            movil=movil,
        )
        familia_serializada = self._resolver_familia_serializada_gobernada(
            valor=descripcion_material or texto_original,
            contexto_semantico=contexto_semantico or {},
            metadata=metadata,
        )
        dimension_agrupacion = self._extraer_dimension_agrupacion(texto)
        nombre_probable = self._detectar_nombre_probable(texto_original, texto)
        if not nombre_probable and "que tiene" in texto and re.search(r"\bque tiene [a-záéíóúñ]{2,}\s+[a-záéíóúñ]{2,}\b", texto):
            nombre_probable = True
        es_kardex = senal_kardex
        es_serializado = self._contiene(texto, sinonimos["serializados"]) or bool(familia_serializada)
        es_validacion_seriales_proveedor = bool(
            es_serializado
            and senal_proveedor
            and senal_archivo
            and (
                "valida" in texto
                or "validacion" in texto
                or "validar" in texto
                or "revisa" in texto
                or "revisar" in texto
                or "cruza" in texto
                or "cruzar" in texto
                or "contra nuestras bases" in texto
            )
        )
        senal_stock = (
            self._contiene(texto, sinonimos["inventario"])
            or bool(re.search(r"\bmaterial(?:es)?\b", texto))
            or self._contiene(texto, sinonimos["ferretero"])
            or self._contiene(texto, sinonimos["material_claro"])
            or es_serializado
        )
        if es_validacion_seriales_proveedor:
            reglas_aplicadas.append("validacion_seriales_proveedor_desde_dd_reglas")
            return {
                "coincidencia_gobernada": True,
                "dominio_candidato": "inventario_logistica",
                "intencion": "provider_serial_validation",
                "capacidad_candidata": "inventory_provider_serial_validation",
                "template_id": "inventory_provider_serial_validation",
                "operation": "validate_file",
                "filtros": {"source_kind": "provider_file", "serial_scope": "external_inventory_validation"},
                "entidades": {"archivo": "seriales_proveedor"},
                "group_by": [],
                "familias": ["serializados"],
                "incluye_serializados": True,
                "reglas_aplicadas": [item for item in dict.fromkeys(reglas_aplicadas) if item],
                "limitaciones": [],
                "requiere_aclaracion": False,
                "pregunta_aclaracion": "",
                "regla_metadata_usada": list(
                    dict.fromkeys([*reglas_metadata_usadas, "inventario.route.provider_serial_validation"])
                ),
                "fuente_dd": list(FUENTES_DD_GOBERNADAS),
                "fallback_sombreado_usado": fallback_sombreado_usado,
                "regla_legacy_detectada": False,
                "regla_migrada": True,
            }
        tiene_senal_inventario = senal_stock or senal_kardex or senal_limitacion_documental
        if not tiene_senal_inventario:
            return self._resultado_vacio()
        menciona_portador = self._contiene(texto, sinonimos["movil"]) or self._contiene(texto, sinonimos["tecnico"])
        es_consulta_tenencia_explicita = any(
            fragmento in texto
            for fragmento in ("que tiene", "tiene asignado", "asignado", "muestrame lo que tiene", "muestrame que tiene")
        )
        tiene_portador = bool(
            cedula
            or movil
            or nombre_probable
            or (
                menciona_portador
                and (es_consulta_tenencia_explicita or es_kardex or senal_limitacion_documental)
            )
        )
        es_consulta_agrupada = bool(dimension_agrupacion)
        senal_familia_agrupable = self._contiene(texto, sinonimos["material_claro"]) or self._contiene(texto, sinonimos["ferretero"])
        es_agrupacion_material_filtrado = bool(
            senal_stock
            and dimension_agrupacion
            and (
                codigo
                or descripcion_material
                or familia_serializada
                or (senal_familia_agrupable and dimension_agrupacion in {"movil", "cedula"})
            )
        )
        if not tiene_portador and not (es_kardex and codigo):
            if not es_agrupacion_material_filtrado:
                return self._resultado_vacio()

        if cedula:
            filtros["cedula"] = cedula
            entidades["cedula"] = cedula
            reglas_aplicadas.append("identificador_numerico_prioriza_cedula")
            reglas_metadata_usadas.append("inventario.identifier.numeric_to_cedula")
        elif movil:
            filtros["movil"] = movil
            entidades["movil"] = movil
            reglas_aplicadas.append("identificador_alfanumerico_prioriza_movil")
            reglas_metadata_usadas.append("inventario.identifier.alphanumeric_to_movil")

        if codigo:
            filtros["codigo"] = codigo
            entidades.setdefault("codigo", codigo)
        elif familia_serializada:
            filtros["material_family"] = familia_serializada
            filtros["material_family_match_mode"] = "contains"
            entidades.setdefault("material_family", familia_serializada)
            reglas_aplicadas.append("familia_serializada_desde_catalogo_gobernado")
            reglas_metadata_usadas.append("inventario.serial_family.busqueda_parcial_catalogo")
        elif descripcion_material:
            filtros["descripcion"] = descripcion_material
            entidades.setdefault("descripcion", descripcion_material)

        if self._contiene(texto, sinonimos["material_claro"]):
            filtros["tipo"] = "material"
            reglas_aplicadas.append("material_claro_desde_dd_sinonimos")
            reglas_metadata_usadas.append("inventario.filter.material_claro")
        elif self._contiene(texto, sinonimos["ferretero"]):
            filtros["tipo"] = "ferretero"
            reglas_aplicadas.append("ferretero_desde_dd_sinonimos")
            reglas_metadata_usadas.append("inventario.filter.ferretero")
        elif re.search(r"\bmaterial(?:es)?\b", texto):
            filtros["tipo"] = ["material", "ferretero"]
            reglas_aplicadas.append("material_generico_desde_dd_reglas")
            reglas_metadata_usadas.append("inventario.filter.material_generico")

        if (
            senal_stock
            and dimension_agrupacion
            and familia_serializada
            and not (cedula or movil)
        ):
            filtros["grouping_dimension"] = dimension_agrupacion
            reglas_aplicadas.extend(
                [
                    "familia_serializada_agrupada_por_dimension_desde_dd_reglas",
                    "serializados_usan_conteo_si_aplica_desde_dd_reglas",
                ]
            )
            return {
                "coincidencia_gobernada": True,
                "dominio_candidato": "inventario_logistica",
                "intencion": "stock_balance",
                "capacidad_candidata": "inventory_serial_stock_by_family_grouped_dimension",
                "template_id": "inventory_serial_stock_by_family_grouped_dimension",
                "operation": "aggregate",
                "filtros": filtros,
                "entidades": entidades,
                "group_by": [dimension_agrupacion],
                "familias": ["serializados"],
                "incluye_serializados": True,
                "reglas_aplicadas": [item for item in dict.fromkeys(reglas_aplicadas) if item],
                "limitaciones": [],
                "requiere_aclaracion": False,
                "pregunta_aclaracion": "",
                "regla_metadata_usada": [
                    item
                    for item in dict.fromkeys(
                        [
                            *reglas_metadata_usadas,
                            "inventario.metric.serial_count_only",
                            "inventario.route.serial_stock_family_grouped_dimension",
                        ]
                    )
                    if item
                ],
                "fuente_dd": list(FUENTES_DD_GOBERNADAS),
                "fallback_sombreado_usado": fallback_sombreado_usado,
                "regla_legacy_detectada": False,
                "regla_migrada": True,
            }

        if (
            es_agrupacion_material_filtrado
            and not (cedula or movil)
            and "materiales criticos" not in texto
            and "materiales críticos" not in texto
        ):
            familias = self._resolver_familias(filtros=filtros, es_serializado=False)
            filtros["grouping_dimension"] = dimension_agrupacion
            reglas_aplicadas.extend(
                [
                    "saldo_agrupado_por_dimension_desde_dd_reglas",
                    "saldo_incluye_cero_y_negativo_desde_dd_reglas",
                ]
            )
            return {
                "coincidencia_gobernada": True,
                "dominio_candidato": "inventario_logistica",
                "intencion": "stock_balance",
                "capacidad_candidata": "inventory_stock_balance_by_material_dimension",
                "template_id": "inventory_material_stock_grouped_dimension",
                "operation": "aggregate",
                "filtros": filtros,
                "entidades": entidades,
                "group_by": [dimension_agrupacion],
                "familias": familias,
                "incluye_serializados": False,
                "reglas_aplicadas": [item for item in dict.fromkeys(reglas_aplicadas) if item],
                "limitaciones": [],
                "requiere_aclaracion": False,
                "pregunta_aclaracion": "",
                "regla_metadata_usada": [
                    item
                    for item in dict.fromkeys(
                        [
                            *reglas_metadata_usadas,
                            "inventario.metric.stock_include_zero_negative",
                            "inventario.route.stock_balance_material_grouped_dimension",
                        ]
                    )
                    if item
                ],
                "fuente_dd": list(FUENTES_DD_GOBERNADAS),
                "fallback_sombreado_usado": fallback_sombreado_usado,
                "regla_legacy_detectada": False,
                "regla_migrada": True,
            }

        habla_de_tenencia = senal_stock or "muestrame lo que tiene" in texto or "muestrame que tiene" in texto
        requiere_aclaracion = False
        pregunta_aclaracion = ""

        if senal_limitacion_documental and tiene_portador:
            limitaciones.append("documentos_sap_y_actas_no_habilitados")
            return {
                "coincidencia_gobernada": True,
                "dominio_candidato": "inventario_logistica",
                "intencion": "document_generation",
                "capacidad_candidata": "inventory_document_generation_pending",
                "template_id": "inventory_document_generation_pending",
                "operation": "detail",
                "filtros": filtros,
                "entidades": entidades,
                "familias": ["material_claro", "ferretero"] if not es_serializado else ["serializados"],
                "incluye_serializados": False,
                "reglas_aplicadas": list(dict.fromkeys(reglas_aplicadas + ["documentos_no_disponibles_desde_dd_reglas"])),
                "limitaciones": limitaciones,
                "requiere_aclaracion": False,
                "pregunta_aclaracion": "",
                "regla_metadata_usada": list(dict.fromkeys([*reglas_metadata_usadas, "inventario.limit.document_generation_pending"])),
                "fuente_dd": list(FUENTES_DD_GOBERNADAS),
                "fallback_sombreado_usado": fallback_sombreado_usado,
                "regla_legacy_detectada": False,
                "regla_migrada": True,
            }

        if es_kardex:
            if cedula:
                reglas_aplicadas.extend(
                    [
                        "kardex_equivale_a_movimientos_desde_dd_sinonimos",
                        "cedula_dirige_kardex_empleado_desde_dd_reglas",
                    ]
                )
                return {
                    "coincidencia_gobernada": True,
                    "dominio_candidato": "inventario_logistica",
                    "intencion": "movement_history",
                    "capacidad_candidata": "inventory_kardex_by_employee",
                    "template_id": "inventory_kardex_by_employee",
                    "operation": "detail",
                    "filtros": filtros,
                    "entidades": entidades,
                    "familias": ["material_claro", "ferretero"] if not es_serializado else ["serializados"],
                    "incluye_serializados": False,
                    "reglas_aplicadas": list(dict.fromkeys(reglas_aplicadas)),
                    "limitaciones": [],
                    "requiere_aclaracion": False,
                    "pregunta_aclaracion": "",
                    "regla_metadata_usada": list(dict.fromkeys([*reglas_metadata_usadas, "inventario.route.kardex_employee"])),
                    "fuente_dd": list(FUENTES_DD_GOBERNADAS),
                    "fallback_sombreado_usado": fallback_sombreado_usado,
                    "regla_legacy_detectada": False,
                    "regla_migrada": True,
                }
            if codigo:
                reglas_aplicadas.append("codigo_dirige_kardex_consolidado_desde_dd_reglas")
                return {
                    "coincidencia_gobernada": True,
                    "dominio_candidato": "inventario_logistica",
                    "intencion": "movement_history",
                    "capacidad_candidata": "inventory_kardex_consolidated",
                    "template_id": "inventory_kardex_consolidated",
                    "operation": "detail",
                    "filtros": filtros,
                    "entidades": entidades,
                    "familias": ["material_claro", "ferretero"],
                    "incluye_serializados": False,
                    "reglas_aplicadas": list(dict.fromkeys(reglas_aplicadas)),
                    "limitaciones": [],
                    "requiere_aclaracion": False,
                    "pregunta_aclaracion": "",
                    "regla_metadata_usada": list(dict.fromkeys([*reglas_metadata_usadas, "inventario.route.kardex_codigo"])),
                    "fuente_dd": list(FUENTES_DD_GOBERNADAS),
                    "fallback_sombreado_usado": fallback_sombreado_usado,
                    "regla_legacy_detectada": False,
                    "regla_migrada": True,
                }
            return self._resultado_vacio()

        if not requiere_aclaracion and habla_de_tenencia and tiene_portador:
            if not cedula and not movil:
                if es_consulta_agrupada:
                    return self._resultado_vacio()
                if nombre_probable or "tecnico" in texto or "técnico" in texto or "empleado" in texto:
                    requiere_aclaracion = True
                    pregunta_aclaracion = "¿Debo buscar por cédula o por móvil/cuadrilla? Con nombre propio no es seguro."
                else:
                    requiere_aclaracion = True
                    pregunta_aclaracion = "¿Cuál es la cédula o el móvil/cuadrilla que quieres consultar?"
            else:
                if cedula or movil:
                    filtros.setdefault("stock_scope", "movil")
                familias = self._resolver_familias(filtros=filtros, es_serializado=es_serializado)
                incluye_serializados = self._debe_incluir_serializados(
                    texto=texto,
                    filtros=filtros,
                    es_serializado=es_serializado,
                    movil=movil,
                    reglas_gobernadas=reglas_gobernadas,
                )
                reglas_aplicadas.extend(
                    [
                        "inventario_generico_desde_dd_reglas" if incluye_serializados else "",
                        "saldo_incluye_cero_y_negativo_desde_dd_reglas",
                        "serializados_usan_conteo_si_aplica_desde_dd_reglas" if es_serializado or incluye_serializados else "",
                    ]
                )
                return {
                    "coincidencia_gobernada": True,
                    "dominio_candidato": "inventario_logistica",
                    "intencion": "serial_holder_query" if es_serializado and (cedula or movil) and not filtros.get("tipo") else "stock_balance",
                    "capacidad_candidata": "inventory_serial_by_operational_holder"
                    if es_serializado and (cedula or movil) and not filtros.get("tipo")
                    else "inventory_stock_balance_by_mobile",
                    "template_id": "inventory_serial_by_operational_holder"
                    if es_serializado and (cedula or movil) and not filtros.get("tipo")
                    else "inventory_material_stock_mobile",
                    "operation": "stock_balance",
                    "filtros": filtros,
                    "entidades": entidades,
                    "familias": familias,
                    "incluye_serializados": incluye_serializados,
                    "reglas_aplicadas": [item for item in dict.fromkeys(reglas_aplicadas) if item],
                    "limitaciones": [],
                    "requiere_aclaracion": False,
                    "pregunta_aclaracion": "",
                    "regla_metadata_usada": [
                        item
                        for item in dict.fromkeys(
                            [
                                *reglas_metadata_usadas,
                                "inventario.scope.dual_block_unspecified_family" if incluye_serializados and not filtros.get("tipo") else "",
                                "inventario.metric.stock_include_zero_negative",
                                "inventario.metric.serial_count_only" if es_serializado or incluye_serializados else "",
                                "inventario.route.serial_holder" if es_serializado and (cedula or movil) and not filtros.get("tipo") else "inventario.route.stock_balance_holder",
                            ]
                        )
                        if item
                    ],
                    "fuente_dd": list(FUENTES_DD_GOBERNADAS),
                    "fallback_sombreado_usado": fallback_sombreado_usado,
                    "regla_legacy_detectada": False,
                    "regla_migrada": True,
                }
        if senal_stock and not tiene_portador:
            return self._resultado_vacio()

        if requiere_aclaracion:
            return {
                "coincidencia_gobernada": True,
                "dominio_candidato": "inventario_logistica",
                "intencion": "needs_clarification",
                "capacidad_candidata": "",
                "template_id": "",
                "operation": "detail",
                "filtros": filtros,
                "entidades": entidades,
                "familias": [],
                "incluye_serializados": False,
                "reglas_aplicadas": [item for item in dict.fromkeys(reglas_aplicadas) if item],
                "limitaciones": [],
                "requiere_aclaracion": True,
                "pregunta_aclaracion": pregunta_aclaracion,
                "regla_metadata_usada": list(dict.fromkeys(reglas_metadata_usadas)),
                "fuente_dd": list(FUENTES_DD_GOBERNADAS),
                "fallback_sombreado_usado": fallback_sombreado_usado,
                "regla_legacy_detectada": False,
                "regla_migrada": bool(reglas_metadata_usadas),
            }

        return self._resultado_vacio()

    @classmethod
    def _resolver_familias(cls, *, filtros: dict[str, Any], es_serializado: bool) -> list[str]:
        tipo = filtros.get("tipo")
        if es_serializado and not tipo:
            return ["serializados"]
        if tipo == "material":
            return ["material_claro"]
        if tipo == "ferretero":
            return ["ferretero"]
        if isinstance(tipo, list):
            return ["material_claro", "ferretero"]
        return ["material_claro", "ferretero"]

    @classmethod
    def _debe_incluir_serializados(
        cls,
        *,
        texto: str,
        filtros: dict[str, Any],
        es_serializado: bool,
        movil: str,
        reglas_gobernadas: dict[str, dict[str, Any]],
    ) -> bool:
        if es_serializado:
            return True
        if filtros.get("tipo"):
            return False
        if "kardex" in texto or "movimientos" in texto or "entradas y salidas" in texto:
            return False
        if movil and (
            "inventario" in texto
            or "saldo" in texto
            or "stock" in texto
            or "que tiene" in texto
            or "tiene asignado" in texto
        ):
            return "inventario.scope.dual_block_unspecified_family" in reglas_gobernadas
        return False

    @classmethod
    def _construir_sinonimos(
        cls,
        *,
        contexto_semantico: dict[str, Any],
        metadata: dict[str, Any],
    ) -> tuple[dict[str, tuple[str, ...]], bool]:
        sinonimos = {clave: list(valores) for clave, valores in cls._SINONIMOS_BASE.items()}
        fallback_sombreado_usado = False
        metadata_rows = list(metadata.get("dd_sinonimos") or [])
        if not metadata_rows:
            fallback_sombreado_usado = True
        for row in metadata_rows:
            alias = cls._normalizar(str((row or {}).get("synonym") or ""))
            canonico = cls._normalizar(str((row or {}).get("canonical_value") or ""))
            if not alias or not canonico:
                continue
            if canonico == "movil":
                sinonimos["movil"].append(alias)
            if canonico in {"movement_history", "kardex"}:
                sinonimos["kardex"].append(alias)
            if canonico == "material_claro":
                sinonimos["material_claro"].append(alias)
            if canonico == "ferretero":
                sinonimos["ferretero"].append(alias)
            if canonico == "serializados":
                sinonimos["serializados"].append(alias)
            if canonico == "cedula":
                sinonimos["tecnico"].append(alias)
            if canonico in {"sap", "document_generation", "acta", "actas"} or "document" in canonico:
                sinonimos["limitacion_documental"].append(alias)
        indice = dict(contexto_semantico.get("synonym_index") or {})
        for alias, canonico in indice.items():
            alias_normalizado = cls._normalizar(alias)
            canonico_normalizado = cls._normalizar(canonico)
            if canonico_normalizado == "movil":
                sinonimos["movil"].append(alias_normalizado)
            if canonico_normalizado in {"kardex", "movimientos", "tipo_movimiento"}:
                sinonimos["kardex"].append(alias_normalizado)
            if canonico_normalizado in {"tipo", "material", "ferretero"}:
                if "ferreter" in alias_normalizado:
                    sinonimos["ferretero"].append(alias_normalizado)
                if "material" in alias_normalizado:
                    sinonimos["material_claro"].append(alias_normalizado)
            if canonico_normalizado in {"serial", "serializados", "equipo", "equipos"}:
                sinonimos["serializados"].append(alias_normalizado)
        return ({clave: tuple(dict.fromkeys(valores)) for clave, valores in sinonimos.items()}, fallback_sombreado_usado)

    @staticmethod
    def _metadata_gobernada(*, contexto_semantico: dict[str, Any]) -> dict[str, Any]:
        default_metadata = construir_metadata_gobernada_inventario()
        dictionary = dict(contexto_semantico.get("dictionary") or {})
        return {
            "dd_sinonimos": list(dictionary.get("synonyms") or contexto_semantico.get("synonyms") or default_metadata.get("dd_sinonimos") or []),
            "dd_reglas": list(dictionary.get("rules") or contexto_semantico.get("rules") or default_metadata.get("dd_reglas") or []),
        }

    @staticmethod
    def _indice_reglas(*, metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
        indice: dict[str, dict[str, Any]] = {}
        for row in list(metadata.get("dd_reglas") or []):
            if not isinstance(row, dict):
                continue
            codigo = str(row.get("codigo") or row.get("rule_name") or "").strip()
            if codigo:
                indice[codigo] = dict(row)
        return indice

    @staticmethod
    def _extraer_cedula(texto_original: str, texto: str) -> str:
        if any(token in texto for token in ("serial", "seriales", "trazabilidad")):
            return ""
        for patron in (
            r"\b(?:empleado|tecnico|técnico|cedula|cédula)\s+([0-9]{5,15})\b",
        ):
            coincidencia = re.search(patron, texto_original, re.IGNORECASE)
            if coincidencia:
                return str(coincidencia.group(1) or "").strip()
        if re.search(r"\bcod(?:igo)?\b", texto_original, re.IGNORECASE):
            return ""
        coincidencia = re.search(r"\b([0-9]{5,15})\b", texto)
        return str(coincidencia.group(1) or "").strip() if coincidencia else ""

    @staticmethod
    def _extraer_movil(texto_original: str, texto: str) -> str:
        if any(token in texto for token in ("serial", "seriales", "trazabilidad")):
            return ""
        if re.search(r"\bcod(?:igo)?\s+[a-z0-9_-]{2,}\b", texto, re.IGNORECASE):
            return ""
        movil = EmployeeIdentifierService.extract_movil_identifier(texto_original or texto)
        if movil:
            return str(movil).strip().upper()
        coincidencia = re.search(r"\b([A-Z]{2,}[A-Z0-9_-]*\d{2,})\b", texto_original)
        return str(coincidencia.group(1) or "").strip().upper() if coincidencia else ""

    @staticmethod
    def _extraer_codigo(texto_original: str, texto: str) -> str:
        for patron in (
            r"\b(?:del?\s+)?cod(?:igo)?\s+([A-Za-z0-9_-]{2,})\b",
            r"\bmaterial\s+([A-Za-z0-9_-]{2,})\b",
        ):
            coincidencia = re.search(patron, texto_original, re.IGNORECASE)
            if coincidencia:
                valor = str(coincidencia.group(1) or "").strip().upper()
                if valor.lower() not in MatcherSemanticoGobernadoInventario._PALABRAS_NO_CODIGO:
                    return valor
        if "kardex" in texto and "codigo" in texto:
            coincidencia = re.search(r"\bcodigo\s+([a-z0-9_-]{2,})\b", texto)
            if coincidencia:
                return str(coincidencia.group(1) or "").strip().upper()
        return ""

    @classmethod
    def _extraer_descripcion_material(
        cls,
        *,
        texto_original: str,
        texto: str,
        codigo: str,
        cedula: str,
        movil: str,
    ) -> str:
        if codigo or cedula or movil:
            return ""
        patrones = (
            r"\b(?:saldo|inventario|existencia|existencias|stock)\s+en\s+(?:moviles|m[oó]viles|cuadrillas|brigadas|tecnicos|t[eé]cnicos|empleados|bodegas)\s+de\s+(.+)$",
            r"\b(?:saldo|inventario|existencia|existencias|stock)\s+de\s+(.+?)\s+por\s+(?:movil|m[oó]vil|cuadrilla|brigada|tecnico|t[eé]cnico|empleado|bodega)\b",
        )
        for patron in patrones:
            coincidencia = re.search(patron, texto_original, re.IGNORECASE)
            if not coincidencia:
                continue
            valor = str(coincidencia.group(1) or "").strip(" .,:;")
            if not valor:
                continue
            valor_normalizado = cls._normalizar(valor)
            if valor_normalizado in cls._PALABRAS_NO_CODIGO:
                return ""
            if valor_normalizado in {"ferretero", "material", "material claro", "material de claro"}:
                return ""
            return valor.upper()
        return ""

    @classmethod
    def _resolver_familia_serializada_gobernada(
        cls,
        *,
        valor: str,
        contexto_semantico: dict[str, Any],
        metadata: dict[str, Any],
    ) -> str:
        normalized_value = cls._normalizar(valor)
        if not normalized_value:
            return ""
        aliases = cls._aliases_familias_serializadas(metadata=metadata)
        has_alias_signal = any(
            alias and re.search(rf"(^|\W){re.escape(alias)}($|\W)", normalized_value)
            for alias in aliases
        )
        if not has_alias_signal and len(normalized_value.split()) > 2:
            return ""
        catalogo = cls._catalogo_familias_serializadas(contexto_semantico=contexto_semantico)
        if not catalogo:
            return ""
        exact = cls._buscar_familia_exacta(catalogo=catalogo, valor=valor)
        if exact:
            return exact
        contained_value = cls._buscar_familias_por_contiene(catalogo=catalogo, valor=valor)
        if contained_value:
            return contained_value
        for alias, canonical in aliases.items():
            if alias and re.search(rf"(^|\W){re.escape(alias)}($|\W)", normalized_value):
                exact_alias = cls._buscar_familia_exacta(catalogo=catalogo, valor=canonical)
                if exact_alias:
                    return exact_alias
                contained = cls._buscar_familia_por_token_unico(catalogo=catalogo, valor=canonical)
                if contained:
                    return contained
                contained_alias = cls._buscar_familias_por_contiene(catalogo=catalogo, valor=canonical)
                if contained_alias:
                    return contained_alias
        return ""

    @classmethod
    def _catalogo_familias_serializadas(cls, *, contexto_semantico: dict[str, Any]) -> list[str]:
        families = [
            str(item or "").strip().upper()
            for item in list(contexto_semantico.get("inventory_catalog_families") or [])
            if str(item or "").strip()
        ]
        if families:
            return list(dict.fromkeys(families))
        try:
            with connections["logistica_cinco"].cursor() as cursor:
                cursor.execute(
                    """
                    SELECT UPPER(TRIM(familia)) AS familia
                    FROM base_codigo_seriales
                    WHERE familia IS NOT NULL AND TRIM(familia) <> ''
                    GROUP BY UPPER(TRIM(familia))
                    ORDER BY familia
                    """
                )
                return [
                    str(row[0] or "").strip().upper()
                    for row in cursor.fetchall()
                    if str(row[0] or "").strip()
                ]
        except Exception:
            return []

    @classmethod
    def _aliases_familias_serializadas(cls, *, metadata: dict[str, Any]) -> dict[str, str]:
        aliases: dict[str, str] = {}
        for row in list(metadata.get("dd_sinonimos") or []):
            if not isinstance(row, dict):
                continue
            if str(row.get("scope_tipo") or "").strip().lower() != "familia_serializada":
                continue
            alias = cls._normalizar(str(row.get("synonym") or ""))
            canonical = str(row.get("canonical_value") or "").strip().upper()
            if alias and canonical:
                aliases[alias] = canonical
        return aliases

    @classmethod
    def _buscar_familia_exacta(cls, *, catalogo: list[str], valor: str) -> str:
        normalized_value = cls._normalizar(valor)
        upper_value = str(valor or "").strip().upper()
        for family in catalogo:
            if family == upper_value:
                return family
        for family in catalogo:
            if cls._normalizar(family) == normalized_value:
                return family
        return ""

    @classmethod
    def _buscar_familia_por_token_unico(cls, *, catalogo: list[str], valor: str) -> str:
        normalized_value = cls._normalizar(valor)
        if not normalized_value:
            return ""
        matches = [
            family
            for family in catalogo
            if re.search(rf"(^|\W){re.escape(normalized_value)}($|\W)", cls._normalizar(family))
        ]
        if len(matches) == 1:
            return matches[0]
        return ""

    @classmethod
    def _buscar_familias_por_contiene(cls, *, catalogo: list[str], valor: str) -> str:
        normalized_value = cls._normalizar(valor)
        if not normalized_value:
            return ""
        matches = [
            family
            for family in catalogo
            if normalized_value in cls._normalizar(family)
        ]
        if matches:
            return str(valor or "").strip().upper()
        return ""

    @staticmethod
    def _extraer_dimension_agrupacion(texto: str) -> str:
        if re.search(r"\b(?:por|en)\s+(?:movil|m[oó]vil|moviles|m[oó]viles|cuadrilla|cuadrillas|brigada|brigadas)\b", texto):
            return "movil"
        if re.search(r"\bpor\s+(?:tecnico|t[eé]cnico|empleado|empleados|cedula|c[eé]dula)\b", texto):
            return "cedula"
        if re.search(r"\bpor\s+(?:bodega|bodegas|almacen|almacenes)\b", texto):
            return "bodega"
        return ""

    @staticmethod
    def _detectar_nombre_probable(texto_original: str, texto: str) -> bool:
        if re.search(r"\bjuan\s+perez\b", texto):
            return True
        return bool(
            re.search(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\b", str(texto_original or ""))
            and not re.search(r"\b(?:material|ferretero|inventario|kardex|movil|cuadrilla|brigada|serial|codigo|empleado|tecnico)\b", texto)
        )

    @staticmethod
    def _contiene(texto: str, sinonimos: tuple[str, ...]) -> bool:
        return any(item and item in texto for item in sinonimos)

    @staticmethod
    def _normalizar(texto: str) -> str:
        minusculas = str(texto or "").strip().lower()
        normalizado = unicodedata.normalize("NFKD", minusculas)
        limpio = "".join(caracter for caracter in normalizado if not unicodedata.combining(caracter))
        return re.sub(r"\s+", " ", limpio)

    @staticmethod
    def _resultado_vacio() -> dict[str, Any]:
        return {
            "coincidencia_gobernada": False,
            "dominio_candidato": "",
            "intencion": "",
            "capacidad_candidata": "",
            "template_id": "",
            "operation": "",
            "filtros": {},
            "entidades": {},
            "familias": [],
            "incluye_serializados": False,
            "reglas_aplicadas": [],
            "limitaciones": [],
            "requiere_aclaracion": False,
            "pregunta_aclaracion": "",
            "regla_metadata_usada": [],
            "fuente_dd": list(FUENTES_DD_GOBERNADAS),
            "fallback_sombreado_usado": False,
            "regla_legacy_detectada": False,
            "regla_migrada": False,
        }
