from datetime import UTC, datetime, timedelta
from typing import Any

import aioboto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings
from app.core.logger import get_logger
from app.core.storage import ObjectStorage, PresignedUpload
from app.infra.storage.metrics import (
    presigned_urls_generated_total,
    storage_backend_errors_total,
    storage_object_deletes_total,
)

settings = get_settings()

_NOT_FOUND_CODES = frozenset({"404", "NoSuchKey", "NotFound"})


class S3ObjectStorage(ObjectStorage):
    """S3-compatible object storage implementation backed by ``aioboto3``.

    Targets MinIO via ``S3_ENDPOINT_URL`` for server-side operations and
    issues presigned URLs against ``S3_PUBLIC_ENDPOINT_URL`` so they remain
    reachable by clients outside the docker network.
    """

    def __init__(self) -> None:
        self._bucket = settings.S3_BUCKET_DEFAULT
        self._region = settings.S3_REGION
        self._internal_endpoint = settings.S3_ENDPOINT_URL
        self._public_endpoint = settings.S3_PUBLIC_ENDPOINT_URL
        self._access_key = settings.S3_ACCESS_KEY
        self._secret_key = settings.S3_SECRET_KEY
        self._session = aioboto3.Session()
        self._logger = get_logger("app.infra.storage")

    def _client(self, endpoint_url: str) -> Any:
        return self._session.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=self._region,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    async def generate_presigned_upload(
        self,
        object_key: str,
        content_type: str,
        max_size_bytes: int,
        expires_in_seconds: int,
    ) -> PresignedUpload:
        try:
            async with self._client(self._public_endpoint) as client:
                response: dict[str, Any] = await client.generate_presigned_post(
                    Bucket=self._bucket,
                    Key=object_key,
                    Fields={"Content-Type": content_type},
                    Conditions=[
                        {"Content-Type": content_type},
                        ["content-length-range", 1, max_size_bytes],
                    ],
                    ExpiresIn=expires_in_seconds,
                )
        except (ClientError, BotoCoreError) as exc:
            storage_backend_errors_total.labels(operation="presigned_upload").inc()
            self._logger.error(
                "S3 generate_presigned_post failed",
                extra={"object_key": object_key, "content_type": content_type},
                exc_info=exc,
            )
            raise

        presigned_urls_generated_total.labels(operation="upload").inc()
        self._logger.debug(
            "Presigned upload generated",
            extra={"object_key": object_key, "expires_in_seconds": expires_in_seconds},
        )
        return PresignedUpload(
            url=str(response["url"]),
            method="POST",
            fields={str(k): str(v) for k, v in response["fields"].items()},
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in_seconds),
        )

    async def generate_presigned_download_url(
        self, object_key: str, expires_in_seconds: int
    ) -> str:
        try:
            async with self._client(self._public_endpoint) as client:
                url: str = await client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self._bucket, "Key": object_key},
                    ExpiresIn=expires_in_seconds,
                )
        except (ClientError, BotoCoreError) as exc:
            storage_backend_errors_total.labels(operation="presigned_download").inc()
            self._logger.error(
                "S3 generate_presigned_url failed",
                extra={"object_key": object_key},
                exc_info=exc,
            )
            raise

        presigned_urls_generated_total.labels(operation="download").inc()
        return url

    async def object_exists(self, object_key: str) -> bool:
        async with self._client(self._internal_endpoint) as client:
            try:
                await client.head_object(Bucket=self._bucket, Key=object_key)
            except ClientError as exc:
                if self._is_not_found(exc):
                    return False
                storage_backend_errors_total.labels(operation="head_object").inc()
                self._logger.error(
                    "S3 head_object failed",
                    extra={"object_key": object_key},
                    exc_info=exc,
                )
                raise
        return True

    async def get_object_size(self, object_key: str) -> int | None:
        async with self._client(self._internal_endpoint) as client:
            try:
                response: dict[str, Any] = await client.head_object(
                    Bucket=self._bucket, Key=object_key
                )
            except ClientError as exc:
                if self._is_not_found(exc):
                    return None
                storage_backend_errors_total.labels(operation="head_object").inc()
                self._logger.error(
                    "S3 head_object failed",
                    extra={"object_key": object_key},
                    exc_info=exc,
                )
                raise
        return int(response["ContentLength"])

    async def delete_object(self, object_key: str) -> None:
        try:
            async with self._client(self._internal_endpoint) as client:
                await client.delete_object(Bucket=self._bucket, Key=object_key)
        except (ClientError, BotoCoreError) as exc:
            storage_backend_errors_total.labels(operation="delete_object").inc()
            self._logger.error(
                "S3 delete_object failed",
                extra={"object_key": object_key},
                exc_info=exc,
            )
            raise
        storage_object_deletes_total.inc()
        self._logger.debug("Object deleted from storage", extra={"object_key": object_key})

    @staticmethod
    def _is_not_found(exc: ClientError) -> bool:
        error = exc.response.get("Error", {}) if isinstance(exc.response, dict) else {}
        code = error.get("Code") if isinstance(error, dict) else None
        return code in _NOT_FOUND_CODES
