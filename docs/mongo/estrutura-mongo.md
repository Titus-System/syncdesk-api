# MongoDB Schema — SyncDesk

## Collections

### conversations

* Document class: `Conversation`
* Domínio: `live_chat`
* Arquivo: `app/domains/live_chat/entities.py`
* Descrição: conversas de atendimento ao vivo associadas a tickets. Armazena participantes, encadeamento entre conversas e mensagens embutidas.
* Fields:
  * `_id`: `ObjectId`, implícito do Beanie
  * `ticket_id`: `PydanticObjectId`, obrigatório, referência lógica para `tickets._id`
  * `agent_id`: `UUID | None`, opcional, referência lógica para `users.id` do PostgreSQL
  * `client_id`: `UUID`, obrigatório, referência lógica para `users.id` do PostgreSQL
  * `sequential_index`: `int`, default `0`
  * `parent_id`: `PydanticObjectId | None`, opcional, referência para outra conversa
  * `children_ids`: `list[PydanticObjectId]`, default lista vazia, referências para conversas filhas
  * `started_at`: `datetime`, default `datetime.now(UTC)`
  * `finished_at`: `datetime | None`, opcional
  * `messages`: `list[ChatMessage]`, default lista vazia
* Embedded documents:
  * `ChatMessage`
    * `id`: `UUID`, obrigatório
    * `conversation_id`: `PydanticObjectId`, obrigatório, referência lógica para `conversations._id`
    * `sender_id`: `UUID | "System"`, obrigatório, referência lógica para `users.id` ou marcador textual de sistema
    * `timestamp`: `datetime`, default `datetime.now(UTC)`
    * `type`: literal `"text"` ou `"file"`, obrigatório
    * `content`: `str`, obrigatório
    * `mime_type`: `str | None`, opcional
    * `filename`: `str | None`, opcional
    * `file_id`: `UUID | None`, opcional, referência lógica para `file_objects.id` do PostgreSQL
    * `responding_to`: `UUID | None`, opcional, possível referência a outro `ChatMessage.id`
* Arrays:
  * `children_ids`: array de `ObjectId`
  * `messages`: array de subdocumentos `ChatMessage`
* References:
  * `ticket_id -> tickets._id`, reference by ObjectId
  * `agent_id -> PostgreSQL users.id`, reference by UUID
  * `client_id -> PostgreSQL users.id`, reference by UUID
  * `parent_id -> conversations._id`, self-reference by ObjectId
  * `children_ids[] -> conversations._id`, self-reference by ObjectId
  * `messages[].conversation_id -> conversations._id`, embedded self/context reference
  * `messages[].sender_id -> PostgreSQL users.id` ou `"System"`
  * `messages[].file_id -> PostgreSQL file_objects.id`, relação lógica inferida
  * `messages[].responding_to -> messages[].id`, possível referência interna
* Enums:
  * `messages[].type`: `"text" | "file"`
  * `messages[].sender_id`: `UUID | "System"`
* Indexes:
  * unique index: `(ticket_id, sequential_index)`
* Notes:
  * `ConversationRepository.get_active_conversations` faz `$lookup` com `tickets`, confirmando relação lógica `conversations.ticket_id -> tickets._id`.
  * Seed remove índice legado `service_session_id_1_sequential_index_1`, indicando schema anterior não mais usado.
  * Para mensagens `type="file"`, o schema de entrada exige `mime_type`, `filename` e `file_id`, mas o model mantém esses campos opcionais para compatibilidade com documentos históricos.

### tickets

* Document class: `Ticket`
* Domínio: `ticket`
* Arquivo: `app/domains/ticket/models.py`
* Descrição: chamados de suporte criados a partir da triagem/chatbot, com snapshot do cliente, histórico de agentes, comentários e vínculos com conversas.
* Fields:
  * `_id`: `ObjectId`, implícito do Beanie
  * `triage_id`: `PydanticObjectId`, obrigatório, referência lógica para atendimento/triagem
  * `type`: `TicketType`, obrigatório
  * `criticality`: `TicketCriticality`, obrigatório
  * `product`: `str`, obrigatório, snapshot textual do produto
  * `status`: `TicketStatus`, obrigatório
  * `level`: `TicketLevel`, default `N1`
  * `creation_date`: `datetime`, obrigatório
  * `description`: `str`, obrigatório
  * `chat_ids`: `list[PydanticObjectId]`, default lista vazia
  * `agent_history`: `list[TicketHistory]`, default lista vazia
  * `client`: `TicketClient`, obrigatório
  * `comments`: `list[TicketComment]`, default lista vazia
  * `closed_at`: `datetime | None`, opcional
  * `closed_by_agent`: `TicketHistory | None`, opcional
