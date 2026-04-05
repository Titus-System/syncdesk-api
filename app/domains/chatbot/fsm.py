from typing import Optional, Dict, List, TypedDict, NotRequired
from app.domains.chatbot.enums import TriageState
from app.domains.chatbot.schemas import InternalBotResponseDTO

# --- Tipagem estrita para o Pylance ---
class MenuOption(TypedDict):
    label: str
    value: str
    next_state: Optional[TriageState]

class MenuConfig(TypedDict):
    message: str
    input_type: str
    options: NotRequired[List[MenuOption]]
    next_state: NotRequired[Optional[TriageState]]
# -------------------------------------

# Mapa de menus (Dicionário Python)
# Preparado para ser migrado futuramente para o banco de dados.
MENU_MAP: Dict[TriageState, MenuConfig] = {
    TriageState.MAIN_MENU: {
        "message": "Olá! Bem vindo ao SyncDesk! Para começarmos, verifiquei no seu cadastro e você possui os seguintes produtos disponíveis para manutenção. Selecione a opção que indica sobre o que você quer falar hoje:",
        "input_type": "quick_replies",
        "options": [
            {"label": "Produto A", "value": "1", "next_state": TriageState.CHOOSING_PRODUCT_PROBLEM},
            {"label": "Produto B", "value": "2", "next_state": TriageState.CHOOSING_PRODUCT_PROBLEM},
            {"label": "Produto C", "value": "3", "next_state": TriageState.CHOOSING_PRODUCT_PROBLEM},
            {"label": "Desejo apenas tirar uma dúvida.", "value": "4", "next_state": TriageState.CHOOSING_QUESTION_TYPE},
            {"label": "Desejo uma liberação de acesso no Sync Desk.", "value": "5", "next_state": TriageState.REQUESTING_ACCESS}
        ]
    },
    TriageState.CHOOSING_PRODUCT_PROBLEM: {
        "message": "Entendi. Como posso te ajudar hoje em relação ao Produto escolhido?",
        "input_type": "quick_replies",
        "options": [
            {"label": "O sistema apresenta falhas.", "value": "1", "next_state": TriageState.WAITING_FAILURE_TEXT},
            {"label": "Quero solicitar uma nova função.", "value": "2", "next_state": TriageState.WAITING_FEATURE_TEXT}
        ]
    },
    TriageState.CHOOSING_QUESTION_TYPE: {
        "message": "Entendi. Selecione, por favor, qual a sua dúvida:",
        "input_type": "quick_replies",
        "options": [
            {"label": "Qual o período restante para manutenção dos sistemas que eu já adquiri?", "value": "1", "next_state": TriageState.SHOWING_DEADLINES},
            {"label": "Estou com dúvidas sobre como utilizar um dos meus sistemas.", "value": "2", "next_state": TriageState.SHOWING_MANUAL},
            {"label": "Como faço para solicitar um novo sistema?", "value": "3", "next_state": TriageState.SHOWING_EMAIL}
        ]
    },
    TriageState.REQUESTING_ACCESS: {
        "message": "Entendi. Por favor, envie uma mensagem respondendo as seguintes perguntas: 1-Essa liberação se refere a um novo perfil ou à edição de um perfil já existente? 2-Qual o email e empresa da pessoa que deve ser cadastrada? 3-Qual o motivo da solicitação? 4-Quais produtos essa pessoa deve ter vinculados à sua conta?",
        "input_type": "free_text",
        "next_state": None
    },
    TriageState.WAITING_FAILURE_TEXT: {
        "message": "Por favor, explique da maneira mais detalhada possível o seu problema. Lembre-se: Se a descrição do problema não for clara e/ou faltarem informações, seu chamado poderá ser cancelado pelo time de suporte. Seja específico e detalhista.",
        "input_type": "free_text",
        "next_state": None
    },
    TriageState.WAITING_FEATURE_TEXT: {
        "message": "Por favor, explique da maneira mais detalhada possível a nova funcionalidade que deseja. Lembre-se: Se a descrição da função não for clara e/ou faltarem informações, sua solicitação poderá ser cancelada pelo time de analistas. Seja específico e detalhista.",
        "input_type": "free_text",
        "next_state": None
    },
    TriageState.SHOWING_DEADLINES: {
        "message": "Verifiquei e esses são os seguintes prazos:\n Produto A - Até dd/mm/aaaa\n Produto B - Até dd/mm/aaa\n Produto C - Até dd/mm/aaaa\n\nAjudo em algo mais?",
        "input_type": "quick_replies",
        "options": [
            {"label": "Sim", "value": "1", "next_state": TriageState.MAIN_MENU},
            {"label": "Não", "value": "2", "next_state": TriageState.SERVICE_FINISHED}
        ]
    },
    TriageState.SHOWING_MANUAL: {
        "message": "Todos os nossos produtos possuem manual do usuário, onde você pode logar e acessar todas as informações necessárias para a navegação. Verifique no sistema e tire todas as suas dúvidas por lá.\n\nAjudo em algo mais?",
        "input_type": "quick_replies",
        "options": [
            {"label": "Sim", "value": "1", "next_state": TriageState.MAIN_MENU},
            {"label": "Não", "value": "2", "next_state": TriageState.SERVICE_FINISHED}
        ]
    },
    TriageState.SHOWING_EMAIL: {
        "message": "Você pode enviar um pedido através do nosso email suporte@empresa.com\n\nAjudo em algo mais?",
        "input_type": "quick_replies",
        "options": [
            {"label": "Sim", "value": "1", "next_state": TriageState.MAIN_MENU},
            {"label": "Não", "value": "2", "next_state": TriageState.SERVICE_FINISHED}
        ]
    },
    TriageState.ANYTHING_ELSE: {
        "message": "Ajudo em algo mais?",
        "input_type": "quick_replies",
        "options": [
            {"label": "Sim", "value": "1", "next_state": TriageState.MAIN_MENU},
            {"label": "Não", "value": "2", "next_state": TriageState.SERVICE_FINISHED}
        ]
    }
}

