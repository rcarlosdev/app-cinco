from __future__ import annotations

import re
import unicodedata
from typing import Any

from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    ColumnSemanticResolution,
)
from apps.ia_dev.services.employee_identifier_service import EmployeeIdentifierService


class ColumnSemanticResolver:
    """
    Resolver de metadata funcional de columnas usando dd_campos y perfil semantico.
    """

    _COUNT_METRIC_TOKENS = ("cantidad", "cuantos", "cuantas", "total", "numero")
    _DATE_HINTS = ("fecha", "periodo", "dia", "mes", "year", "ano")
    _IDENTIFIER_HINTS = ("cedula", "identificacion", "documento", "id_empleado", "codigo_sap", "movil")
    @staticmethod
    def _normalize_text(value: str | None) -> str:
        lowered = str(value or "").strip().lower()
        normalized = unicodedata.normalize("NFKD", lowered)
        return "".join(ch for ch in normalized if not unicodedata.combining(ch))

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        text = str(value or "").strip().lower()
        return text in {"1", "true", "yes", "on", "si"}

    @staticmethod
    def _parse_allowed_values(value: Any) -> list[str]:
        if isinstance(value, list):
            parsed = [str(item or "").strip().upper() for item in value if str(item or "").strip()]
            return sorted(dict.fromkeys(parsed))
        text = str(value or "").strip()
        if not text:
            return []
        for separator in ("|", ";"):
            text = text.replace(separator, ",")
        parsed = [item.strip().upper() for item in text.split(",") if item.strip()]
        return sorted(dict.fromkeys(parsed))

    @staticmethod
    def _parse_semantic_tags(text: Any) -> dict[str, str]:
        payload: dict[str, str] = {}
        for key, value in re.findall(r"\[([a-zA-Z0-9_]+)=(.*?)\](?=\[|$)", str(text or "")):
            clean_key = str(key or "").strip().lower()
            clean_value = str(value or "").strip()
            if clean_key and clean_value:
                payload[clean_key] = clean_value
        return payload

    @classmethod
    def _parse_list_tag(cls, value: Any) -> list[str]:
        raw = str(value or "").strip()
        if not raw:
            return []
        normalized = raw
        for separator in (";", ","):
            normalized = normalized.replace(separator, "|")
        return [
            str(item or "").strip()
            for item in normalized.split("|")
            if str(item or "").strip()
        ]

    def build_column_profiles(
        self,
        *,
        runtime_columns: list[dict[str, Any]] | None = None,
        dictionary_fields: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        profiles: list[dict[str, Any]] = []

        for row in list(runtime_columns or []):
            if not isinstance(row, dict):
                continue
            logical = self._normalize_text(row.get("nombre_columna_logico"))
            column_name = self._normalize_text(row.get("column_name"))
            if not logical and not column_name:
                continue
            semantic_tags = self._parse_semantic_tags(
                row.get("definicion_negocio") or row.get("definition") or row.get("descripcion")
            )
            profiles.append(
                {
                    "logical_name": logical or column_name,
                    "column_name": column_name,
                    "table_name": self._normalize_text(row.get("table_name")),
                    "supports_filter": self._to_bool(row.get("es_filtro")),
                    "supports_group_by": self._to_bool(row.get("es_group_by")),
                    "supports_metric": self._to_bool(row.get("es_metrica")),
                    "supports_dimension": self._to_bool(row.get("es_group_by")),
                    "is_date": any(token in logical for token in self._DATE_HINTS),
                    "is_identifier": any(token in logical for token in self._IDENTIFIER_HINTS),
                    "is_chart_dimension": self._to_bool(row.get("es_group_by")),
                    "is_chart_measure": self._to_bool(row.get("es_metrica")),
                    "allowed_values": [],
                    "allowed_operators": self._parse_list_tag(semantic_tags.get("allowed_missing_operators")),
                    "supports_missingness": self._to_bool(semantic_tags.get("supports_missingness")),
                    "empty_equivalent_values": self._parse_list_tag(semantic_tags.get("empty_equivalent_values")),
                    "json_path": str(semantic_tags.get("json_path") or "").strip(),
                    "privacy": str(semantic_tags.get("privacy") or "").strip().lower(),
                    "missing_fallback_fields": self._parse_list_tag(semantic_tags.get("missing_fallback_fields")),
                    "confidence": 0.75,
                }
            )

        for row in list(dictionary_fields or []):
            if not isinstance(row, dict):
                continue
            logical = self._normalize_text(row.get("campo_logico"))
            column_name = self._normalize_text(row.get("column_name"))
            if not logical and not column_name:
                continue
            allowed_values = self._parse_allowed_values(row.get("valores_permitidos"))
            semantic_tags = self._parse_semantic_tags(
                row.get("definicion_negocio") or row.get("definition") or row.get("descripcion")
            )
            supports_filter = self._to_bool(row.get("es_filtro")) or bool(allowed_values)
            supports_group_by = self._to_bool(row.get("es_group_by"))
            supports_metric = self._to_bool(row.get("es_metrica"))
            supports_dimension = self._to_bool(row.get("es_dimension")) or supports_group_by
            is_date = self._to_bool(row.get("is_date")) or any(
                token in logical for token in self._DATE_HINTS
            )
            is_identifier = self._to_bool(row.get("is_identifier")) or (
                any(token in logical for token in self._IDENTIFIER_HINTS)
                or column_name in {"cedula", "identificacion"}
            )
            supports_missingness = self._to_bool(semantic_tags.get("supports_missingness")) or (
                "missing_value_alert" in semantic_tags
                or "empty_value" in semantic_tags
                or bool(semantic_tags.get("json_path"))
            )
            profile = {
                "logical_name": logical or column_name,
                "column_name": column_name,
                "table_name": self._normalize_text(row.get("table_name")),
                "supports_filter": supports_filter,
                "supports_group_by": supports_group_by,
                "supports_metric": supports_metric,
                "supports_dimension": supports_dimension,
                "is_date": is_date,
                "is_identifier": is_identifier,
                "is_chart_dimension": self._to_bool(row.get("is_chart_dimension")) or supports_group_by,
                "is_chart_measure": self._to_bool(row.get("is_chart_measure")) or supports_metric,
                "allowed_values": allowed_values,
                "allowed_operators": self._parse_list_tag(
                    row.get("allowed_operators") or semantic_tags.get("allowed_missing_operators")
                ),
                "supports_missingness": supports_missingness,
                "empty_equivalent_values": self._parse_list_tag(semantic_tags.get("empty_equivalent_values")),
                "json_path": str(semantic_tags.get("json_path") or "").strip(),
                "privacy": str(semantic_tags.get("privacy") or "").strip().lower(),
                "missing_fallback_fields": self._parse_list_tag(semantic_tags.get("missing_fallback_fields")),
                "confidence": 0.92,
            }
            profiles.append(profile)

        deduped: dict[tuple[str, str], dict[str, Any]] = {}
        for profile in profiles:
            key = (
                str(profile.get("logical_name") or ""),
                str(profile.get("column_name") or ""),
            )
            current = deduped.get(key)
            if current is None:
                deduped[key] = profile
                continue

            current_confidence = float(current.get("confidence") or 0.0)
            incoming_confidence = float(profile.get("confidence") or 0.0)
            base = dict(current if current_confidence >= incoming_confidence else profile)
            allowed_values = sorted(
                dict.fromkeys(
                    [
                        *self._parse_allowed_values(current.get("allowed_values")),
                        *self._parse_allowed_values(profile.get("allowed_values")),
                    ]
                )
            )
            base["table_name"] = str(base.get("table_name") or current.get("table_name") or profile.get("table_name") or "")
            base["supports_filter"] = bool(current.get("supports_filter")) or bool(profile.get("supports_filter"))
            base["supports_group_by"] = bool(current.get("supports_group_by")) or bool(profile.get("supports_group_by"))
            base["supports_metric"] = bool(current.get("supports_metric")) or bool(profile.get("supports_metric"))
            base["supports_dimension"] = bool(current.get("supports_dimension")) or bool(profile.get("supports_dimension"))
            base["is_date"] = bool(current.get("is_date")) or bool(profile.get("is_date"))
            base["is_identifier"] = bool(current.get("is_identifier")) or bool(profile.get("is_identifier"))
            base["is_chart_dimension"] = bool(current.get("is_chart_dimension")) or bool(profile.get("is_chart_dimension"))
            base["is_chart_measure"] = bool(current.get("is_chart_measure")) or bool(profile.get("is_chart_measure"))
            base["allowed_values"] = allowed_values
            base["allowed_operators"] = list(
                dict.fromkeys(
                    [
                        *self._parse_list_tag(current.get("allowed_operators")),
                        *self._parse_list_tag(profile.get("allowed_operators")),
                    ]
                )
            )
            base["supports_missingness"] = bool(current.get("supports_missingness")) or bool(profile.get("supports_missingness"))
            base["empty_equivalent_values"] = list(
                dict.fromkeys(
                    [
                        *self._parse_list_tag(current.get("empty_equivalent_values")),
                        *self._parse_list_tag(profile.get("empty_equivalent_values")),
                    ]
                )
            )
            base["json_path"] = str(base.get("json_path") or current.get("json_path") or profile.get("json_path") or "")
            base["privacy"] = str(base.get("privacy") or current.get("privacy") or profile.get("privacy") or "")
            base["missing_fallback_fields"] = list(
                dict.fromkeys(
                    [
                        *self._parse_list_tag(current.get("missing_fallback_fields")),
                        *self._parse_list_tag(profile.get("missing_fallback_fields")),
                    ]
                )
            )
            base["confidence"] = max(current_confidence, incoming_confidence)
            deduped[key] = base

        return list(deduped.values())

    @staticmethod
    def _match_profile(
        *,
        term: str,
        profiles: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        clean = str(term or "").strip().lower()
        if not clean:
            return None
        for row in profiles:
            logical = str(row.get("logical_name") or "").strip().lower()
            column = str(row.get("column_name") or "").strip().lower()
            if clean in {logical, column}:
                return row
        return None

    def resolve_identifier_filter(
        self,
        *,
        message: str,
        semantic_context: dict[str, Any],
    ) -> tuple[str, str] | None:
        normalized_message = self._normalize_text(message)
        profiles = list(semantic_context.get("column_profiles") or [])
        match = re.search(r"\b\d{6,13}\b", normalized_message)
        if match:
            value = "".join(ch for ch in match.group(0) if ch.isdigit())
            profile = self._find_profile(
                profiles=profiles,
                accepted_names={"cedula", "cedula_empleado", "identificacion", "documento"},
                require_identifier=False,
            )
            if profile is not None:
                logical = str(profile.get("logical_name") or profile.get("column_name") or "cedula").strip().lower()
                return logical, value
            for row in profiles:
                if not isinstance(row, dict):
                    continue
                if not self._to_bool(row.get("is_identifier")):
                    continue
                logical = str(row.get("logical_name") or "").strip().lower() or str(row.get("column_name") or "").strip().lower()
                if logical:
                    return logical, value
            return "cedula", value

        movil_profile = self._find_profile(
            profiles=profiles,
            accepted_names={"movil"},
            require_identifier=False,
        )
        if movil_profile is None:
            return None

        value = EmployeeIdentifierService.extract_movil_identifier(message or normalized_message)
        if value:
            logical = str(movil_profile.get("logical_name") or movil_profile.get("column_name") or "movil").strip().lower()
            return logical, value
        return None

    def resolve_schema_value_filters(
        self,
        *,
        message: str,
        semantic_context: dict[str, Any],
    ) -> tuple[dict[str, str], list[ColumnSemanticResolution]]:
        """
        Resolve explicit column/value references using the semantic schema.

        This keeps the LLM/planner away from guessing physical fields: values are
        only bound to columns that exist in column_profiles or approved aliases.
        """

        normalized_message = self._normalize_text(message)
        profiles = [
            dict(row)
            for row in list((semantic_context or {}).get("column_profiles") or [])
            if isinstance(row, dict)
        ]
        term_index = self._schema_term_index(
            profiles=profiles,
            semantic_context=semantic_context,
        )
        filters: dict[str, str] = {}
        resolutions: list[ColumnSemanticResolution] = []

        for term, profile in sorted(term_index.items(), key=lambda item: len(item[0]), reverse=True):
            if not term or len(term) < 2:
                continue
            if self._term_already_captured_as_value(term=term, filters=filters):
                continue
            value = self._extract_value_after_term(
                normalized_message=normalized_message,
                term=term,
                profile=profile,
            )
            if not value:
                continue
            logical_name = str(profile.get("logical_name") or profile.get("column_name") or "").strip().lower()
            if not logical_name or logical_name in filters:
                continue
            filters[logical_name] = value
            resolutions.append(self._profile_resolution(requested_term=term, profile=profile))

        # Strong unlabelled identifiers are still schema-based: they bind only if
        # an identifier-like profile is available, then fall back to safe names.
        if not any(key in filters for key in ("cedula", "cedula_empleado", "identificacion", "documento")):
            match = re.search(r"\b\d{6,13}\b", normalized_message)
            if match:
                profile = self._find_profile(
                    profiles=profiles,
                    accepted_names={"cedula", "cedula_empleado", "identificacion", "documento"},
                    require_identifier=False,
                )
                logical = str((profile or {}).get("logical_name") or (profile or {}).get("column_name") or "cedula").strip().lower()
                filters[logical] = "".join(ch for ch in match.group(0) if ch.isdigit())
                if profile:
                    resolutions.append(self._profile_resolution(requested_term=logical, profile=profile))

        if not any(key in filters for key in ("movil",)):
            movil = EmployeeIdentifierService.extract_movil_identifier(message or normalized_message)
            if movil:
                profile = self._find_profile(
                    profiles=profiles,
                    accepted_names={"movil"},
                    require_identifier=False,
                )
                logical = str((profile or {}).get("logical_name") or (profile or {}).get("column_name") or "movil").strip().lower()
                filters[logical] = movil
                if profile:
                    resolutions.append(self._profile_resolution(requested_term=logical, profile=profile))

        return filters, resolutions

    def _term_already_captured_as_value(self, *, term: str, filters: dict[str, str]) -> bool:
        clean_term = self._normalize_text(term)
        if not clean_term:
            return False
        return any(
            bool(re.search(rf"\b{re.escape(clean_term)}\b", self._normalize_text(value)))
            for value in dict(filters or {}).values()
            if str(value or "").strip()
        )

    def _schema_term_index(
        self,
        *,
        profiles: list[dict[str, Any]],
        semantic_context: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        index: dict[str, dict[str, Any]] = {}
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            if not (
                self._to_bool(profile.get("supports_filter"))
                or self._to_bool(profile.get("is_identifier"))
                or str(profile.get("logical_name") or "").strip().lower() in {"movil", "area", "cargo", "carpeta", "supervisor", "tipo_labor"}
            ):
                continue
            for raw_term in (
                profile.get("logical_name"),
                profile.get("column_name"),
                str(profile.get("logical_name") or "").replace("_", " "),
                str(profile.get("column_name") or "").replace("_", " "),
            ):
                term = self._normalize_text(raw_term)
                if term:
                    index.setdefault(term, profile)

        aliases = dict((semantic_context or {}).get("aliases") or {})
        aliases.update(dict((semantic_context or {}).get("synonym_index") or {}))
        for alias, canonical in aliases.items():
            alias_term = self._normalize_text(alias)
            canonical_term = self._normalize_text(canonical)
            if not alias_term or not canonical_term:
                continue
            profile = self._match_profile(term=canonical_term, profiles=profiles)
            if profile is not None:
                index.setdefault(alias_term, profile)
        return index

    def _extract_value_after_term(
        self,
        *,
        normalized_message: str,
        term: str,
        profile: dict[str, Any],
    ) -> str:
        logical = self._normalize_text(profile.get("logical_name") or profile.get("column_name"))
        pattern = rf"\b{re.escape(term)}\b\s*(?::|=|es|de|del|la|el|con)?\s+([a-z0-9_ .-]{{2,80}})"
        match = re.search(pattern, normalized_message)
        if not match:
            return ""
        raw = str(match.group(1) or "").strip()
        for separator in (" y ", " con ", " por ", ",", ".", ";", "?"):
            if separator in raw:
                raw = raw.split(separator, 1)[0].strip()
        if re.match(r"^(y|e|o)\b", raw):
            return ""
        if logical in {"cedula", "cedula_empleado", "identificacion", "documento"}:
            digit_match = re.search(r"\b\d{6,13}\b", raw)
            return digit_match.group(0) if digit_match else ""
        if logical == "movil":
            token = EmployeeIdentifierService.normalize_movil_value(raw.split()[0] if raw.split() else raw)
            return token if EmployeeIdentifierService.is_movil_candidate(token) else ""
        if logical == "codigo_sap":
            token = raw.split()[0] if raw.split() else raw
            return token.upper()[:40]
        return raw[:80].strip()

    def _profile_resolution(
        self,
        *,
        requested_term: str,
        profile: dict[str, Any],
    ) -> ColumnSemanticResolution:
        return ColumnSemanticResolution(
            requested_term=str(requested_term or ""),
            canonical_term=str(profile.get("logical_name") or profile.get("column_name") or "").strip().lower(),
            table_name=str(profile.get("table_name") or ""),
            column_name=str(profile.get("column_name") or ""),
            supports_filter=self._to_bool(profile.get("supports_filter")),
            supports_group_by=self._to_bool(profile.get("supports_group_by")),
            supports_metric=self._to_bool(profile.get("supports_metric")),
            supports_dimension=self._to_bool(profile.get("supports_dimension")),
            is_date=self._to_bool(profile.get("is_date")),
            is_identifier=self._to_bool(profile.get("is_identifier")),
            is_chart_dimension=self._to_bool(profile.get("is_chart_dimension")),
            is_chart_measure=self._to_bool(profile.get("is_chart_measure")),
            allowed_values=self._parse_allowed_values(profile.get("allowed_values")),
            confidence=float(profile.get("confidence") or 0.0),
        )

    @staticmethod
    def _has_letters_and_digits(value: str) -> bool:
        text = str(value or "").strip().lower()
        return bool(re.search(r"[a-z]", text) and re.search(r"\d", text))

    def _find_profile(
        self,
        *,
        profiles: list[dict[str, Any]],
        accepted_names: set[str],
        require_identifier: bool,
    ) -> dict[str, Any] | None:
        normalized_names = {self._normalize_text(item) for item in accepted_names if str(item or "").strip()}
        for row in profiles:
            if not isinstance(row, dict):
                continue
            if require_identifier and not self._to_bool(row.get("is_identifier")):
                continue
            logical = self._normalize_text(row.get("logical_name"))
            column = self._normalize_text(row.get("column_name"))
            if logical in normalized_names or column in normalized_names:
                return row
        return None

    def resolve_filters(
        self,
        *,
        filters: dict[str, Any],
        semantic_context: dict[str, Any],
        canonicalize_term,
        normalize_status_value,
    ) -> tuple[dict[str, Any], list[ColumnSemanticResolution]]:
        profiles = list(semantic_context.get("column_profiles") or [])
        resolved: dict[str, Any] = {}
        resolutions: list[ColumnSemanticResolution] = []

        for raw_key, raw_value in dict(filters or {}).items():
            requested = str(raw_key or "").strip()
            canonical_term = str(canonicalize_term(requested) or requested).strip().lower()
            profile = self._match_profile(term=canonical_term, profiles=profiles)
            if profile is None:
                resolved[canonical_term] = raw_value
                continue

            logical_name = str(profile.get("logical_name") or canonical_term).strip().lower()
            allowed_values = self._parse_allowed_values(profile.get("allowed_values"))
            value = raw_value
            if logical_name in {"estado", "estado_empleado"}:
                try:
                    value = normalize_status_value(
                        raw_value=raw_value,
                        allowed_values=allowed_values,
                    )
                except TypeError:
                    value = normalize_status_value(raw_value, allowed_values)
            resolved[logical_name] = value
            resolutions.append(
                ColumnSemanticResolution(
                    requested_term=requested,
                    canonical_term=logical_name,
                    table_name=str(profile.get("table_name") or ""),
                    column_name=str(profile.get("column_name") or ""),
                    supports_filter=self._to_bool(profile.get("supports_filter")),
                    supports_group_by=self._to_bool(profile.get("supports_group_by")),
                    supports_metric=self._to_bool(profile.get("supports_metric")),
                    supports_dimension=self._to_bool(profile.get("supports_dimension")),
                    is_date=self._to_bool(profile.get("is_date")),
                    is_identifier=self._to_bool(profile.get("is_identifier")),
                    is_chart_dimension=self._to_bool(profile.get("is_chart_dimension")),
                    is_chart_measure=self._to_bool(profile.get("is_chart_measure")),
                    allowed_values=allowed_values,
                    confidence=float(profile.get("confidence") or 0.0),
                )
            )
        return resolved, resolutions

    def resolve_group_by(
        self,
        *,
        requested_group_by: list[str],
        message: str,
        semantic_context: dict[str, Any],
        canonicalize_term,
    ) -> tuple[list[str], list[ColumnSemanticResolution]]:
        profiles = list(semantic_context.get("column_profiles") or [])
        values = [str(item or "").strip() for item in list(requested_group_by or []) if str(item or "").strip()]
        normalized_message = self._normalize_text(message)
        if not values:
            message_tokens = re.findall(r"\b(?:por)\s+([a-z0-9_]+)\b", normalized_message)
            values.extend(message_tokens)
            for profile in profiles:
                if not isinstance(profile, dict):
                    continue
                if not (
                    self._to_bool(profile.get("supports_group_by"))
                    or self._to_bool(profile.get("supports_dimension"))
                ):
                    continue
                candidates = [
                    str(profile.get("logical_name") or "").strip().lower(),
                    str(profile.get("column_name") or "").strip().lower(),
                ]
                for candidate in candidates:
                    if not candidate:
                        continue
                    if re.search(rf"\b{re.escape(candidate)}\b", normalized_message):
                        values.append(candidate)
                        continue
                    # Soporte de plural simple: area->areas, cargo->cargos, supervisor->supervisores.
                    if re.search(rf"\b{re.escape(candidate)}(?:s|es)\b", normalized_message):
                        values.append(candidate)

        values = list(dict.fromkeys(values))

        resolved: list[str] = []
        resolutions: list[ColumnSemanticResolution] = []
        for token in values:
            canonical_term = str(canonicalize_term(token) or token).strip().lower()
            profile = self._match_profile(term=canonical_term, profiles=profiles)
            if profile is None:
                continue
            if not (self._to_bool(profile.get("supports_group_by")) or self._to_bool(profile.get("supports_dimension"))):
                continue
            logical_name = str(profile.get("logical_name") or canonical_term).strip().lower()
            if logical_name in resolved:
                continue
            resolved.append(logical_name)
            resolutions.append(
                ColumnSemanticResolution(
                    requested_term=token,
                    canonical_term=logical_name,
                    table_name=str(profile.get("table_name") or ""),
                    column_name=str(profile.get("column_name") or ""),
                    supports_filter=self._to_bool(profile.get("supports_filter")),
                    supports_group_by=self._to_bool(profile.get("supports_group_by")),
                    supports_metric=self._to_bool(profile.get("supports_metric")),
                    supports_dimension=self._to_bool(profile.get("supports_dimension")),
                    is_date=self._to_bool(profile.get("is_date")),
                    is_identifier=self._to_bool(profile.get("is_identifier")),
                    is_chart_dimension=self._to_bool(profile.get("is_chart_dimension")),
                    is_chart_measure=self._to_bool(profile.get("is_chart_measure")),
                    allowed_values=self._parse_allowed_values(profile.get("allowed_values")),
                    confidence=float(profile.get("confidence") or 0.0),
                )
            )
        return resolved, resolutions

    def resolve_metrics(
        self,
        *,
        requested_metrics: list[str],
        operation: str,
        message: str,
        semantic_context: dict[str, Any],
        canonicalize_term,
    ) -> tuple[list[str], list[ColumnSemanticResolution]]:
        profiles = list(semantic_context.get("column_profiles") or [])
        normalized_message = self._normalize_text(message)
        requested = [str(item or "").strip() for item in list(requested_metrics or []) if str(item or "").strip()]
        if not requested and (
            str(operation or "").strip().lower() == "count"
            or any(token in normalized_message for token in self._COUNT_METRIC_TOKENS)
        ):
            requested = ["count"]

        resolved: list[str] = []
        resolutions: list[ColumnSemanticResolution] = []
        for token in requested:
            canonical_term = str(canonicalize_term(token) or token).strip().lower()
            if canonical_term in {"count", "conteo"}:
                if "count" not in resolved:
                    resolved.append("count")
                continue
            profile = self._match_profile(term=canonical_term, profiles=profiles)
            if profile is None:
                continue
            if not self._to_bool(profile.get("supports_metric")):
                continue
            logical_name = str(profile.get("logical_name") or canonical_term).strip().lower()
            if logical_name in resolved:
                continue
            resolved.append(logical_name)
            resolutions.append(
                ColumnSemanticResolution(
                    requested_term=token,
                    canonical_term=logical_name,
                    table_name=str(profile.get("table_name") or ""),
                    column_name=str(profile.get("column_name") or ""),
                    supports_filter=self._to_bool(profile.get("supports_filter")),
                    supports_group_by=self._to_bool(profile.get("supports_group_by")),
                    supports_metric=self._to_bool(profile.get("supports_metric")),
                    supports_dimension=self._to_bool(profile.get("supports_dimension")),
                    is_date=self._to_bool(profile.get("is_date")),
                    is_identifier=self._to_bool(profile.get("is_identifier")),
                    is_chart_dimension=self._to_bool(profile.get("is_chart_dimension")),
                    is_chart_measure=self._to_bool(profile.get("is_chart_measure")),
                    allowed_values=self._parse_allowed_values(profile.get("allowed_values")),
                    confidence=float(profile.get("confidence") or 0.0),
                )
            )
        return resolved or ["count"], resolutions