* Embedded documents:
  * `TicketClient`
    * `id`: `UUID`, referência lógica para `users.id` do PostgreSQL
    * `name`: `str`, snapshot
    * `email`: `str`, snapshot
    * `company`: `TicketCompany`
  * `TicketCompany`
    * `id`: `UUID`, normalmente referência lógica para `companies.id` do PostgreSQL; se `company_id` for omitido, o serviço usa `user.id` como fallback
    * `name`: `str`, snapshot
  * `TicketHistory`
    * `agent_id`: `UUID`, referência lógica para `users.id` do PostgreSQL
    * `name`: `str`, snapshot do agente
    * `level`: `str`, nível de suporte, normalmente `N1`, `N2`, `N3`
    * `assignment_date`: `datetime`
    * `exit_date`: `datetime | None`
    * `transfer_reason`: `str | None`
  * `TicketComment`
    * `comment_id`: `UUID`, default `uuid4`
    * `author`: `str`, nome textual do autor, sem `author_id`
    * `text`: `str`
    * `date`: `datetime`
    * `internal`: `bool`, default `False`
  * `closed_by_agent`
    * Mesmo shape de `TicketHistory`, snapshot do agente ativo no fechamento
* Arrays:
  * `chat_ids`: array de `ObjectId`, referências para `conversations._id`
  * `agent_history`: array de subdocumentos `TicketHistory`
  * `comments`: array de subdocumentos `TicketComment`
* References:
  * `triage_id -> atendimentos._id` ou `attendances._id`, reference by ObjectId; relação lógica inferida por eventos e repositório
  * `chat_ids[] -> conversations._id`, reference by ObjectId
  * `client.id -> PostgreSQL users.id`, reference by UUID
  * `client.company.id -> PostgreSQL companies.id`, reference by UUID quando `company_id` existe; possível fallback para `users.id` quando empresa é omitida
  * `agent_history[].agent_id -> PostgreSQL users.id`, reference by UUID
  * `closed_by_agent.agent_id -> PostgreSQL users.id`, reference by UUID
  * `product`: possível relação lógica com `products.name` do PostgreSQL, mas sem ID/FK; é snapshot textual
* Enums:
  * `TicketType`: `issue`, `access`, `new_feature`
  * `TicketCriticality`: `high`, `medium`, `low`
  * `TicketStatus`: `open`, `awaiting_assignment`, `in_progress`, `waiting_for_provider`, `waiting_for_validation`, `finished`, `cancelled`
  * `TicketLevel`: `N1`, `N2`, `N3`
* Indexes:
  * nenhum índice definido no model Beanie
* Notes:
  * `TicketService._build_ticket_client` monta snapshot do usuário a partir do PostgreSQL.
  * `ConversationListener._attach_chat_to_ticket` adiciona `conversation.id` em `ticket.chat_ids`.
  * `closed_by_agent` é preenchido ao finalizar ticket, copiando o agente ativo de `agent_history`.
  * `department_id` aparece em DTOs como contrato provisório, mas o próprio service comenta que o modelo persistido ainda não armazena departamento.

### attendances

* Document class: `Attendance`
* Domínio: `chatbot`
* Arquivo: `app/domains/chatbot/models.py`
* Descrição: model Beanie registrado para atendimentos/triagens do chatbot.
* Fields:
  * `_id`: `ObjectId`, implícito do Beanie
  * `status`: `AttendanceStatus`, obrigatório
  * `start_date`: `datetime`, obrigatório
  * `end_date`: `datetime | None`, opcional
  * `client`: `AttendanceClient`, obrigatório
  * `triage`: `list[Triage]`, default lista vazia
  * `result`: `AttendanceResult | None`, opcional
  * `evaluation`: `AttendanceEvaluation | None`, opcional
* Embedded documents:
  * `AttendanceClient`
    * `id`: `UUID`, referência lógica para `users.id` do PostgreSQL
    * `name`: `str`
    * `email`: `str`
    * `company`: `AttendanceCompany | dict[str, Any] | None`
  * `AttendanceCompany`
    * `id`: `UUID`, referência lógica para `companies.id` do PostgreSQL
    * `name`: `str`
  * `Triage`
    * `step`: `str`
    * `question`: `str`
    * `answer_value`: `str | None`
    * `answer_text`: `str | None`
  * `AttendanceResult`
    * `type`: `str`, valores observados: `"Ticket"` ou `"Resolved"`
    * `closure_message`: `str`
    * `ticket_id`: `str | None`, referência lógica para `tickets._id` como string
    * `chat_id`: `str | None`, referência lógica para `conversations._id` como string
  * `AttendanceEvaluation`
    * `rating`: `int`, obrigatório, validação `1 <= rating <= 5`
* Arrays:
  * `triage`: array de subdocumentos `Triage`
* References:
  * `client.id -> PostgreSQL users.id`, reference by UUID
  * `client.company.id -> PostgreSQL companies.id`, reference by UUID quando presente
  * `result.ticket_id -> tickets._id`, relação lógica como string
  * `result.chat_id -> conversations._id`, relação lógica como string
* Enums:
  * `AttendanceStatus`: `opened`, `in_progress`, `finished`
  * `TriageState` usado nos steps: `A`, `B`, `C`, `D`, `F`, `G`, `X`, `J`, `L`, `H`, `E`, `I`
