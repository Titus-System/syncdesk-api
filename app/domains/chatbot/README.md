# Domínio Chatbot (URA de Triagem)

Módulo responsável pela triagem automatizada de atendimentos via chatbot (URA). O cliente interage com um fluxo de perguntas e respostas (máquina de estados finita) que resulta na abertura de um ticket, resolução de dúvida ou encerramento simples.

## Visão Geral

O domínio `chatbot`:
- gerencia o ciclo de vida de um **Attendance** (atendimento) no MongoDB
- conduz a triagem por uma FSM (Finite State Machine) baseada em menus
- cria tickets automaticamente no domínio `ticket` quando a triagem resulta em demanda
- expõe avaliação de satisfação pós-atendimento
- expõe consulta de atendimentos individuais com campo computado `needs_evaluation`

Dependências principais:
- `ChatbotRepository` para persistência no MongoDB
- `ChatbotService` para regra de negócio e orquestração da FSM
- `ChatbotFSM` para transições de estado (puro, sem I/O)
- `ResponseFactoryDep` para o envelope de resposta HTTP
- `CurrentUserSessionDep` para autenticação
- Domínio `ticket` para criação de tickets a partir da triagem

## Arquitetura

```
chatbot/
├── routers.py              # Borda HTTP — endpoints REST
├── swagger_utils.py        # Dicts de documentação OpenAPI (separados das rotas)
├── schemas.py              # DTOs de entrada e saída (Pydantic)
├── models.py               # Documento Beanie (Attendance) e subdocumentos
├── enums.py                # TriageState e AttendanceStatus
├── fsm.py                  # Máquina de estados — MENU_MAP + ChatbotFSM
├── services/
│   └── chatbot_service.py  # Regra de negócio e orquestração
├── repositories/
│   └── chatbot_repository.py  # Acesso direto ao MongoDB (Motor)
├── dependencies.py         # Wiring de DI (ChatbotServiceDep, ChatbotRepositoryDep)
├── metrics.py              # Contadores Prometheus (mensagens, tickets)
├── exceptions.py           # Exceções de domínio
└── README.md
```

### Fluxo resumido

1. Router valida autenticação e delega ao service.
2. Service carrega (ou cria) o attendance do MongoDB.
3. Service extrai o estado atual da triagem e delega a transição para `ChatbotFSM`.
4. FSM retorna o próximo estado, mensagem e opções de input.
5. Service persiste o novo estado e, se a triagem finalizou com ticket, cria o ticket.
6. Router devolve resposta no envelope padrão.

## Máquina de Estados (FSM)

A FSM é definida em `fsm.py` através do dicionário `MENU_MAP`. Cada estado mapeia para uma mensagem, tipo de input e opções de transição.

```
MAIN_MENU (A)
├── [1,2,3] Produto → CHOOSING_PRODUCT_PROBLEM (B)
│   ├── [1] Falha → WAITING_FAILURE_TEXT (F) → TICKET_CREATED (E)
│   └── [2] Nova função → WAITING_FEATURE_TEXT (G) → TICKET_CREATED (E)
├── [4] Dúvida → CHOOSING_QUESTION_TYPE (C)
│   ├── [1] Prazos → SHOWING_DEADLINES (X) → [Sim] MAIN_MENU / [Não] SERVICE_FINISHED (I)
│   ├── [2] Manual → SHOWING_MANUAL (J) → [Sim] MAIN_MENU / [Não] SERVICE_FINISHED (I)
│   └── [3] Novo sistema → SHOWING_EMAIL (L) → [Sim] MAIN_MENU / [Não] SERVICE_FINISHED (I)
└── [5] Acesso → REQUESTING_ACCESS (D) → TICKET_CREATED (E)
```

Estados terminais: `TICKET_CREATED` (E) e `SERVICE_FINISHED` (I).

Tipos de input:
- `quick_replies`: usuário seleciona uma opção pré-definida (campo `answer_value`)
- `free_text`: usuário envia texto livre (campo `answer_text`)

A FSM é **pura** — não faz I/O. Recebe o estado atual e a mensagem, retorna `InternalBotResponseDTO`. Toda persistência e efeito colateral fica no service.

## Rotas Disponíveis

Base path: `/api/chatbot`

| Método | Path                        | Descrição                      | Permissão planejada    |
|--------|-----------------------------|--------------------------------|------------------------|
| POST   | `/`                         | Criar atendimento              | `chatbot:create`       |
| GET    | `/`                         | Listar atendimentos            | `chatbot:list`         |
| POST   | `/webhook`                  | Interagir com a triagem        | `chatbot:interact`     |
| GET    | `/{triage_id}`              | Consultar atendimento          | `chatbot:read`         |
| POST   | `/{triage_id}/evaluation`   | Avaliar atendimento            | `chatbot:evaluate`     |

A documentação OpenAPI de cada rota está em `swagger_utils.py`, aplicada via `**dict` no decorator do router — mantendo as rotas limpas.

### POST `/` — Criar atendimento

Cria um attendance com `status = opened` e já executa a primeira transição da FSM, retornando a pergunta inicial (MAIN_MENU). A identidade do cliente é derivada do token JWT. Não recebe request body.

Este é o **único ponto de criação** de um attendance. O webhook não cria attendances.

