from typing import Any

from fastapi import status

from app.domains.files.schemas import (
    ConfirmUploadResponse,
    DownloadUrlResponse,
    PresignUploadResponse,
)
from app.schemas.response import ErrorContent, GenericSuccessContent

presign_upload_responses: dict[int | str, dict[str, Any]] = {
    201: {
        "description": "Presigned upload URL issued successfully.",
        "model": GenericSuccessContent[PresignUploadResponse],
    },
    400: {
        "description": (
            "Validation failure: unsupported content type, file larger than the "
            "context allows, malformed conversation id, or sanitized filename "
            "rejected."
        ),
        "model": ErrorContent,
    },
    403: {
        "description": (
            "When context=live_chat_message, the authenticated user must be a "
            "participant of the referenced conversation."
        ),
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

presign_upload_swagger: dict[str, Any] = {
    "summary": "Request a presigned upload URL for a new file",
    "description": (
        "Validates the requested upload (mime type, size, context) and returns "
        "a presigned POST URL the client must use to send the file directly to "
        "the object storage backend. A `file_objects` row is created in `pending` "
        "state and only transitions to `uploaded` once the client calls the "
        "confirm endpoint after the upload finishes.\n\n"
        "Authorization rules per context:\n"
        "- `live_chat_message`: the user must be a participant of the "
        "conversation identified by `context_ref.conversation_id`.\n"
        "- `user_avatar`: any authenticated user can request the URL; the "
        "resulting object key is bound to the authenticated user id."
    ),
    "status_code": status.HTTP_201_CREATED,
    "response_model": GenericSuccessContent[PresignUploadResponse],
    "responses": presign_upload_responses,
}


confirm_upload_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Upload confirmed: the file is now in `uploaded` state.",
        "model": GenericSuccessContent[ConfirmUploadResponse],
    },
    403: {
        "description": "Only the original uploader can confirm a pending upload.",
        "model": ErrorContent,
    },
    404: {
        "description": "File not found or already deleted.",
        "model": ErrorContent,
    },
    409: {
        "description": (
            "Object is not yet present in the storage backend; the client should "
            "retry once the underlying upload has actually completed."
        ),
        "model": ErrorContent,
    },
}

confirm_upload_swagger: dict[str, Any] = {
    "summary": "Confirm that the upload finished",
    "description": (
        "Verifies that the object physically exists in the storage backend and "
        "transitions the `file_objects` row from `pending` to `uploaded`. "
        "Idempotent: calling for an already-uploaded file returns 200 without "
        "side effects."
    ),
    "response_model": GenericSuccessContent[ConfirmUploadResponse],
    "responses": confirm_upload_responses,
}


download_url_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Presigned download URL issued successfully.",
        "model": GenericSuccessContent[DownloadUrlResponse],
    },
    403: {
        "description": (
            "For `live_chat_message` files, only participants of the conversation "
            "and admins can read."
        ),
        "model": ErrorContent,
    },
    404: {
        "description": "File not found or not in `uploaded` state.",
        "model": ErrorContent,
    },
}

download_url_swagger: dict[str, Any] = {
    "summary": "Get a presigned download URL for a file",
    "description": (
        "Returns a short-lived presigned GET URL for the file. Read authorization "
        "depends on the file context:\n"
        "- `live_chat_message`: caller must be a participant of the conversation "
        "or have the admin role.\n"
        "- `user_avatar`: any authenticated user can read (profile pictures are "
        "considered visible across the system)."
    ),
    "response_model": GenericSuccessContent[DownloadUrlResponse],
    "responses": download_url_responses,
}


delete_file_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "File soft-deleted successfully (status set to `deleted`).",
        "model": GenericSuccessContent[ConfirmUploadResponse],
    },
    403: {
        "description": "Only the uploader or an admin can delete the file.",
        "model": ErrorContent,
    },
    404: {
        "description": "File not found or already deleted.",
        "model": ErrorContent,
    },
}

delete_file_swagger: dict[str, Any] = {
    "summary": "Soft-delete a file",
    "description": (
        "Marks the `file_objects` row as `deleted`. Physical removal from the "
        "storage backend happens later through a background job, after the "
        "configured grace period. Only the original uploader or an admin can "
        "call this endpoint."
    ),
    "response_model": GenericSuccessContent[ConfirmUploadResponse],
    "responses": delete_file_responses,
}
