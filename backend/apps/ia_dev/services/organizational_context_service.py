from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any

from django.db import connections


@dataclass(frozen=True, slots=True)
class OrganizationalParameter:
    tipo: str
    condicion: str
    valor: str
    tipo_area: str
    datos: dict[str, Any]


class OrganizationalContextService:
    """
    Resolver liviano para catalogos operativos de infraestructura_parametros.
    Mantiene las consultas de negocio alineadas con areas, carpetas y centros de costo reales.
    """

    def __init__(
        self,
        *,
        db_alias: str = "default",
        table: str = "bd_c3nc4s1s.infraestructura_parametros",
    ):
        self.db_alias = db_alias
        self.table = table

    def resolve_reference(self, *, message: str) -> dict[str, Any]:
        reference = self._extract_reference(message)
        if not reference:
            return {"resolved": False, "reference": "", "filters": {}, "candidates": []}
        return self.resolve_value(value=reference, message=message)

    def resolve_value(self, *, value: str, message: str = "") -> dict[str, Any]:
        raw = str(value or "").strip(" .,:;?¿!¡")
        if not raw:
            return {"resolved": False, "reference": "", "filters": {}, "candidates": []}
        normalized_message = self._normalize(message)
        wants_carpeta = "carpeta" in normalized_message
        wants_area = "area" in normalized_message

        area_matches = self._match(raw, self.active_areas(), fields=("condicion", "valor"))
        carpeta_matches = self._match(raw, self.active_carpetas(), fields=("valor",))
        candidates = [
            *[{**item, "filter": "area"} for item in area_matches],
            *[{**item, "filter": "carpeta"} for item in carpeta_matches],
        ]
        if not candidates:
            return {"resolved": False, "reference": raw, "filters": {}, "candidates": []}

        selected: dict[str, Any] | None = None
        if wants_carpeta and carpeta_matches:
            selected = {**carpeta_matches[0], "filter": "carpeta"}
        elif wants_area and area_matches:
            selected = {**area_matches[0], "filter": "area"}
        elif area_matches and area_matches[0]["score"] >= 0.98:
            selected = {**area_matches[0], "filter": "area"}
        elif carpeta_matches and carpeta_matches[0]["score"] >= 0.98:
            selected = {**carpeta_matches[0], "filter": "carpeta"}
        else:
            selected = max(candidates, key=lambda item: float(item.get("score") or 0.0))

        parameter = selected["parameter"]
        filter_key = str(selected["filter"])
        filter_value = parameter.condicion if filter_key == "area" else parameter.valor
        return {
            "resolved": True,
            "reference": raw,
            "filters": {filter_key: filter_value},
            "selected": {
                "tipo": parameter.tipo,
                "condicion": parameter.condicion,
                "valor": parameter.valor,
                "filter": filter_key,
                "score": float(selected.get("score") or 0.0),
                "matched_field": str(selected.get("matched_field") or ""),
            },
            "candidates": [
                {
                    "tipo": item["parameter"].tipo,
                    "condicion": item["parameter"].condicion,
                    "valor": item["parameter"].valor,
                    "filter": item.get("filter"),
                    "score": float(item.get("score") or 0.0),
                    "matched_field": item.get("matched_field"),
                }
                for item in candidates[:5]
            ],
        }

    def cost_center_for(self, *, area: Any = "", carpeta: Any = "") -> str:
        area_text = str(area or "").strip()
        carpeta_text = str(carpeta or "").strip()
        if carpeta_text:
            match = self.resolve_value(value=carpeta_text, message="carpeta")
            selected = dict(match.get("selected") or {})
            if str(selected.get("tipo") or "").upper() == "CARPETA":
                parameter = self._find_parameter(tipo="CARPETA", condicion=selected.get("condicion"), valor=selected.get("valor"))
                cc = self._format_cost_center((parameter.datos if parameter else {}) or {})
                if cc:
                    return cc
        if area_text:
            match = self.resolve_value(value=area_text, message="area")
            selected = dict(match.get("selected") or {})
            if str(selected.get("tipo") or "").upper() == "AREA":
                parameter = self._find_parameter(tipo="AREA", condicion=selected.get("condicion"), valor=selected.get("valor"))
                cc = self._format_cost_center((parameter.datos if parameter else {}) or {})
                if cc:
                    return cc
        return "N/D"

    @classmethod
    def _format_cost_center(cls, datos: dict[str, Any]) -> str:
        if not isinstance(datos, dict):
            return ""
        if "centro_costo" in datos:
            cc = str(datos.get("centro_costo") or "").strip()
            sub = datos.get("subcentro_costo")
            return cls._format_cc_pair(cc=cc, sub=sub)
        centers = datos.get("centros_costo")
        if isinstance(centers, list) and centers:
            labels = []
            for item in centers:
                if not isinstance(item, dict):
                    continue
                label = cls._format_cc_pair(cc=str(item.get("centro_costo") or ""), sub=item.get("subcentro_costo"))
                if label:
                    labels.append(label)
            return ", ".join(dict.fromkeys(labels))
        return ""

    @staticmethod
    def _format_cc_pair(*, cc: str, sub: Any) -> str:
        clean_cc = str(cc or "").strip()
        if not clean_cc:
            return ""
        if isinstance(sub, list):
            sub_values = [str(item).strip() for item in sub if str(item).strip()]
            return ", ".join(f"{clean_cc}-{item}" for item in sub_values) if sub_values else clean_cc
        clean_sub = str(sub or "").strip()
        return f"{clean_cc}-{clean_sub}" if clean_sub else clean_cc

    def _find_parameter(self, *, tipo: Any, condicion: Any, valor: Any) -> OrganizationalParameter | None:
        wanted_tipo = str(tipo or "").strip().upper()
        wanted_condicion = self._normalize(condicion)
        wanted_valor = self._normalize(valor)
        source = self.active_areas() if wanted_tipo == "AREA" else self.active_carpetas()
        for item in source:
            if self._normalize(item.condicion) == wanted_condicion and self._normalize(item.valor) == wanted_valor:
                return item
        return None

    @staticmethod
    def _extract_reference(message: str) -> str:
        text = str(message or "").strip()
        normalized = OrganizationalContextService._normalize(text)
        stop_words = (
            " ultimo mes",
            " ultimos",
            " este mes",
            " mes anterior",
            " mes pasado",
            " hoy",
            " ayer",
            " por area",
            " por carpeta",
            " por centro",
            " por cc",
        )
        patterns = (
            r"\b(?:de|del|para|en)\s+(.+)$",
            r"\b(?:area|carpeta)\s+(.+)$",
        )
        for pattern in patterns:
            for match in re.finditer(pattern, normalized):
                value = str(match.group(1) or "").strip()
                value = re.sub(r"^(?:ultimo mes|ultimos \d+ dias|este mes|mes anterior|mes pasado)\s+de\s+", "", value).strip()
                if " de " in value:
                    value = value.rsplit(" de ", 1)[-1].strip()
                for stop in stop_words:
                    pos = value.find(stop.strip())
                    if pos > 0:
                        value = value[:pos].strip()
                if value and value not in {"personal", "empleados", "ausentismos", "rotacion"}:
                    return value
        return ""

    def _match(
        self,
        value: str,
        parameters: list[OrganizationalParameter],
        *,
        fields: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        target = self._normalize(value)
        matches: list[dict[str, Any]] = []
        if not target:
            return []
        for parameter in parameters:
            for field in fields:
                candidate = self._normalize(getattr(parameter, field))
                if not candidate:
                    continue
                score = 0.0
                if target == candidate:
                    score = 1.0
                elif target in candidate or candidate in target:
                    score = 0.92
                else:
                    score = SequenceMatcher(None, target, candidate).ratio()
                if score >= 0.72:
                    matches.append(
                        {
                            "parameter": parameter,
                            "score": round(float(score), 4),
                            "matched_field": field,
                        }
                    )
        matches.sort(key=lambda item: (-float(item.get("score") or 0.0), str(item["parameter"].valor)))
        return matches

    def active_areas(self) -> list[OrganizationalParameter]:
        return self._load_active(kind="AREA", db_alias=self.db_alias, table=self.table)

    def active_carpetas(self) -> list[OrganizationalParameter]:
        return self._load_active(kind="CARPETA", db_alias=self.db_alias, table=self.table)

    @staticmethod
    @lru_cache(maxsize=8)
    def _load_active(*, kind: str, db_alias: str, table: str) -> list[OrganizationalParameter]:
        query = f"""
            SELECT tipo, condicion, valor, COALESCE(tipo_area, ''), datos
            FROM {table}
            WHERE tipo = %s AND estado = 'ACTIVO'
        """
        with connections[db_alias].cursor() as cursor:
            cursor.execute(query, [kind])
            rows = cursor.fetchall()
        params: list[OrganizationalParameter] = []
        for tipo, condicion, valor, tipo_area, datos in rows:
            params.append(
                OrganizationalParameter(
                    tipo=str(tipo or "").strip(),
                    condicion=str(condicion or "").strip(),
                    valor=str(valor or "").strip(),
                    tipo_area=str(tipo_area or "").strip(),
                    datos=OrganizationalContextService._parse_json(datos),
                )
            )
        return params

    @staticmethod
    def _parse_json(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        raw = str(value or "").strip()
        if not raw or raw.lower() == "null":
            return {}
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _normalize(value: Any) -> str:
        lowered = str(value or "").strip().lower()
        normalized = unicodedata.normalize("NFKD", lowered)
        clean = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        clean = clean.replace(" and ", " & ")
        clean = re.sub(r"\s+", " ", clean)
        return clean.strip(" .,:;?¿!¡")
