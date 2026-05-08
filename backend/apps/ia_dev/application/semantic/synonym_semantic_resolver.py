from __future__ import annotations

import re
import unicodedata
from typing import Any


class SynonymSemanticResolver:
    """
    Resolver de sinonimos semanticos usando dd_sinonimos y aliases de campos.
    """
    _LOCAL_EQUIVALENCES = {
        "labor": "tipo_labor",
        "labores": "tipo_labor",
        "tipo laboral": "tipo_labor",
        "clase de labor": "tipo_labor",
        "categoria laboral": "tipo_labor",
        "personal por tipo": "tipo_labor",
        "tipo_labor": "tipo_labor",
    }

    @classmethod
    def normalize_text(cls, value: str | None) -> str:
        lowered = str(value or "").strip().lower()
        normalized = unicodedata.normalize("NFKD", lowered)
        return "".join(ch for ch in normalized if not unicodedata.combining(ch))

    def build_index(
        self,
        *,
        dictionary_synonyms: list[dict[str, Any]] | None = None,
        dictionary_fields: list[dict[str, Any]] | None = None,
        runtime_columns: list[dict[str, Any]] | None = None,
    ) -> dict[str, str]:
        index: dict[str, str] = {}

        for row in list(dictionary_synonyms or []):
            if not isinstance(row, dict):
                continue
            term = self.normalize_text(row.get("termino"))
            synonym = self.normalize_text(row.get("sinonimo"))
            if term:
                index.setdefault(term, term)
            if term and synonym:
                index[synonym] = term

        for row in list(dictionary_fields or []):
            if not isinstance(row, dict):
                continue
            logical = self.normalize_text(row.get("campo_logico"))
            column = self.normalize_text(row.get("column_name"))
            if logical:
                index.setdefault(logical, logical)
            if logical and column:
                index.setdefault(column, logical)

        for row in list(runtime_columns or []):
            if not isinstance(row, dict):
                continue
            logical = self.normalize_text(row.get("nombre_columna_logico"))
            column = self.normalize_text(row.get("column_name"))
            if logical:
                index.setdefault(logical, logical)
            if logical and column:
                index.setdefault(column, logical)

        for alias, canonical in self._LOCAL_EQUIVALENCES.items():
            normalized_alias = self.normalize_text(alias)
            normalized_canonical = self.normalize_text(canonical)
            if normalized_alias and normalized_canonical:
                index.setdefault(normalized_alias, normalized_canonical)
                index.setdefault(normalized_canonical, normalized_canonical)

        return index

    def canonicalize(self, *, term: str | None, synonym_index: dict[str, str] | None) -> str:
        clean = self.normalize_text(term)
        if not clean:
            return ""
        lookup = dict(synonym_index or {})
        return str(lookup.get(clean) or clean)

    def canonicalize_tokens_from_message(
        self,
        *,
        message: str,
        synonym_index: dict[str, str] | None = None,
    ) -> list[str]:
        clean = self.normalize_text(message)
        if not clean:
            return []

        tokens = re.findall(r"[a-z0-9_]{2,}", clean)
        canonical: list[str] = []
        for token in tokens:
            mapped = self.canonicalize(term=token, synonym_index=synonym_index)
            if mapped and mapped not in canonical:
                canonical.append(mapped)
        return canonical
