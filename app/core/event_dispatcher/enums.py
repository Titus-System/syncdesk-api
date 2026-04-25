from enum import Enum


class AppEvent(Enum):
    TRIAGE_FINISHED = "triage.finished"
    TICKET_CREATED = "ticket.created"
    TICKET_STATUS_UPDATED = "ticket.status_updated"
    TICKET_ESCALATED = "ticket.escalated"
    TICKET_ASSIGNEE_UPDATED = "ticket.assignee_updated"
    TICKET_CLOSED = "ticket.closed"
