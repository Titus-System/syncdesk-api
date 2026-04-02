# Domínio de Tickets

Módulo responsável pela criação e atualização de status de chamados no SyncDesk API.

O domínio persiste tickets no MongoDB via Beanie e expõe duas formas de consumo:
- via API HTTP protegida por autenticação e permissões
- via chamada interna de serviço, pensada para integrações como a URA

## Visão Geral

O módulo `ticket` é responsável por:
- criar tickets com status inicial `open`
- resolver o cliente do ticket a partir de `client_id`
- persistir o documento `Ticket` no MongoDB
- alterar o status do ticket respeitando regras de transição

Dependências relevantes:
- MongoDB + Beanie para persistência do `Ticket`
- domínio `auth` para autenticação, autorização e resolução do cliente via `UserService`
- `ResponseFactoryDep` para envelope padrão de respostas HTTP
- `AppHTTPException` para erros de negócio

## Arquitetura do Módulo

Camadas do domínio:

- `routers.py`
  - recebe requests HTTP
  - aplica autenticação e permissões
  - delega a lógica ao service
  - retorna respostas no envelope padrão do projeto
- `schemas.py`
  - define os contratos de entrada e saída das rotas
- `services.py`
  - implementa a regra de negócio
  - resolve cliente por `client_id`
  - monta `TicketClient` e `TicketCompany`
  - aplica regras de transição de status
- `repositories.py`
  - executa persistência e consulta no MongoDB
- `dependencies.py`
  - monta o `TicketService` com `TicketRepository` e `UserService`
- `models.py`
  - define enums e o documento `Ticket`

## Rotas Disponíveis

### `POST /api/tickets/`

Cria um novo ticket.

| Item | Valor |
| --- | --- |
| Método | `POST` |
| Path | `/api/tickets/` |
| Objetivo | Criar ticket com status inicial `open` |
| Permissão | `ticket:create` |
| Autenticação | Bearer token obrigatório |
| Dependências relevantes | `CurrentUserSessionDep`, `TicketServiceDep`, `ResponseFactoryDep` |
| Schema de entrada | `CreateTicketDTO` |
| Schema de saída | `CreateTicketResponseDTO` em `GenericSuccessContent` |

Exemplo de request:

```http
POST /api/tickets/
Authorization: Bearer <access_token>
Content-Type: application/json
```

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

Exemplo de resposta de sucesso:

```json
{
  "data": {
    "id": "67f0ca60e4b0b1a2c3d4e601",
    "status": "open",
    "creation_date": "2026-04-01T20:15:00.123456Z"
  },
  "meta": {
    "timestamp": "2026-04-01T20:15:00.200000+00:00",
    "success": true,
    "request_id": "b0df8c2e-8d69-4d28-8cdd-8ab75db0b8c4"
  }
}
```

Possíveis erros:
- `401`: token ausente, inválido ou sessão inválida
- `403`: usuário autenticado sem `ticket:create`
- `404`: `client_id` não encontrado
- `422`: body inválido ou campos fora do formato esperado
- `500`: falha inesperada de infraestrutura ou persistência

### `PATCH /api/tickets/{ticket_id}/status`

Atualiza o status de um ticket existente.

| Item | Valor |
| --- | --- |
| Método | `PATCH` |
| Path | `/api/tickets/{ticket_id}/status` |
| Objetivo | Alterar o status de um ticket respeitando as transições válidas |
| Permissão | `ticket:update_status` |
| Autenticação | Bearer token obrigatório |
| Dependências relevantes | `CurrentUserSessionDep`, `TicketServiceDep`, `ResponseFactoryDep` |
| Path param | `ticket_id: PydanticObjectId` |
| Schema de entrada | `UpdateTicketStatusDTO` |
| Schema de saída | `UpdateTicketStatusResponseDTO` em `GenericSuccessContent` |

Exemplo de request:

```http
PATCH /api/tickets/67f0ca60e4b0b1a2c3d4e601/status
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "status": "in_progress"
}
```

