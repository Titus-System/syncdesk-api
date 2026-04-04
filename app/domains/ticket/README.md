# Dominio de Tickets

Modulo responsavel pela criacao, consulta e atualizacao de status de tickets no SyncDesk API.

## Visao Geral

O dominio `ticket`:
- persiste tickets no MongoDB usando Beanie
- cria tickets com status inicial `open`
- resolve o cliente do ticket a partir de `client_id`
- permite consulta com filtros opcionais
- permite atualizacao de status com regras de transicao

Dependencias principais:
- `TicketRepository` para persistencia e consulta
- `TicketService` para regra de negocio
- `UserService` do dominio `auth` para resolver o cliente
- `ResponseFactoryDep` para o envelope de resposta HTTP
- `require_permission(...)` para autorizacao

## Arquitetura

- `routers.py`: borda HTTP
- `schemas.py`: contratos de entrada e saida
- `services.py`: regra de negocio
- `repositories.py`: acesso ao MongoDB
- `dependencies.py`: composicao do service
- `models.py`: enums e documento `Ticket`

Fluxo resumido:

1. Router valida autenticacao e permissao.
2. Router delega ao service.
3. Service executa a regra de negocio.
4. Repository acessa o MongoDB.
5. Router devolve resposta no envelope padrao.

## Rotas Disponiveis

### `GET /api/tickets/`

Lista tickets ou busca por filtros opcionais.

Permissao:
- `ticket:read`

Autenticacao:
- Bearer token obrigatorio

Filtros suportados:
- `ticket_id`
- `client_id`
- `triage_id`
- `status`
- `criticality`
- `type`
- `product`

Comportamento:
- sem filtros: retorna todos os tickets
- com filtros: aplica todos em conjunto
- sem resultados: retorna `200` com lista vazia
- com `ticket_id`: continua retornando lista para manter consistencia

Exemplos:

```http
GET /api/tickets/
GET /api/tickets/?status=open
GET /api/tickets/?client_id=0f7d7c4f-7b5b-45cb-9d85-6f3c69f0b5d2
GET /api/tickets/?criticality=high&type=issue
GET /api/tickets/?ticket_id=67f0ca60e4b0b1a2c3d4e601
GET /api/tickets/?client_id=0f7d7c4f-7b5b-45cb-9d85-6f3c69f0b5d2&status=in_progress&criticality=high
```

### `POST /api/tickets/`

Cria um novo ticket.

Permissao:
- `ticket:create`

Body:

```json
{
  "triage_id": "67f0c9b8e4b0b1a2c3d4e5f6",
  "type": "issue",
  "criticality": "high",
  "product": "Sistema Financeiro",
  "description": "Erro ao emitir boleto",
  "chat_ids": ["67f0c9b8e4b0b1a2c3d4e5f7"],
  "client_id": "0f7d7c4f-7b5b-45cb-9d85-6f3c69f0b5d2"
}
```

### `PATCH /api/tickets/{ticket_id}/status`

Atualiza o status de um ticket existente.

Permissao:
- `ticket:update_status`

Body:

```json
{
  "status": "in_progress"
}
```

## Schemas

### `CreateTicketDTO`

Campos:
- `triage_id: PydanticObjectId`
- `type: TicketType`
- `criticality: TicketCriticality`
- `product: str`
- `description: str`
- `chat_ids: list[PydanticObjectId]`
- `client_id: UUID`

### `CreateTicketResponseDTO`

Campos:
- `id: str`
- `status: TicketStatus`
- `creation_date: datetime`

### `TicketSearchFiltersDTO`

Campos opcionais:
- `ticket_id: PydanticObjectId | None`
- `client_id: UUID | None`
- `triage_id: PydanticObjectId | None`
- `status: TicketStatus | None`
- `criticality: TicketCriticality | None`
- `type: TicketType | None`
- `product: str | None`

### `TicketResponseDTO`

Campos retornados:
- `id`
- `triage_id`
- `type`
- `criticality`
- `product`
- `status`
- `creation_date`
- `description`
- `chat_ids`
- `agent_history`
- `client`
- `comments`

### `UpdateTicketStatusDTO`

Campos:
- `status: TicketStatus`

### `UpdateTicketStatusResponseDTO`

Campos:
- `id`
- `previous_status`
- `current_status`

## Regras de Negocio

### Criacao

