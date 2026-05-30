# API do Dashboard de Tickets — Referência para Frontend

Documento de contrato da rota `GET /api/tickets/dashboard`. Cobre request, response, semântica de cada campo, mapeamento para os widgets da tela, casos limite e tratamento de erros.

**Audiência:** equipe de frontend implementando as 3 telas de dashboard (uma por tipo de solicitação: `issue`, `access`, `new_feature`).

---

## 1. Visão geral

A rota é **uma única chamada por tela**. Retorna em um payload tudo o que os 4 KPIs e os 2 donuts precisam.

- Atualização: **tempo real** (cada request executa agregação no Mongo).
- Escopo: **global** (sem filtro de empresa, agente ou janela temporal).
- Resposta independente: cada chamada é stateless e idempotente (`GET`).
- O frontend faz **uma chamada por tipo** (3 telas → 3 requests independentes).

---

## 2. Endpoint

```
GET /api/tickets/dashboard?type={issue|access|new_feature}
```

| Item | Valor |
|---|---|
| Método | `GET` |
| URL | `/api/tickets/dashboard` |
| Content-Type esperado na resposta | `application/json` |
| Códigos de sucesso | `200 OK` |
| Permissão necessária | `ticket:read` |
| Autenticação | Sessão autenticada (mesmo padrão das outras rotas de ticket — `CurrentUserSessionDep`) |

---

## 3. Parâmetros de query

| Nome | Tipo | Obrigatório | Valores aceitos | Descrição |
|---|---|---|---|---|
| `type` | string (enum) | **Sim** | `issue`, `access`, `new_feature` | Filtra a agregação para um único tipo de solicitação. |

Exemplo de URL completa:
```
GET /api/tickets/dashboard?type=issue
GET /api/tickets/dashboard?type=access
GET /api/tickets/dashboard?type=new_feature
```

> Não há paginação, ordenação ou filtros adicionais. Se o frontend precisar de algo a mais, isso será uma evolução de contrato (e o backend será alinhado antes).

---

## 4. Estrutura da resposta

Toda resposta de sucesso vem envelopada no padrão da API:

```json
{
  "data": { /* TicketDashboardResponseDTO */ },
  "meta": {
    "timestamp": "2026-05-18T19:00:00.123Z",
    "success": true
  }
}
```

> Campos `null` no envelope são **omitidos** da serialização (o backend usa `model_dump(exclude_none=True)`). Se houver um `request_id` propagado por middleware (header `X-Request-ID`), ele aparece em `meta.request_id`; senão, o campo simplesmente não vem.

O **payload útil** para o frontend é `data`. O formato é:

```ts
type TicketDashboardResponse = {
  type: "issue" | "access" | "new_feature";
  generated_at: string;  // ISO 8601, UTC
  kpis: {
    open_count: number;
    cancelled_count: number;
    unassigned_count: number;
    overdue_count: number;
  };
  open_breakdown: Array<{
    bucket: "pendente" | "em_atendimento" | "nao_atribuidos";
    label: string;
    count: number;
  }>;
  assigned_breakdown: Array<{
    agent_id: string | null;  // UUID; null apenas no bucket "Outros"
    agent_name: string;
    count: number;
    is_aggregate: boolean;    // true só no bucket "Outros"
  }>;
};
```

---

## 5. Exemplo completo de resposta de sucesso

Resposta correspondendo ao mesmo cenário da tela de referência (190 abertos, 80 cancelados, 110 sem atribuição, 5 vencidos):

```json
{
  "data": {
    "type": "issue",
    "generated_at": "2026-05-18T19:00:00.123Z",
    "kpis": {
      "open_count": 190,
      "cancelled_count": 80,
      "unassigned_count": 110,
      "overdue_count": 5
    },
    "open_breakdown": [
      { "bucket": "pendente",       "label": "Pendente",       "count": 30 },
      { "bucket": "em_atendimento", "label": "Em atendimento", "count": 50 },
      { "bucket": "nao_atribuidos", "label": "Não atribuídos", "count": 110 }
    ],
    "assigned_breakdown": [
      { "agent_id": "4b8b9bd2-6042-43f5-b5a3-6b36fdfaf9a8", "agent_name": "Julia",    "count": 20, "is_aggregate": false },
      { "agent_id": "97f0c9b8-e4b0-41a2-83d4-e5f600000001", "agent_name": "Mafe",     "count": 30, "is_aggregate": false },
      { "agent_id": "0f7d7c4f-7b5b-45cb-9d85-6f3c69f0b5d2", "agent_name": "Angelina", "count": 30, "is_aggregate": false }
    ]
  },
  "meta": {
    "timestamp": "2026-05-18T19:00:00.123Z",
    "success": true
  }
}
```

