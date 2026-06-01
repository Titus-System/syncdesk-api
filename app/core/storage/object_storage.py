from abc import ABC, abstractmethod

from app.core.storage.schemas import PresignedUpload


class ObjectStorage(ABC):
    """Provider-agnostic object storage contract.

    Implementations live under ``app/infra/storage`` and may target MinIO,
    AWS S3, DigitalOcean Spaces or any other S3-compatible backend.
    """

    @abstractmethod
    async def generate_presigned_upload(
        self,
        object_key: str,
        content_type: str,
        max_size_bytes: int,
        expires_in_seconds: int,
    ) -> PresignedUpload:
        """Return a presigned upload payload restricted to the given content type and size."""

    @abstractmethod
    async def generate_presigned_download_url(
        self, object_key: str, expires_in_seconds: int
    ) -> str:
        """Return a single-use presigned URL allowing GET on the object."""

    @abstractmethod
    async def object_exists(self, object_key: str) -> bool:
        """Return whether the object is present in the backend."""

    @abstractmethod
    async def get_object_size(self, object_key: str) -> int | None:
        """Return the object size in bytes, or ``None`` if the object does not exist."""

    @abstractmethod
    async def delete_object(self, object_key: str) -> None:
        """Permanently remove the object from the backend. No-op if absent."""
