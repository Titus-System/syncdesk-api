from typing import Any

from fastapi import status

from app.domains.live_chat.entities import Conversation
from app.domains.live_chat.schemas import PaginatedMessages
from app.schemas.response import ErrorContent, GenericSuccessContent

post_conv_responses: dict[int | str, dict[str, Any]] = {
    201: {
        "description": "Conversation created successfully.",
        "model": GenericSuccessContent[Conversation],
    },
    403: {
        "description": "User attempted to create a conversation on behalf of another user.",
        "model": ErrorContent,
    },
    409: {
        "description": "A conversation with the same constraints already exists.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

post_conv_swagger: dict[str, Any] = {
    "summary": "Create a new conversation",
    "description": (
        "Creates a new live-chat conversation linked to a ticket. "
        "Non-agent / non-admin users can only create conversations for themselves. "
        "Returns 409 if a conversation with the same unique constraints already exists."
    ),
    "status_code": status.HTTP_201_CREATED,
    "response_model": GenericSuccessContent[Conversation],
    "responses": post_conv_responses,
}

get_convs_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "List of conversations retrieved successfully.",
        "model": GenericSuccessContent[list[Conversation]],
    },
    403: {
        "description": "The authenticated user is not a participant in this ticket.",
        "model": ErrorContent,
    },
}

get_client_convs_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "List of conversations for the client retrieved successfully.",
        "model": GenericSuccessContent[list[Conversation]],
    },
    403: {
        "description": "The authenticated user does not have permission to read chats.",
        "model": ErrorContent,
    },
    422: {
        "description": "Path parameter validation failed.",
        "model": ErrorContent,
    },
}

get_client_convs_swagger: dict[str, Any] = {
    "summary": "List conversations for a client",
    "description": (
        "Returns all conversations associated with the given client id. "
        "Requires the 'chat:read' permission."
    ),
    "response_model": GenericSuccessContent[list[Conversation]],
    "responses": get_client_convs_responses,
}

get_convs_swagger: dict[str, Any] = {
    "summary": "List conversations for a ticket",
    "description": (
        "Returns all conversations associated with the given ticket. "
        "Non-admin users must be a current participant in the ticket's latest conversation."
    ),
    "response_model": GenericSuccessContent[list[Conversation]],
    "responses": get_convs_responses,
}

get_messages_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Paginated messages retrieved successfully.",
        "model": GenericSuccessContent[PaginatedMessages],
    },
    403: {
        "description": "The authenticated user is not a participant in this ticket.",
        "model": ErrorContent,
    },
}

get_messages_swagger: dict[str, Any] = {
    "summary": "Get paginated messages for a ticket",
    "description": (
        "Retrieves paginated messages across all conversations of the given ticket. "
        "Messages are ordered chronologically in descending order. "
        "Non-admin users must be a current participant in the ticket."
    ),
    "response_model": GenericSuccessContent[PaginatedMessages],
    "responses": get_messages_responses,
}

set_agent_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Agent assigned to the conversation successfully.",
        "model": GenericSuccessContent[None],
    },
    403: {
        "description": (
            "The user is not allowed to reassign, "
            "or the provided agent_id does not belong to a valid agent."
        ),
        "model": ErrorContent,
    },
    404: {
        "description": "Conversation or referenced resource not found.",
        "model": ErrorContent,
    },
}

set_agent_swagger: dict[str, Any] = {
    "summary": "Assign an agent to a conversation",
    "description": (
        "Sets or reassigns the agent for an existing conversation. "
        "Only admins or the currently assigned agent can reassign. "
        "The target agent_id must correspond to a user with the 'agent' role."
    ),
    "response_model": GenericSuccessContent[None],
    "responses": set_agent_responses,
}
