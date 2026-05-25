from typing import Annotated

from fastapi import Depends

from app.core.dependencies import ObjectStorageDep
from app.db.postgres.dependencies import PgSessionDep

from .repositories import FileObjectRepository
from .services import FileService


def get_file_object_repository(db: PgSessionDep) -> FileObjectRepository:
    return FileObjectRepository(db)


def get_file_service(
    repo: Annotated[FileObjectRepository, Depends(get_file_object_repository)],
    object_storage: ObjectStorageDep,
) -> FileService:
    return FileService(repo=repo, object_storage=object_storage)


FileObjectRepositoryDep = Annotated[FileObjectRepository, Depends(get_file_object_repository)]
FileServiceDep = Annotated[FileService, Depends(get_file_service)]