---

## 6. Referência de campos

### 6.1 `type` e `generated_at`

| Campo | Tipo | Notas |
|---|---|---|
| `type` | string | Eco do filtro `type` da query. Útil para o frontend confirmar que a resposta corresponde à tela carregada (defesa contra request stale). |
| `generated_at` | string (ISO 8601, UTC) | Timestamp do momento em que o backend agregou os dados. Use para exibir "atualizado em…" se desejar. |

### 6.2 `kpis` — 4 cards do topo

Cada KPI é um inteiro `>= 0`. Todos são contagens **independentes**: as 4 podem se sobrepor parcialmente.

| Campo | Significado | Regra de seleção |
|---|---|---|
| `open_count` | "Tickets abertos" | Tickets cujo `status` não é `finished` nem `cancelled`. |
| `cancelled_count` | "Tickets cancelados" | Tickets com `status == "cancelled"`. **Não** está incluído em `open_count`. |
| `unassigned_count` | "Sem atribuição" / "Não atribuídos" | Subconjunto dos **abertos** que **não têm** nenhum agente ativo (nenhum item em `agent_history` com `exit_date == null`). Equivale ao bucket `nao_atribuidos` do donut. |
| `overdue_count` | "Tickets vencidos" | Subconjunto dos **abertos** cujo `creation_date + SLA(criticality)` é menor que o agora do servidor. |

**SLA por criticidade** (usado em `overdue_count`):

| Criticidade | Prazo |
|---|---|
| `high` | 1 dia |
| `medium` | 3 dias |
| `low` | 5 dias |

> `overdue_count` nunca inclui tickets finalizados ou cancelados.
> `unassigned_count` e o bucket `nao_atribuidos` do donut representam o **mesmo conjunto**, apenas exibidos em dois lugares.

### 6.3 `open_breakdown` — donut "Tickets abertos"

Sempre **3 itens**, na ordem `pendente`, `em_atendimento`, `nao_atribuidos`. Mesmo quando todos os contadores são zero, os três itens são retornados (frontend não precisa de tratamento defensivo de ausência).

| `bucket` | `label` (pt-BR) | Status agregados |
|---|---|---|
| `pendente` | `Pendente` | `waiting_for_provider`, `waiting_for_validation` |
| `em_atendimento` | `Em atendimento` | `in_progress` |
| `nao_atribuidos` | `Não atribuídos` | `awaiting_assignment`, `open` |

A soma dos 3 `count` é sempre igual a `kpis.open_count`.

> **Use `bucket` como chave estável** para mapear cores/ícones. `label` é texto pronto para exibição (já vem em pt-BR), mas se o frontend tiver i18n próprio, prefira `bucket` como id.

### 6.4 `assigned_breakdown` — donut "Tickets atribuídos"

Lista dos tickets **abertos com agente ativo**, agrupados pelo agente atualmente atribuído. Ordenada por `count` **decrescente**. Limite de **10 agentes individuais**; o resto é agregado em um único bucket `"Outros"`.

Comprimento da lista: `0 a 11` itens.

| Campo | Tipo | Notas |
|---|---|---|
| `agent_id` | UUID string ou `null` | UUID do agente. `null` **apenas** quando `is_aggregate == true`. |
| `agent_name` | string | Nome do agente ou `"Outros"` no bucket agregado. |
| `count` | int `>= 0` | Quantidade de tickets abertos atribuídos a esse agente (ou somatório do bucket "Outros"). |
| `is_aggregate` | boolean | `true` **somente** no item `"Outros"`. Use isso para diferenciar visualmente (ex.: cinza, sem clique para drill-down). |

**Regras:**

