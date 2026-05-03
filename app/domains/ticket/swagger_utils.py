from typing import Any

from fastapi import status

from app.domains.ticket.schemas import TicketCommentResponse, TicketResponse
from app.schemas.response import ErrorContent, GenericSuccessContent

comment_on_ticket_responses: dict[int | str, dict[str, Any]] = {
    201: {
        "description": "Comment added to the ticket and returned in the response payload.",
        "model": GenericSuccessContent[TicketCommentResponse],
    },
    401: {
        "description": "Missing or invalid authentication token.",
        "model": ErrorContent,
    },
    403: {
        "description": "User lacks the `ticket:comment` permission.",
        "model": ErrorContent,
    },
    404: {
        "description": "Ticket not found for the given `ticket_id`.",
        "model": ErrorContent,
    },
}

comment_on_ticket_swagger: dict[str, Any] = {
    "summary": "Add a comment to a ticket",
    "description": (
        "Appends a comment to the ticket identified by `ticket_id`. "
        "The author is derived from the authenticated user (name, username, or email, "
        "in that order). Use the `internal` flag to mark a comment as visible to "
        "agents only or visible to the requesting client."
    ),
    "status_code": status.HTTP_201_CREATED,
    "response_model": GenericSuccessContent[TicketCommentResponse],
    "responses": comment_on_ticket_responses,
}

get_ticket_comments_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "List of comments belonging to the ticket, in insertion order.",
        "model": GenericSuccessContent[list[TicketCommentResponse]],
    },
    401: {
        "description": "Missing or invalid authentication token.",
        "model": ErrorContent,
    },
    403: {
        "description": "User lacks the `ticket:read` permission.",
        "model": ErrorContent,
    },
    404: {
        "description": "Ticket not found for the given `ticket_id`.",
        "model": ErrorContent,
    },
}

get_ticket_comments_swagger: dict[str, Any] = {
    "summary": "List ticket comments",
    "description": (
        "Returns every comment attached to the ticket identified by `ticket_id`, "
        "preserving insertion order. Both internal and external comments are included; "
        "consumers should filter by the `internal` flag when rendering to clients."
    ),
    "status_code": status.HTTP_200_OK,
    "response_model": GenericSuccessContent[list[TicketCommentResponse]],
    "responses": get_ticket_comments_responses,
}


search_tickets_by_text_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": (
            "List of tickets whose `description` or comments match the query. "
            "Results are scoped by the requester's role and may be empty."
        ),
        "model": GenericSuccessContent[list[TicketResponse]],
    },
    401: {
        "description": "Missing or invalid authentication token.",
        "model": ErrorContent,
    },
    403: {
        "description": "User lacks the `chat:read` permission.",
        "model": ErrorContent,
    },
}

search_tickets_by_text_swagger: dict[str, Any] = {
    "summary": "Search tickets by text",
    "description": (
        "Case-insensitive substring search across the ticket `description` and the "
        "text of every comment. Results are scoped by the requester's role:\n\n"
        "- **client**: only tickets where the requester is the client.\n"
        "- **agent / N1 / N2 / N3**: only tickets where the requester appears in "
        "the assignment history.\n"
        "- **admin**: only tickets whose client belongs to the same company as the "
        "requester. An admin without an associated company sees an empty list.\n\n"
        "A blank `search_query` always returns an empty list."
    ),
    "status_code": status.HTTP_200_OK,
    "response_model": GenericSuccessContent[list[TicketResponse]],
    "responses": search_tickets_by_text_responses,
}
