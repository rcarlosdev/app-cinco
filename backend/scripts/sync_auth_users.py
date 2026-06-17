import csv
import os
import argparse
import sys
from pathlib import Path

import django


def setup_django() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()


def normalize_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def is_active_from_estado(estado: str) -> bool:
    return normalize_text(estado).upper() == "ACTIVO"


def get_total_rows() -> int:
    from django.db import connections
    with connections["azul"].cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM cinco_base_de_personal")
        row = cursor.fetchone()
        return row[0] if row else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Carga usuarios en auth_user desde la tabla cinco_base_de_personal en la DB 'azul'."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula la carga sin escribir en la base de datos.",
    )
    parser.add_argument(
        "--output",
        default=str(Path("tmp") / "auth_user_import.csv"),
        help="Ruta del CSV donde se guardan usuarios nuevos y su password temporal.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Cantidad de registros por lote.",
    )
    return parser


def fetch_source_rows(batch_size: int):
    from django.db import connections

    query = (
        "SELECT id, cedula, email_personal, nombre, apellido, estado "
        "FROM cinco_base_de_personal"
    )
    with connections["azul"].cursor() as cursor:
        cursor.execute(query)
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            for row in rows:
                yield row


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    setup_django()

    from django.contrib.auth.models import User

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_count = get_total_rows()
    print(f"Total de registros a procesar: {total_count}")

    created_count = 0
    updated_count = 0
    skipped_count = 0
    processed_count = 0

    csv_file = None
    csv_writer = None
    if args.output:
        csv_file = output_path.open("w", newline="", encoding="utf-8")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["username", "temp_password", "email"])  # nosec B608

    try:
        for source_id, cedula, email, nombre, apellido, estado in fetch_source_rows(args.batch_size):
            processed_count += 1
            if processed_count % 10 == 0 or processed_count == total_count:
                percent = (processed_count / total_count) * 100 if total_count > 0 else 0
                print(
                    f"\rProgreso: {processed_count}/{total_count} ({percent:.1f}%) | "
                    f"Creados: {created_count} | Saltados: {skipped_count}",
                    end="",
                    flush=True,
                )

            username = normalize_text(cedula)
            if not username:
                skipped_count += 1
                continue

            first_name = normalize_text(nombre)
            last_name = normalize_text(apellido)
            email_value = normalize_text(email)
            is_active = is_active_from_estado(estado)

            existing_by_id = User.objects.filter(pk=source_id).first()
            existing_by_username = User.objects.filter(username=username).first()
            already_synced = (existing_by_id is not None) or (existing_by_username is not None)

            if args.dry_run:
                if already_synced:
                    skipped_count += 1
                else:
                    created_count += 1
                    if csv_writer:
                        csv_writer.writerow([username, "DRY_RUN", email_value])
                continue

            if already_synced:
                skipped_count += 1
                continue

            user = User(
                id=source_id,
                username=username,
                email=email_value,
                first_name=first_name,
                last_name=last_name,
                is_active=is_active,
                is_staff=False,
                is_superuser=False,
            )
            temp_password = username
            user.set_password(temp_password)
            user.save(force_insert=True)
            created_count += 1
            if csv_writer:
                csv_writer.writerow([username, temp_password, email_value])
    finally:
        if csv_file:
            csv_file.close()

    print()  # Salto de línea para limpiar la barra de progreso
    print(
        "Import finalizado. "
        f"Creados: {created_count}. "
        f"Actualizados: {updated_count}. "
        f"Saltados: {skipped_count}."
    )
    if args.output:
        print(f"CSV generado: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