Exemplo de resposta de sucesso:

```json
{
  "data": {
    "id": "67f0ca60e4b0b1a2c3d4e601",
    "previous_status": "open",
    "current_status": "in_progress"
  },
  "meta": {
    "timestamp": "2026-04-01T20:20:00.200000+00:00",
    "success": true,
    "request_id": "9d372770-5e6d-4876-a0c8-57b26f613cc3"
  }
}
```

Possíveis erros:
- `401`: token ausente, inválido ou sessão inválida
- `403`: usuário autenticado sem `ticket:update_status`
- `404`: `ticket_id` inexistente
- `400`: status igual ao atual
- `400`: transição inválida
- `422`: body ou `ticket_id` inválidos
- `500`: falha inesperada de infraestrutura ou persistência

## Schemas e Contratos de Dados

### `CreateTicketDTO`

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `triage_id` | `PydanticObjectId` | Sim | ID da triagem | `67f0c9b8e4b0b1a2c3d4e5f6` |
| `type` | `TicketType` | Sim | Tipo do ticket | `issue` |
| `criticality` | `TicketCriticality` | Sim | Criticidade | `high` |
| `product` | `str` | Sim | Nome do produto/sistema | `Sistema Financeiro` |
| `description` | `str` | Sim | Descrição funcional | `Erro ao emitir boleto` |
| `chat_ids` | `list[PydanticObjectId]` | Sim | Chats relacionados | `["67f0c9b8e4b0b1a2c3d4e5f7"]` |
| `client_id` | `UUID` | Sim | ID do cliente no auth | `0f7d7c4f-7b5b-45cb-9d85-6f3c69f0b5d2` |

### `CreateTicketResponseDTO`

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `id` | `str` | Sim | ID do ticket criado |
| `status` | `TicketStatus` | Sim | Status inicial do ticket |
| `creation_date` | `datetime` | Sim | Data/hora de criação |

### `UpdateTicketStatusDTO`

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `status` | `TicketStatus` | Sim | Novo status desejado | `in_progress` |

### `UpdateTicketStatusResponseDTO`

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `id` | `str` | Sim | ID do ticket |
| `previous_status` | `TicketStatus` | Sim | Status anterior |
| `current_status` | `TicketStatus` | Sim | Status persistido após atualização |

## Padrão e Formato de Cada Dado Recebido

| Campo | Tipo real | Formato esperado | Exemplo válido | Observações |
| --- | --- | --- | --- | --- |
| `triage_id` | `PydanticObjectId` | 24 chars hex | `67f0c9b8e4b0b1a2c3d4e5f6` | valor inválido gera `422` |
| `type` | `TicketType` | enum string | `issue` | aceitos: `issue`, `access`, `new_feature` |
| `criticality` | `TicketCriticality` | enum string | `high` | aceitos: `high`, `medium`, `low` |
| `product` | `str` | texto livre | `Sistema Financeiro` | obrigatório |
| `description` | `str` | texto livre | `Erro ao emitir boleto` | obrigatório |
| `chat_ids` | `list[PydanticObjectId]` | lista de ObjectIds | `["67f0c9b8e4b0b1a2c3d4e5f7"]` | lista vazia é aceita pelo código atual |
| `client_id` | `UUID` | UUID canônico | `0f7d7c4f-7b5b-45cb-9d85-6f3c69f0b5d2` | se não existir no auth, retorna `404` |
| `ticket_id` | `PydanticObjectId` | 24 chars hex | `67f0ca60e4b0b1a2c3d4e601` | valor inválido gera `422` |
| `status` | `TicketStatus` | enum string | `in_progress` | depende da transição válida |

Exemplos inválidos úteis:
- `client_id: "abc"` -> `422`
- `triage_id: "123"` -> `422`
- `status: "closed"` -> `422`

## Regras de Negócio

