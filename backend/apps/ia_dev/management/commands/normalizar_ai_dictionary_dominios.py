from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db import connections, transaction

from apps.ia_dev.services.dictionary_tool_service import DictionaryToolService


class Command(BaseCommand):
    help = "Normaliza dominios de ai_dictionary a EMPLEADOS y AUSENTISMOS, consolidando aliases legacy."

    CANONICOS = {
        "empleados": ("EMPLEADOS", "Empleados"),
        "ausentismo": ("AUSENTISMOS", "Ausentismos"),
    }

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra los cambios detectados sin escribir en la base de datos.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        service = DictionaryToolService()
        schema = service.base_schema
        db_alias = service.db_alias

        with connections[db_alias].cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, codigo, nombre, descripcion, activo
                FROM {schema}.dd_dominios
                ORDER BY id
                """
            )
            rows = cursor.fetchall()

        domain_rows = [
            {
                "id": int(row[0]),
                "codigo": str(row[1] or "").strip(),
                "nombre": str(row[2] or "").strip(),
                "descripcion": str(row[3] or "").strip(),
                "activo": int(row[4] or 0),
            }
            for row in rows
        ]

        canonical_ids: dict[str, int] = {}
        changes: list[str] = []

        for row in domain_rows:
            normalized = self._normalize_domain_key(row)
            if normalized in self.CANONICOS and int(row["activo"]) == 1 and normalized not in canonical_ids:
                canonical_ids[normalized] = int(row["id"])

        for row in domain_rows:
            normalized = self._normalize_domain_key(row)
            if normalized not in self.CANONICOS:
                continue

            canonical_code, canonical_name = self.CANONICOS[normalized]
            current_id = int(row["id"])
            target_id = int(canonical_ids.get(normalized) or current_id)
            if normalized not in canonical_ids:
                canonical_ids[normalized] = current_id
                target_id = current_id

            if target_id == current_id:
                if row["codigo"] != canonical_code or row["nombre"] != canonical_name or int(row["activo"]) != 1:
                    changes.append(
                        f"dd_dominios:{current_id} -> codigo={canonical_code}, nombre={canonical_name}, activo=1"
                    )
                    if not dry_run:
                        self._update_domain_row(
                            db_alias=db_alias,
                            schema=schema,
                            domain_id=current_id,
                            codigo=canonical_code,
                            nombre=canonical_name,
                        )
                continue

            changes.append(
                f"merge dd_dominios:{current_id} -> dd_dominios:{target_id} ({canonical_code})"
            )
            if not dry_run:
                self._merge_domain_row(
                    db_alias=db_alias,
                    schema=schema,
                    source_id=current_id,
                    target_id=target_id,
                    canonical_code=canonical_code,
                    canonical_name=canonical_name,
                )

        if not changes:
            self.stdout.write(self.style.SUCCESS("Sin cambios: ai_dictionary ya está normalizado."))
            return

        prefix = "[dry-run] " if dry_run else ""
        for item in changes:
            self.stdout.write(f"{prefix}{item}")
        if not dry_run:
            self.stdout.write(self.style.SUCCESS("Normalización de ai_dictionary completada."))

    @classmethod
    def _normalize_domain_key(cls, row: dict[str, Any]) -> str:
        normalized = " ".join(
            [
                str(row.get("codigo") or "").strip().lower(),
                str(row.get("nombre") or "").strip().lower(),
                str(row.get("descripcion") or "").strip().lower(),
            ]
        )
        if any(token in normalized for token in ("ausent", "asistenc", "attendance")):
            return "ausentismo"
        if any(token in normalized for token in ("emplead", "employee", "rrhh", "personal", "humano")):
            return "empleados"
        return ""

    @staticmethod
    def _update_domain_row(*, db_alias: str, schema: str, domain_id: int, codigo: str, nombre: str) -> None:
        with transaction.atomic(using=db_alias):
            with connections[db_alias].cursor() as cursor:
                cursor.execute(
                    f"""
                    UPDATE {schema}.dd_dominios
                    SET codigo = %s,
                        nombre = %s,
                        activo = 1
                    WHERE id = %s
                    """,
                    [codigo, nombre, int(domain_id)],
                )

    @staticmethod
    def _merge_domain_row(
        *,
        db_alias: str,
        schema: str,
        source_id: int,
        target_id: int,
        canonical_code: str,
        canonical_name: str,
    ) -> None:
        with transaction.atomic(using=db_alias):
            with connections[db_alias].cursor() as cursor:
                cursor.execute(
                    """
                    SELECT table_name, column_name
                    FROM information_schema.columns
                    WHERE table_schema = %s
                      AND column_name IN ('dominio_id', 'dominio_origen_id', 'dominio_destino_id')
                    ORDER BY table_name, column_name
                    """,
                    [schema],
                )
                refs = cursor.fetchall()
                for table_name, column_name in refs:
                    cursor.execute(
                        f"UPDATE {schema}.{table_name} SET {column_name} = %s WHERE {column_name} = %s",
                        [int(target_id), int(source_id)],
                    )

                cursor.execute(
                    f"""
                    UPDATE {schema}.dd_dominios
                    SET codigo = %s,
                        nombre = %s,
                        activo = 1
                    WHERE id = %s
                    """,
                    [canonical_code, canonical_name, int(target_id)],
                )
                cursor.execute(
                    f"""
                    UPDATE {schema}.dd_dominios
                    SET activo = 0
                    WHERE id = %s
                    """,
                    [int(source_id)],
                )
