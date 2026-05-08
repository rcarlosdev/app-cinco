from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.ia_dev.services.ai_dictionary_deduplication_service import (
    AIDictionaryDeduplicationService,
)


class Command(BaseCommand):
    help = "Diagnostica y aplica deduplicacion segura de metadata en ai_dictionary."

    def add_arguments(self, parser):
        parser.add_argument("--domain", type=str, default="ausentismo")
        parser.add_argument("--with-empleados", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--apply-safe", action="store_true")
        parser.add_argument("--as-json", action="store_true")

    def handle(self, *args, **options):
        domain = str(options.get("domain") or "ausentismo").strip().lower()
        with_empleados = bool(options.get("with_empleados"))
        service = AIDictionaryDeduplicationService()
        analysis = service.analyze(domain=domain, with_empleados=with_empleados)
        if bool(options.get("apply_safe")):
            analysis = service.apply_safe(
                analysis=analysis,
                domain=domain,
                with_empleados=with_empleados,
            )

        if bool(options.get("as_json")):
            self.stdout.write(json.dumps(analysis, ensure_ascii=False, indent=2))
            return

        self.stdout.write("IA dictionary deduplicate")
        self.stdout.write(
            "domains={domains} | dry_run={dry_run} | apply_safe={apply_safe}".format(
                domains=", ".join(list(analysis.get("domains") or [])),
                dry_run=bool(options.get("dry_run") or not options.get("apply_safe")),
                apply_safe=bool(options.get("apply_safe")),
            )
        )
        self.stdout.write(
            "legacy_duplicate_signals={count}".format(
                count=int(analysis.get("legacy_duplicate_signal_count") or 0)
            )
        )
        for key in (
            "total_duplicates",
            "auto_merge_candidates",
            "manual_review_required",
            "conflicts",
        ):
            self.stdout.write(f"{key}={int(analysis.get(key) or 0)}")
        breakdown = dict(analysis.get("duplicates_by_type") or {})
        self.stdout.write(f"duplicates_by_type={breakdown}")
        legacy_breakdown = dict(analysis.get("legacy_duplicate_signal_breakdown") or {})
        self.stdout.write(f"legacy_duplicate_signal_breakdown={legacy_breakdown}")

        self.stdout.write("duplicates:")
        duplicates = list(analysis.get("duplicates") or [])
        if not duplicates:
            self.stdout.write("  - none")
        for item in duplicates:
            canonical = dict(item.get("canonical_record") or {})
            duplicate = dict(item.get("duplicate_record") or {})
            self.stdout.write(
                "  - type={entity_type} | classification={classification} | canonical={canonical} | duplicate={duplicate} | auto_merge={auto_merge} | manual_review={manual_review} | reason={reason} | action={action}".format(
                    entity_type=item.get("entity_type"),
                    classification=item.get("classification"),
                    canonical=canonical,
                    duplicate=duplicate,
                    auto_merge=bool(item.get("can_auto_merge")),
                    manual_review=bool(item.get("requires_manual_review")),
                    reason=item.get("conflict_reason"),
                    action=item.get("recommended_action"),
                )
            )

        self.stdout.write("recommended_sql_or_actions:")
        for item in list(analysis.get("recommended_sql_or_actions") or []):
            self.stdout.write(f"  - {item}")

        if bool(options.get("apply_safe")):
            self.stdout.write(
                "applied_merge_count={count} | skipped_merge_count={skipped}".format(
                    count=int(analysis.get("applied_merge_count") or 0),
                    skipped=int(analysis.get("skipped_merge_count") or 0),
                )
            )
            for item in list(analysis.get("applied_merges") or []):
                self.stdout.write(f"  - applied={item}")
