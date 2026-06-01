from typing import Any

from fastapi import status

from app.domains.chatbot.schemas import (
    AttendanceResponse,
    EvaluationResponse,
    TriageData,
)
from app.schemas.response import ErrorContent, GenericSuccessContent

_MAIN_MENU_MESSAGE = (
    "Olá! Bem vindo ao SyncDesk! Para começarmos, verifiquei no seu cadastro "
    "e você possui os seguintes produtos disponíveis para manutenção. "
    "Selecione a opção que indica sobre o que você quer falar hoje:"
)

_MAIN_MENU_QUICK_REPLIES = [
    {"label": "Produto A", "value": "1"},
    {"label": "Produto B", "value": "2"},
    {"label": "Produto C", "value": "3"},
    {"label": "Desejo apenas tirar uma dúvida.", "value": "4"},
    {"label": "Desejo uma liberação de acesso no Sync Desk.", "value": "5"},
]

_TRIAGE_IN_PROGRESS_EXAMPLE: dict[str, Any] = {
    "data": {
        "triage_id": "69f40f33baca8f85e73cb741",
        "step_id": "step_a",
        "message": _MAIN_MENU_MESSAGE,
        "input": {
            "mode": "quick_replies",
            "quick_replies": _MAIN_MENU_QUICK_REPLIES,
        },
    },
    "meta": {
        "timestamp": "2026-05-01T02:25:55.593576+00:00",
        "success": True,
        "request_id": "d87e6a1b-f3fe-4c60-bb20-f65f3299976f",
    },
}

_TRIAGE_FINISHED_TICKET_EXAMPLE: dict[str, Any] = {
    "data": {
        "triage_id": "69f40f33baca8f85e73cb741",
        "finished": True,
        "closure_message": (
            "Aguarde, sua solicitação foi criada e será atribuída a um de nossos "
            "analistas. Você já pode acompanhar o tema pela tela 'Minhas demandas'. "
            "Obrigada!"
        ),
        "result": {"type": "Ticket", "id": "69f40f33baca8f85e73cb741"},
    },
    "meta": {
        "timestamp": "2026-05-01T02:30:11.123456+00:00",
        "success": True,
        "request_id": "5b1c8d2e-7a44-4f9b-9cf3-2e8a4b1d6f70",
    },
}

_TRIAGE_FINISHED_RESOLVED_EXAMPLE: dict[str, Any] = {
    "data": {
        "triage_id": "69f40f33baca8f85e73cb741",
        "finished": True,
        "closure_message": "Atendimento finalizado! Momento de avaliação do atendimento.",
        "result": None,
    },
    "meta": {
        "timestamp": "2026-05-01T02:32:44.778899+00:00",
        "success": True,
        "request_id": "8e2a51fb-9eaa-4af6-95cc-bb0f25c91022",
    },
}

create_attendance_responses: dict[int | str, dict[str, Any]] = {
    201: {
        "description": "Attendance created and first triage step (MAIN_MENU) returned.",
        "model": GenericSuccessContent[TriageData],
        "content": {
            "application/json": {
                "example": _TRIAGE_IN_PROGRESS_EXAMPLE,
            },
        },
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
        "and immediately runs the first FSM transition, returning the MAIN_MENU "
        "question. The client identity is derived from the JWT token; no request "
        "body is required. The persisted attendance starts with `status = opened` "
        "and a single triage step (`A`).\n\n"
        "This is the only way to create an attendance — the webhook does not "
        "create them."
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
        "description": (
            "Triage step processed successfully. The response shape depends on "
            "whether the triage is still running (`step_id` + `message` + `input`) "
            "or has finished (`finished: true` + `closure_message` + optional `result`)."
        ),
        "model": GenericSuccessContent[TriageData],
        "content": {
            "application/json": {
                "examples": {
                    "in_progress": {
                        "summary": "Triage step in progress",
                        "value": _TRIAGE_IN_PROGRESS_EXAMPLE,
                    },
                    "finished_ticket": {
                        "summary": "Triage finished — ticket created",
                        "value": _TRIAGE_FINISHED_TICKET_EXAMPLE,
                    },
                    "finished_resolved": {
                        "summary": "Triage finished — resolved without ticket",
                        "value": _TRIAGE_FINISHED_RESOLVED_EXAMPLE,
                    },
                },
            },
        },
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
        "from the chatbot FSM. The attendance must already exist (created via "
        "`POST /`). Exactly one of `answer_text` or `answer_value` must be "
        "provided.\n\n"
        "While the triage is running, the response carries `step_id`, `message` "
        "and `input` (mode + quick_replies). When the triage finishes, the "
        "response carries `finished: true`, a `closure_message`, and a `result` "
        "block when a ticket was generated."
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
