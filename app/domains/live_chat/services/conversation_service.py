from ..repositories import ConversationRepository


class ConversationService:
    def __init__(self, repo: ConversationRepository):
        self.repo = repo