- Tickets **sem** agente ativo **não aparecem** aqui (eles estão em `unassigned_count` / `nao_atribuidos`).
- Tickets `finished` ou `cancelled` **não aparecem** aqui.
- "Agente ativo" = o item mais recente de `agent_history` com `exit_date == null`. Cada ticket aberto pertence a no máximo 1 agente ativo por vez.
- Quando há até 10 agentes distintos: lista tem 1 a 10 itens, todos `is_aggregate == false`.
- Quando há 11+ agentes: lista tem exatamente 11 itens — 10 com `is_aggregate == false` (ordenados desc por `count`) + 1 com `is_aggregate == true` (`"Outros"`, somando os agentes 11+).

A soma de todos os `count` em `assigned_breakdown` é igual a `kpis.open_count - kpis.unassigned_count`.

---

## 7. Mapeamento direto para a tela

Referência rápida — qual campo alimenta cada widget da imagem original:

| Widget na tela | Campo da resposta |
|---|---|
| Card "190 Tickets abertos" | `data.kpis.open_count` |
| Card "80 tickets cancelados" | `data.kpis.cancelled_count` |
| Card "110 sem atribuição" | `data.kpis.unassigned_count` |
| Card "5 Tickets vencidos" | `data.kpis.overdue_count` |
| Donut "Tickets abertos" — centro | `data.kpis.open_count` |
| Donut "Tickets abertos" — fatias | `data.open_breakdown[*]` |
| Donut "Tickets atribuídos" — centro | soma de `data.assigned_breakdown[*].count` (= `open_count - unassigned_count`) |
| Donut "Tickets atribuídos" — fatias | `data.assigned_breakdown[*]` |

---

## 8. Casos limite

### 8.1 Coleção vazia (nenhum ticket do tipo solicitado)

A resposta vem com KPIs zerados, donut de status com os 3 buckets em zero, e donut de agentes como lista vazia:

```json
{
  "data": {
    "type": "issue",
    "generated_at": "2026-05-18T19:00:00.123Z",
    "kpis": {
      "open_count": 0,
      "cancelled_count": 0,
      "unassigned_count": 0,
      "overdue_count": 0
    },
    "open_breakdown": [
      { "bucket": "pendente",       "label": "Pendente",       "count": 0 },
      { "bucket": "em_atendimento", "label": "Em atendimento", "count": 0 },
      { "bucket": "nao_atribuidos", "label": "Não atribuídos", "count": 0 }
    ],
    "assigned_breakdown": []
  },
  "meta": { "timestamp": "...", "success": true }
}
```

> Frontend deve aceitar `assigned_breakdown == []` como "nenhum agente atribuído ainda" e renderizar estado vazio do donut. **Não confundir** com erro.

### 8.2 Sem agentes ativos mas com tickets abertos

Se todos os tickets abertos estão sem assignment (todos em `awaiting_assignment` / `open`), o donut de agentes vem vazio (`[]`), `unassigned_count` reflete o total de abertos, e `nao_atribuidos` no donut de status também.

### 8.3 Empate no top-10

A ordenação é estável apenas por `count` desc. Se houver empate (ex.: dois agentes com 5 tickets cada e ambos no limite do top 10), a ordem dos empatados é determinada pelo Mongo (não garantida). Não dependa de ordenação secundária — se importar, peça um tiebreaker explícito.

### 8.4 Bucket "Outros"

- Sempre o **último** item da lista quando presente.
- `agent_id` é `null` — não use como chave de drill-down.
- Recomendação visual: cor cinza ou estilo distinto, sem link clicável.

### 8.5 Mudanças de status durante a request

A agregação é atômica do ponto de vista do Mongo (`$facet` em uma única pipeline), então KPIs e donuts são consistentes entre si dentro de uma mesma resposta. Mas duas requests consecutivas podem ver estados diferentes — não há cache.

### 8.6 Retrocompatibilidade

Campos podem ser **adicionados** ao response sem aviso. Clientes devem aceitar campos desconhecidos em vez de quebrar. Campos existentes não serão removidos sem versionamento. (No momento da escrita: contrato v1.)

---

## 9. Erros

Erros seguem o padrão da API (inspirado em RFC 7807) com `meta.success = false`. Formato:

```json
{
  "type": "https://httpstatuses.io/422",
  "title": "Validation Error",
  "status": 422,
  "detail": "Request validation failed",
  "instance": "/api/tickets/dashboard",
  "errors": [
    {
      "type": "enum",
      "loc": ["query", "type"],
      "msg": "Input should be 'issue', 'access' or 'new_feature'",
      "input": "foo"
    }
  ],
  "meta": { "timestamp": "...", "success": false }
}
```