* Indexes:
  * nenhum índice definido no model
* Notes:
  * Embora registrado no `init_beanie`, não encontrei uso direto de `Attendance.find`, `Attendance.get` ou `Attendance.insert`.
  * O repositório usa diretamente `atendimentos`, não `attendances`.

### atendimentos

* Document class: não usa diretamente `Attendance` no repository; shape compatível/parcialmente divergente com `Attendance`
* Domínio: `chatbot`
* Arquivo principal: `app/domains/chatbot/repositories/chatbot_repository.py`
* Descrição: collection efetivamente usada para salvar atendimentos/triagens do chatbot.
* Fields:
  * `_id`: `ObjectId`, definido manualmente a partir de `triage_id`
  * `status`: string enum de `AttendanceStatus`
  * `start_date`: `datetime` ou string ISO, dependendo do caminho de persistência
  * `end_date`: `datetime | str | None`
  * `client`: objeto embutido
  * `triage`: array de steps
  * `result`: objeto embutido opcional
  * `evaluation`: objeto embutido opcional
* Embedded documents:
  * `client`
    * `id`: UUID serializado, referência lógica para `users.id`
    * `name`: `str`
    * `email`: `str`
    * `company`: objeto opcional com `id` e `name`
  * `triage[]`
    * `step`: `str`
    * `question`: `str`
    * `answer_text`: `str | None`
    * `answer_value`: `str | None`
    * `type`: `str`, campo persistido pelo service, valores observados: `free_text` ou `quick_replies`
  * `result`
    * `type`: `str`, `"Ticket"` ou `"Resolved"`
    * `closure_message`: `str`
    * `ticket_id`: `str | None`
    * `chat_id`: `str | None`
  * `evaluation`
    * `rating`: `int`, 1 a 5
* Arrays:
  * `triage`: array de subdocumentos de etapa
* References:
  * `_id -> tickets.triage_id`, reference by ObjectId
  * `client.id -> PostgreSQL users.id`, reference by UUID/string UUID
  * `client.company.id -> PostgreSQL companies.id`, reference by UUID/string UUID quando presente
  * `result.ticket_id -> tickets._id`, relação lógica como string
  * `result.chat_id -> conversations._id`, relação lógica como string
* Enums:
  * `status`: `opened`, `in_progress`, `finished`
  * `triage[].step`: valores de `TriageState`
* Indexes:
  * nenhum índice definido no código
* Notes:
  * Diverge do model `Attendance` em dois pontos relevantes:
    * collection name: repository usa `atendimentos`, model declara `attendances`
    * `triage[].type` é persistido pelo service, mas não existe no model `Triage`
  * `CreateAttendanceDTO.model_dump(mode="json")` tende a serializar datas/UUIDs para JSON, então documentos dessa collection podem guardar datas e UUIDs como strings. O service tem coerções defensivas ao ler.

---

## Relações Lógicas Principais

* `tickets.triage_id -> atendimentos._id`: reference by ObjectId, relação lógica inferida por `TicketListener` e `ChatbotRepository.find_ticket_and_conversation_ids_by_triage_id`
* `tickets.triage_id -> attendances._id`: relação lógica pelo model Beanie registrado, mas há divergência porque o repository usa `atendimentos`
* `tickets.chat_ids[] -> conversations._id`: reference by ObjectId, atualizada por `ConversationListener._attach_chat_to_ticket`
* `conversations.ticket_id -> tickets._id`: reference by ObjectId, confirmada por `$lookup` em `ConversationRepository.get_active_conversations`
* `conversations.parent_id -> conversations._id`: self-reference by ObjectId
* `conversations.children_ids[] -> conversations._id`: self-reference by ObjectId
* `conversations.client_id -> PostgreSQL users.id`: reference by UUID
* `conversations.agent_id -> PostgreSQL users.id`: reference by UUID
* `conversations.messages[].sender_id -> PostgreSQL users.id | "System"`: reference by UUID ou marcador de sistema
* `conversations.messages[].file_id -> PostgreSQL file_objects.id`: reference by UUID, relação lógica inferida pelo comentário/model/schema de mensagens de arquivo
* `conversations.messages[].responding_to -> conversations.messages[].id`: possível referência interna por UUID
* `tickets.client.id -> PostgreSQL users.id`: reference by UUID
* `tickets.client.company.id -> PostgreSQL companies.id`: reference by UUID quando `company_id` vem preenchido; possível fallback para `users.id` quando omitido
* `tickets.agent_history[].agent_id -> PostgreSQL users.id`: reference by UUID
* `tickets.closed_by_agent.agent_id -> PostgreSQL users.id`: reference by UUID
* `atendimentos.client.id -> PostgreSQL users.id`: reference by UUID/string UUID
* `atendimentos.client.company.id -> PostgreSQL companies.id`: reference by UUID/string UUID quando presente
* `atendimentos.result.ticket_id -> tickets._id`: logical relation as string
* `atendimentos.result.chat_id -> conversations._id`: logical relation as string