class ChatbotFSM:
    @staticmethod
    def process_interaction(current_state: Optional[TriageState], message: str) -> InternalBotResponseDTO:
        msg = message.strip() if message else ""

        # Se não houver estado, inicia pelo menu principal
        if not current_state or current_state not in MENU_MAP:
            return ChatbotFSM._get_state_response(TriageState.MAIN_MENU)

        current_menu = MENU_MAP[current_state]

        # Tratamento de entrada em texto livre
        if current_menu["input_type"] == "free_text":
            next_state = current_menu.get("next_state")
            if next_state is None:
                return ChatbotFSM._get_ticket_response()
            return ChatbotFSM._get_state_response(next_state)

        # Tratamento de resposta de opções
        if current_menu["input_type"] == "quick_replies":
            options = current_menu.get("options", [])
            for opt in options:
                if opt["value"] == msg:
                    next_state = opt.get("next_state")
                    
                    # Se não houver próximo estado, encerra e abre ticket (atendimento humano)
                    if next_state is None:
                        return ChatbotFSM._get_ticket_response()
                    
                    if next_state == TriageState.SERVICE_FINISHED:
                        return ChatbotFSM._get_finished_response()
                    
                    return ChatbotFSM._get_state_response(next_state)

            # Cai aqui se a mensagem não bater com nenhuma opção válida
            return ChatbotFSM._invalid_response(current_state, current_menu)
        
        return ChatbotFSM._get_state_response(TriageState.MAIN_MENU)

    @staticmethod
    def _get_state_response(state: TriageState) -> InternalBotResponseDTO:
        menu = MENU_MAP[state]
        is_free_text = menu["input_type"] == "free_text"
        
        # Constrói as opções apenas se não for campo de texto
        options = None
        if not is_free_text:
            options = [{"label": o["label"], "value": o["value"]} for o in menu.get("options", [])]
            
        return InternalBotResponseDTO(
            new_state=state,
            response_text=menu["message"],
            is_free_text=is_free_text,
            quick_replies=options
        )

    @staticmethod
    def _get_ticket_response() -> InternalBotResponseDTO:
        return InternalBotResponseDTO(
            new_state=TriageState.TICKET_CREATED,
            response_text="Aguarde, sua solicitação foi criada e será atribuída a um de nossos analistas. Você já pode acompanhar o tema pela tela 'Minhas demandas'. Obrigada!",
            is_finished=True
        )

    @staticmethod
    def _get_finished_response() -> InternalBotResponseDTO:
        return InternalBotResponseDTO(
            new_state=TriageState.SERVICE_FINISHED,
            response_text="Atendimento finalizado! Momento de avaliação do atendimento.",
            is_finished=True
        )

    @staticmethod
    def _invalid_response(state: TriageState, menu: MenuConfig) -> InternalBotResponseDTO:
        is_free_text = menu["input_type"] == "free_text"
        
        options = None
        if not is_free_text:
            options = [{"label": o["label"], "value": o["value"]} for o in menu.get("options", [])]
            
        return InternalBotResponseDTO(
            new_state=state,
            response_text="Opção inválida. Por favor, selecione uma das opções válidas abaixo.",
            is_free_text=is_free_text,
            quick_replies=options
        )