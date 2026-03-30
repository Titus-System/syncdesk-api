from app.domains.ticket.repositories import TicketRepository


class TicketService:
    def __init__(self, repository: TicketRepository):
        self.repo = repository