Retorno: `201` — `GenericSuccessContent[TriageData]` via `ResponseFactory`.

### POST `/webhook` — Interagir com a triagem

Recebe `triage_id` + resposta do usuário. O attendance já deve existir (criado via `POST /`). Retorna `404` se o `triage_id` não for encontrado.

Validações:
- `answer_text` e `answer_value` são mutuamente exclusivos (422)
- Ambos `None` serão rejeitados com 422 (T09)

Retorno: `200` — `GenericSuccessContent[TriageData]` via `ResponseFactory`.
Em andamento: `step_id`, `message`, `input` (mode + quick_replies).
Finalizado: `finished: true`, `closure_message`, e `result` (se ticket criado).

### GET `/{triage_id}` — Consultar atendimento

Retorna o attendance completo incluindo `needs_evaluation` (campo computado: `true` sse `status == finished` e `evaluation == null`).

### POST `/{triage_id}/evaluation` — Avaliar atendimento

Registra a nota de satisfação (1-5). Só pode ser chamado uma vez, e só após a triagem estar finalizada.

Erros: `404` (não encontrado), `409` (não finalizado ou já avaliado), `422` (rating inválido).

## Modelo de Dados

### Attendance (MongoDB — collection configurada em `models.py`)

| Campo        | Tipo                     | Descrição                              |
|--------------|--------------------------|----------------------------------------|
| `_id`        | `ObjectId`               | Usado como `triage_id`                 |
| `status`     | `AttendanceStatus`       | `opened`, `in_progress`, `finished`    |
| `start_date` | `datetime`               | Início do atendimento (UTC)            |
| `end_date`   | `datetime \| None`       | Fim do atendimento (UTC)               |
| `client`     | `AttendanceClient`       | Dados do cliente                       |
| `triage`     | `list[Triage]`           | Histórico de perguntas e respostas     |
| `result`     | `AttendanceResult \| None` | Tipo do resultado + mensagem de fechamento |
| `evaluation` | `AttendanceEvaluation \| None` | Nota de satisfação              |

O model `Attendance` herda de `beanie.Document` e deve estar registrado no `init_beanie()` em `app/main.py`.

## Schemas

### Entrada

| Schema              | Descrição                                        |
|---------------------|--------------------------------------------------|
| `TriageInputDTO`    | Payload do webhook (triage_id + resposta)        |
| `EvaluationRequest` | Payload da avaliação (rating: 1-5)               |
| `CreateAttendanceDTO` | DTO interno para criação de attendance         |

### Saída

| Schema              | Descrição                                        |
|---------------------|--------------------------------------------------|
| `TriageData`        | Bloco `data` da resposta de triagem (usado com `GenericSuccessContent[TriageData]`) |
| `AttendanceResponse`| Consulta completa com `needs_evaluation`         |
| `EvaluationResponse`| Confirmação da avaliação com `evaluated_at`      |
| `TriageStepSchema`  | Item do histórico de triagem                     |

### Internos

| Schema                 | Descrição                                    |
|------------------------|----------------------------------------------|
| `InternalBotResponseDTO` | Retorno da FSM (new_state, response_text, quick_replies) |
| `TriageInputDef`       | Definição do input esperado (mode + quick_replies) |

## Métricas

Definidas em `metrics.py`, registradas no Prometheus:

| Métrica                              | Tipo    | Labels | Descrição                        |
|--------------------------------------|---------|--------|----------------------------------|
| `domain_chatbot_messages_total`      | Counter | `step` | Total de mensagens processadas   |
| `domain_chatbot_tickets_created_total` | Counter | —    | Tickets criados pela triagem     |

## Integração com o Domínio Ticket

O `ChatbotService` cria tickets diretamente via `ChatbotRepository.create_ticket()`, usando o model `Ticket` do domínio `ticket`. O service:

1. Analisa as respostas da triagem para extrair `type`, `criticality` e `product`.
2. Monta um `TicketClient` a partir dos dados do attendance.
3. Insere o ticket via Beanie.

> **Nota (T09):** A criação direta será substituída por emissão do evento `triage.finished` via `EventDispatcher`. Um listener no domínio `ticket` irá criar o ticket a partir do payload do evento.

## Problemas Conhecidos

| Severidade | Problema | Descrição |
|---|---|---|
| Alto | Webhook sem autenticação | `POST /webhook` não exige token — qualquer requisição é aceita. Corrigido na T09. |
| Alto | Identidade do cliente no payload | `client_id/name/email` vem no body em vez de derivar do token. Corrigido na T09. |
| Alto | Criação de ticket acoplada | O service cria tickets diretamente, sem atomicidade. Migrar para EventDispatcher na T09. |
| Médio | `step_id` no DTO sem uso | Campo exigido no `TriageInputDTO` mas ignorado pelo service. Removido na T09. |
| Médio | `answer_text` sem sanitização | Texto livre persistido sem tratamento. Corrigido na T09. |
| Médio | `except Exception` genérico | Repository usa `except Exception` na conversão de ObjectId. Corrigido na T08. |
| Médio | `InternalBotResponseDTO.new_state` sem tipagem | Tipado como `Any`, deveria ser `TriageState \| None`. Corrigido na T08. |
| Baixo | Permissões comentadas | `require_permission(...)` está comentado em todas as rotas. Ativado progressivamente nas T08/T09. |