Comportamento confirmado:
- o ticket nasce com `status = open`
- `creation_date` e preenchida automaticamente
- `comments` inicia como lista vazia
- `agent_history` inicia como lista vazia
- o cliente e resolvido por `client_id` usando `UserService.get_by_id(...)`
- se o cliente nao existir, a criacao falha com `404`

Observacao tecnica:
- o projeto nao possui hoje um dominio proprio de empresa
- por isso, `TicketCompany` e montado internamente no service com base no usuario resolvido

### Consulta

Comportamento confirmado:
- a consulta usa uma unica rota GET com query params opcionais
- filtros informados sao combinados com AND
- `client_id` filtra por `client.id`
- `ticket_id` filtra pelo `_id` do documento
- `product` usa comparacao exata

### Atualizacao de status

Transicoes validas:

| Status atual | Proximos status validos |
| --- | --- |
| `open` | `in_progress` |
| `in_progress` | `waiting_for_provider`, `waiting_for_validation`, `finished` |
| `waiting_for_provider` | `in_progress` |
| `waiting_for_validation` | `in_progress`, `finished` |
| `finished` | nenhum |

Regras adicionais:
- ticket inexistente retorna `404`
- mesmo status retorna `400`
- transicao invalida retorna `400`

## Formato dos Dados

| Campo | Tipo | Exemplo |
| --- | --- | --- |
| `ticket_id` | ObjectId | `67f0ca60e4b0b1a2c3d4e601` |
| `triage_id` | ObjectId | `67f0c9b8e4b0b1a2c3d4e5f6` |
| `chat_ids[]` | ObjectId | `67f0c9b8e4b0b1a2c3d4e5f7` |
| `client_id` | UUID | `0f7d7c4f-7b5b-45cb-9d85-6f3c69f0b5d2` |
| `type` | enum | `issue`, `access`, `new_feature` |
| `criticality` | enum | `high`, `medium`, `low` |
| `status` | enum | `open`, `in_progress`, `waiting_for_provider`, `waiting_for_validation`, `finished` |
| `product` | string | `Sistema Financeiro` |

## Retornos Possiveis

### `GET /api/tickets/`

- `200`: sucesso com lista de tickets
- `401`: token ausente ou invalido
- `403`: usuario sem `ticket:read`
- `422`: query params invalidos
- `500`: erro inesperado

### `POST /api/tickets/`

- `201`: ticket criado
- `401`: token ausente ou invalido
- `403`: usuario sem `ticket:create`
- `404`: cliente inexistente
- `422`: body invalido
- `500`: erro inesperado

### `PATCH /api/tickets/{ticket_id}/status`

- `200`: status atualizado
- `400`: mesmo status ou transicao invalida
- `401`: token ausente ou invalido
- `403`: usuario sem `ticket:update_status`
- `404`: ticket inexistente
- `422`: `ticket_id` ou body invalidos
- `500`: erro inesperado

## Integracao com a URA

A URA nao deve consumir as rotas HTTP de tickets.

Ponto de entrada recomendado:
- `TicketService.create_ticket(dto)`
- `TicketService.update_status(ticket_id, dto)` quando necessario

Dados que a URA precisa fornecer para criacao:
- `triage_id`
- `type`
- `criticality`
- `product`
- `description`
- `chat_ids`
- `client_id`

Validacoes que continuam existindo na chamada interna:
- `client_id` precisa existir
- enums precisam ser validos
- `triage_id` e `chat_ids` precisam ser ObjectIds validos
- regras de transicao continuam sendo aplicadas

Diferencas para HTTP:
- nao usa autenticacao da rota
- nao usa `ResponseFactoryDep`
- erros devem ser tratados como excecoes Python, principalmente `AppHTTPException`

Exemplo de uso interno:

```python
from app.domains.ticket.schemas import CreateTicketDTO

dto = CreateTicketDTO(
    triage_id="67f0c9b8e4b0b1a2c3d4e5f6",
    type="issue",
    criticality="high",
    product="Sistema Financeiro",
    description="Erro ao emitir boleto",
    chat_ids=["67f0c9b8e4b0b1a2c3d4e5f7"],
    client_id="0f7d7c4f-7b5b-45cb-9d85-6f3c69f0b5d2",
)

result = await ticket_service.create_ticket(dto)
```

## Observacoes Tecnicas

- a nova permissao necessaria para leitura e `ticket:read`
- o seed central deve conter essa permissao para ambientes novos
- a consulta atual usa filtro exato para `product`
- a rota GET retorna tickets completos, nao apenas resumo