Regras confirmadas pelo código:
- todo ticket novo nasce com status `open`
- `creation_date` é preenchida automaticamente
- `comments` inicia vazio
- `agent_history` inicia vazio
- o cliente é resolvido a partir de `client_id`
- se o cliente não existir, a criação falha com `404`
- não é permitido atualizar para o mesmo status
- não é permitido executar transições fora da tabela `allowed_transitions`
- se o ticket não existir, a atualização falha com `404`

Regra inferida do código:
- `TicketCompany` não vem de um domínio próprio de empresas; ele é sintetizado no service com base no usuário resolvido no auth

## Permissões e Autenticação

Permissões exigidas:

| Operação | Permissão |
| --- | --- |
| Criar ticket | `ticket:create` |
| Atualizar status | `ticket:update_status` |

Autenticação:
- as duas rotas usam `CurrentUserSessionDep`
- portanto exigem bearer token válido
- a verificação de permissão é feita por `require_permission(...)`
- os nomes das permissões precisam bater exatamente com o código

## Todos os Retornos Possíveis das Rotas

### `POST /api/tickets/`

| HTTP | Motivo |
| --- | --- |
| `201` | ticket criado com sucesso |
| `401` | autenticação ausente ou inválida |
| `403` | usuário sem `ticket:create` |
| `404` | `client_id` não encontrado |
| `422` | request inválida ou tipos incompatíveis |
| `500` | erro inesperado |

### `PATCH /api/tickets/{ticket_id}/status`

| HTTP | Motivo |
| --- | --- |
| `200` | status atualizado com sucesso |
| `400` | mesmo status informado |
| `400` | transição inválida |
| `401` | autenticação ausente ou inválida |
| `403` | usuário sem `ticket:update_status` |
| `404` | `ticket_id` inexistente |
| `422` | body inválido ou `ticket_id` malformado |
| `500` | erro inesperado |

Formato aproximado de erro:

```json
{
  "type": "https://httpstatuses.io/400",
  "title": "HTTP Error",
  "status": 400,
  "detail": "Invalid status transition from 'open' to 'finished'.",
  "instance": "/api/tickets/67f0ca60e4b0b1a2c3d4e601/status",
  "meta": {
    "timestamp": "2026-04-01T20:30:00.200000+00:00",
    "success": false,
    "request_id": "..."
  }
}
```

## Exemplos Reais de Uso das Rotas

### Criar chamado de erro no sistema financeiro

```json
{
  "triage_id": "67f0c9b8e4b0b1a2c3d4e5f6",
  "type": "issue",
  "criticality": "high",
  "product": "Sistema Financeiro",
  "description": "Erro ao emitir boleto para cliente final.",
  "chat_ids": ["67f0c9b8e4b0b1a2c3d4e5f7"],
  "client_id": "0f7d7c4f-7b5b-45cb-9d85-6f3c69f0b5d2"
}
```

### Atualizar de `open` para `in_progress`

```json
{
  "status": "in_progress"
}
```

### Atualizar de `in_progress` para `waiting_for_validation`

```json
{
  "status": "waiting_for_validation"
}
```

### Erro: tentar ir de `open` direto para `finished`

```json
{
  "status": "finished"
}
```

Erro esperado: `400`

### Erro: `client_id` inexistente

Exemplo:

```json
{
  "triage_id": "67f0c9b8e4b0b1a2c3d4e5f6",
  "type": "issue",
  "criticality": "high",
  "product": "Sistema Financeiro",
  "description": "Erro ao emitir boleto",
  "chat_ids": ["67f0c9b8e4b0b1a2c3d4e5f7"],
  "client_id": "11111111-1111-1111-1111-111111111111"
}
```

Erro esperado: `404`

### Erro: `ticket_id` inexistente

Exemplo de path:

```http
PATCH /api/tickets/67f0ca60e4b0b1a2c3d4e6ff/status
```

Erro esperado: `404`

## Integração com a URA

### Ponto mais importante

A URA **não deve consumir as rotas HTTP** do domínio `ticket`.

A integração recomendada para a URA é por chamada interna de serviço, usando:
- `TicketService.create_ticket(dto)`
- `TicketService.update_status(ticket_id, dto)` quando necessário

