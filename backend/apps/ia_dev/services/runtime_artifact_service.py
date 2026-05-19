from __future__ import annotations

from pathlib import Path

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner


class RuntimeArtifactService:
    SERVICE_VERSION = "runtime_artifact.v1"
    ARTIFACT_TOKEN_SALT = "ia_dev.runtime_artifact"
    DEFAULT_ARTIFACT_TTL_SECONDS = 24 * 60 * 60
    PROVIDER_SERIAL_EXPORT_DIR = "tmp_provider_serial_validation_exports"

    def __init__(self) -> None:
        self.signer = TimestampSigner(salt=self.ARTIFACT_TOKEN_SALT)

    @classmethod
    def provider_serial_export_dir(cls) -> Path:
        return Path(__file__).resolve().parents[3] / cls.PROVIDER_SERIAL_EXPORT_DIR

    def issue_artifact_id(self, *, filename: str) -> str:
        normalized = str(filename or "").strip()
        if not normalized:
            raise ValueError("artifact_filename_required")
        return self.signer.sign(normalized)

    def resolve_artifact_path(
        self,
        *,
        artifact_id: str,
        max_age_seconds: int | None = None,
    ) -> Path:
        normalized_token = str(artifact_id or "").strip()
        if not normalized_token:
            raise ValueError("artifact_id_required")
        try:
            filename = str(
                self.signer.unsign(
                    normalized_token,
                    max_age=max_age_seconds or self.DEFAULT_ARTIFACT_TTL_SECONDS,
                )
            ).strip()
        except SignatureExpired as exc:
            raise ValueError("artifact_expired") from exc
        except BadSignature as exc:
            raise ValueError("artifact_invalid") from exc

        if not filename or "/" in filename or "\\" in filename:
            raise ValueError("artifact_invalid")

        artifact_path = (self.provider_serial_export_dir() / filename).resolve()
        export_dir = self.provider_serial_export_dir().resolve()
        if export_dir not in artifact_path.parents:
            raise ValueError("artifact_invalid")
        if not artifact_path.exists() or not artifact_path.is_file():
            raise ValueError("artifact_not_found")
        return artifact_path