Campos do envelope de erro:

| Campo | Conteúdo |
|---|---|
| `type` | URI estável no formato `https://httpstatuses.io/{status_code}`. |
| `title` | Categoria do erro: `Validation Error` (422), `Application Error` (regras de negócio), `HTTP Error` (genérico do framework), `Internal Server Error` (500). |
| `status` | Código HTTP, espelhando o status da resposta. |
| `detail` | Mensagem curta em pt-BR ou en, específica do caso. |
| `instance` | Caminho da request que falhou (ex.: `/api/tickets/dashboard`). |
| `errors` | Lista de detalhes — presente em `422` (validação), omitido em outros. |
| `meta` | Mesmo formato do envelope de sucesso, com `success: false`. Campos `null` são omitidos. |

Erros possíveis nesta rota:

| Status | Quando ocorre | Como o frontend deve reagir |
|---|---|---|
| `422 Unprocessable Entity` | `type` ausente ou com valor inválido (não está em `issue\|access\|new_feature`). O campo `errors` traz os detalhes do pydantic. | Validar no client antes do request. Tratar `errors[*].loc` para apontar campo específico se necessário. |
| `403 Forbidden` | **Sem header `Authorization`** (token ausente), token expirado/inválido, **ou** usuário autenticado mas sem `ticket:read`. A FastAPI Security dep retorna 403 em todos esses cenários. | Inspecionar `detail` para diferenciar: token ausente/inválido → redirecionar para login; sem permissão → exibir estado "sem acesso". |
| `401 Unauthorized` | Raro nesta rota — só ocorre em alguns fluxos internos de validação de token. | Tratar como equivalente a 403 (redirecionar para login). |
| `500 Internal Server Error` | Falha inesperada no Mongo ou no service. `detail` traz mensagem genérica (sem stack trace). | Exibir mensagem genérica e botão de retry. Não há side effects — request pode ser refeito com segurança. |

> **Atenção:** validação de query/body vem com status **422**, não 400. O frontend deve esperar 422 e ler `errors[*]` para feedback granular.

---

## 10. Padrões e detalhes técnicos

- **Datas:** todas em ISO 8601 UTC com sufixo `Z` ou offset `+00:00`. Não há datas locais.
- **UUIDs:** representação string lowercase com hífens (RFC 4122).
- **Encoding:** UTF-8. `label` `"Não atribuídos"` vem com acentos corretos.
- **Idempotência:** `GET` sem efeitos colaterais — pode ser cacheado em camada de rede curta (5–30s) se a UX permitir.
- **Tempo de resposta esperado:** sub-segundo até centenas de milhares de tickets graças ao pipeline `$facet`.
- **Performance:** quanto mais agentes ativos, maior o `assigned_breakdown_raw` interno. Limite de 10+Outros mantém o payload estável (~11 itens no máximo).

---

## 11. Mudanças e versionamento

| Versão | Data | Mudança |
|---|---|---|
| 1.0 | 2026-05-18 | Versão inicial do contrato. |

Próximas evoluções discutidas mas não implementadas:
- Filtro por janela temporal (ex.: últimos 30 dias).
- Filtro por empresa do cliente.
- Endpoint complementar de séries históricas (KPIs ao longo do tempo).

Quando essas vierem, o contrato atual permanece estável; novos parâmetros são opcionais.

---

## 12. Quick checklist para o frontend

- [ ] Fazer 3 requests independentes (`type=issue`, `type=access`, `type=new_feature`).
- [ ] Tratar 401 → login, 403 → estado sem acesso, 500 → retry.
- [ ] KPIs: 4 cards mapeados diretos.
- [ ] Donut 1: iterar `open_breakdown` (sempre 3 buckets, ordem garantida) usando `bucket` como key.
- [ ] Donut 2: iterar `assigned_breakdown` (0–11 itens), aplicar estilo distinto quando `is_aggregate == true`.
- [ ] Aceitar `assigned_breakdown == []` como estado válido (renderizar "nenhum agente atribuído").
- [ ] Não depender de campos `agent_id` para drill-down quando `is_aggregate == true`.
- [ ] Aceitar campos novos no payload sem quebrar (use type-safe deserialization permissiva).