### Ponto de entrada mais adequado

Hoje, o ponto de entrada mais adequado para a URA é a camada de service:
- [services.py](/c:/Users/eduar/OneDrive/Área%20de%20Trabalho/syncdesk-api/app/domains/ticket/services.py)

### Dados que a URA precisa fornecer para criação

Mesmo sem rota HTTP, a URA precisa fornecer os mesmos dados funcionais do `CreateTicketDTO`:
- `triage_id`
- `type`
- `criticality`
- `product`
- `description`
- `chat_ids`
- `client_id`

### Validações que continuam existindo sem uso da rota

Mesmo via chamada direta:
- `client_id` precisa existir no domínio `auth`
- `type` precisa ser um valor válido de `TicketType`
- `criticality` precisa ser um valor válido de `TicketCriticality`
- `triage_id` e `chat_ids` precisam ser `PydanticObjectId` válidos
- o service sempre criará o ticket com `status = open`
- atualizações de status continuam sujeitas às mesmas regras de transição

### Diferenças entre rota HTTP e chamada interna

| Item | Rota HTTP | Chamada interna |
| --- | --- | --- |
| Autenticação | obrigatória | não se aplica por padrão |
| Permissão | obrigatória | depende do chamador interno |
| Validação Pydantic | automática na borda HTTP | deve ser feita ao montar o DTO |
| Envelope de resposta | `response.success(...)` | retorno direto de DTO/objeto |
| Tratamento de erros | HTTP status + payload de erro | exceções Python, especialmente `AppHTTPException` |

### Como a URA deve tratar erros

Ao integrar internamente, a URA ou o fluxo que a invoca deve:
- capturar `AppHTTPException`
- mapear `404` para cliente/ticket inexistente
- mapear `400` para transição inválida ou status repetido
- tratar demais exceções como falhas técnicas

### Exemplo de uso interno para criação

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

Retorno esperado:
- `CreateTicketResponseDTO`

### Exemplo de uso interno para atualização de status

```python
from beanie import PydanticObjectId
from app.domains.ticket.schemas import UpdateTicketStatusDTO

ticket_id = PydanticObjectId("67f0ca60e4b0b1a2c3d4e601")
dto = UpdateTicketStatusDTO(status="in_progress")

result = await ticket_service.update_status(ticket_id, dto)
```

Retorno esperado:
- `UpdateTicketStatusResponseDTO`

### Cuidados para a URA

- não enviar strings arbitrárias para enums
- validar `client_id` como UUID antes de montar o DTO
- validar `triage_id` e `chat_ids` como ObjectIds válidos
- não depender do envelope HTTP para interpretar sucesso/erro
- usar a mesma lógica central do `TicketService`, sem duplicar regras

## Fluxos Práticos

### Fluxo: criar ticket

1. Receber `triage_id`, `client_id`, `chat_ids` e dados funcionais.
2. Montar `CreateTicketDTO`.
3. Chamar `TicketService.create_ticket(dto)`.
4. O service resolve o cliente no auth.
5. O service cria o ticket com status `open`.
6. O repository persiste no MongoDB.
7. O chamador recebe `id`, `status` e `creation_date`.

### Fluxo: atualizar para atendimento em andamento

1. Receber `ticket_id`.
2. Montar `UpdateTicketStatusDTO(status="in_progress")`.
3. Chamar `update_status`.
4. O service valida existência e transição.
5. O repository persiste o novo status.

### Fluxo: mover para `waiting_for_validation`

1. Garantir que o ticket esteja em `in_progress`.
2. Chamar atualização para `waiting_for_validation`.
3. Persistir com sucesso.

### Fluxo: finalizar ticket

1. Garantir que o ticket esteja em `in_progress` ou `waiting_for_validation`.
2. Chamar atualização para `finished`.
3. Persistir com sucesso.

### Fluxo inválido

1. Ticket está em `open`.
2. Chamador tenta `finished`.
3. Service rejeita com `400`.
4. Nenhuma alteração é persistida.
