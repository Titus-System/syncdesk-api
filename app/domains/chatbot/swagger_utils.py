from typing import Any

from fastapi import status

from app.domains.chatbot.schemas import (
    AttendanceResponse,
    EvaluationResponse,
    TriageData,
)
from app.schemas.response import ErrorContent, GenericSuccessContent

create_attendance_responses: dict[int | str, dict[str, Any]] = {
    201: {
        "description": "Attendance created and first triage step returned.",
        "model": GenericSuccessContent[TriageData],
    },
    401: {
        "description": "Missing or invalid authentication token.",
        "model": ErrorContent,
    },
}

create_attendance_swagger: dict[str, Any] = {
    "summary": "Create a new attendance and start triage",
    "description": (
        "Creates a new triage attendance session for the authenticated user "
        "and returns the first question from the FSM (MAIN_MENU). "
        "The client identity is derived from the JWT token. No request body required. "
        "This is the only way to create an attendance — the webhook does not create them."
    ),
    "status_code": status.HTTP_201_CREATED,
    "response_model": GenericSuccessContent[TriageData],
    "responses": create_attendance_responses,
}

list_attendances_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "List of attendances retrieved successfully.",
        "model": GenericSuccessContent[list[AttendanceResponse]],
    },
    401: {
        "description": "Missing or invalid authentication token.",
        "model": ErrorContent,
    },
}

list_attendances_swagger: dict[str, Any] = {
    "summary": "List attendances",
    "description": (
        "Returns triage attendances visible to the authenticated user. "
        "All filters are optional and combined with AND; no filters returns all attendances.\n\n"
        "**Query parameters:**\n"
        "- `client_id` — UUID exato do cliente.\n"
        "- `client_name` — Busca parcial (case-insensitive) pelo nome do cliente.\n"
        "- `status` — Status do atendimento: `opened`, `in_progress`, `finished`.\n"
        "- `result_type` — Tipo do resultado: `Ticket` ou `Resolved`.\n"
        "- `start_date_from` — Início do intervalo de busca por data de início (inclusive, UTC).\n"
        "- `start_date_to` — Fim do intervalo de busca por data de início (inclusive, UTC).\n"
        "- `has_evaluation` — `true` = já avaliado, `false` = sem avaliação.\n"
        "- `rating` — Nota exata de avaliação (1–5)."
    ),
    "response_model": GenericSuccessContent[list[AttendanceResponse]],
    "responses": list_attendances_responses,
}

webhook_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Triage step processed successfully.",
        "model": GenericSuccessContent[TriageData],
    },
    401: {
        "description": "Missing or invalid authentication token.",
        "model": ErrorContent,
    },
    403: {
        "description": "User lacks the `chatbot:interact` permission.",
        "model": ErrorContent,
    },
    404: {
        "description": "Attendance not found for the given `triage_id`.",
        "model": ErrorContent,
    },
    422: {
        "description": (
            "Validation error: `answer_text` and `answer_value` sent together, or both are null."
        ),
        "model": ErrorContent,
    },
}

webhook_swagger: dict[str, Any] = {
    "summary": "Interact with the triage chatbot",
    "description": (
        "Sends an answer to the current triage step and receives the next step "
        "from the chatbot FSM. The attendance must already exist (created via POST /). "
        "Exactly one of `answer_text` or `answer_value` must be provided. "
        "When the triage finishes, the response includes "
        "a closure message and, if applicable, the generated ticket id."
    ),
    "response_model": GenericSuccessContent[TriageData],
    "responses": webhook_responses,
}

get_attendance_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Attendance details retrieved successfully.",
        "model": GenericSuccessContent[AttendanceResponse],
    },
    401: {
        "description": "Missing or invalid authentication token.",
        "model": ErrorContent,
    },
    404: {
        "description": "Attendance not found.",
        "model": ErrorContent,
    },
}

get_attendance_swagger: dict[str, Any] = {
    "summary": "Get attendance details",
    "description": (
        "Returns the full attendance record, including triage history, result, "
        "evaluation, and the computed `needs_evaluation` flag."
    ),
    "response_model": GenericSuccessContent[AttendanceResponse],
    "responses": get_attendance_responses,
}

evaluation_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Evaluation submitted successfully.",
        "model": GenericSuccessContent[EvaluationResponse],
    },
    401: {
        "description": "Missing or invalid authentication token.",
        "model": ErrorContent,
    },
    404: {
        "description": "Attendance not found.",
        "model": ErrorContent,
    },
    409: {
        "description": ("Attendance is not yet finished, or has already been evaluated."),
        "model": ErrorContent,
    },
    422: {
        "description": "Rating value out of the allowed range (1-5).",
        "model": ErrorContent,
    },
}

evaluation_swagger: dict[str, Any] = {
    "summary": "Submit attendance evaluation",
    "description": (
        "Records the client's satisfaction rating for a finished attendance. "
        "Can only be called once per attendance, and only after the triage "
        "has been completed (`status = finished`)."
    ),
    "status_code": status.HTTP_200_OK,
    "response_model": GenericSuccessContent[EvaluationResponse],
    "responses": evaluation_responses,
}
