from __future__ import annotations

import re
import unicodedata
from typing import Any


class EmployeeIdentifierService:
    _DETAIL_PREFIX_RE = r"(?:info|informacion|detalle|datos|ficha)"
    _MOVIL_TOKEN_RE = r"(?:[a-z][a-z0-9_-]*(?:[\s_-]*\d+[a-z0-9_-]*)+|\d{3,5})"
    _MOVIL_PATTERNS = (
        re.compile(
            rf"\bmovil(?:\s+(?:de|del|la|el))?\s+(?P<token>{_MOVIL_TOKEN_RE})\b",
            re.IGNORECASE,
        ),
        re.compile(
            rf"\b{_DETAIL_PREFIX_RE}\s+de\s+(?P<token>{_MOVIL_TOKEN_RE})\b",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^\s*{_DETAIL_PREFIX_RE}\s+(?P<token>{_MOVIL_TOKEN_RE})\s*$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^\s*(?P<token>{_MOVIL_TOKEN_RE})\s*$",
            re.IGNORECASE,
        ),
    )

    @staticmethod
    def _normalize_text(value: Any) -> str:
        lowered = str(value or "").strip().lower()
        normalized = unicodedata.normalize("NFKD", lowered)
        return "".join(ch for ch in normalized if not unicodedata.combining(ch))

    @classmethod
    def normalize_movil_value(cls, value: Any) -> str:
        normalized = cls._normalize_text(value)
        compact = re.sub(r"[\s_-]+", "", normalized)
        return compact.upper()

    @classmethod
    def is_movil_candidate(cls, value: Any) -> bool:
        normalized = cls.normalize_movil_value(value)
        if not normalized:
            return False
        if re.fullmatch(r"\d{3,5}", normalized):
            return True
        return bool(re.search(r"[A-Z]", normalized) and re.search(r"\d", normalized))

    @classmethod
    def extract_movil_identifier(cls, message: Any) -> str:
        normalized = cls._normalize_text(message)
        if not normalized:
            return ""
        for pattern in cls._MOVIL_PATTERNS:
            match = pattern.search(normalized)
            if not match:
                continue
            token = cls.normalize_movil_value(match.group("token"))
            if token and cls.is_movil_candidate(token):
                return token
        return ""

    @classmethod
    def has_movil_identifier(cls, message: Any) -> bool:
        return bool(cls.extract_movil_identifier(message))

    @staticmethod
    def prune_redundant_search_filter(filters: dict[str, Any] | None) -> dict[str, Any]:
        cleaned = dict(filters or {})
        has_identifier = any(
            str(cleaned.get(key) or "").strip()
            for key in ("cedula", "movil", "codigo_sap")
        )
        if has_identifier:
            cleaned.pop("search", None)
        return cleaned
