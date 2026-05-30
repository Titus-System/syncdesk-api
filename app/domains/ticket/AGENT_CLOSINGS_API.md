# API do Gráfico de Encerramentos por Atendente — Referência para Frontend

Documento de contrato da rota `GET /api/tickets/dashboard/agent-closings`. Cobre request, response, semântica de cada campo, mapeamento para o gráfico de barras horizontais, casos limite e erros.

**Audiência:** equipe de frontend implementando o gráfico de tickets encerrados por agente (3 barras por agente, uma por tipo de ticket).

---

## 1. Visão geral

- Rota de **uma única chamada por tela**.
- Devolve uma lista de agentes; cada agente tem 3 contadores (`issue_count`, `access_count`, `new_feature_count`) + `total`.
- **"Encerrou"** = tickets com `status = finished` cuja transição foi feita via `update_ticket` ou `update_status` (rota legacy). Cancelados **não** entram.
- Janela = mês civil definido por `month` + `year`. Default = mês/ano atual.
- Limite: top 10 agentes por total + bucket `Outros` (mesmo padrão dos outros dashboards).

---

## 2. Endpoint

```
GET /api/tickets/dashboard/agent-closings
```

| Item | Valor |
|---|---|
| Método | `GET` |
| Permissão | `ticket:read` |
| Resposta | `GenericSuccessContent[AgentClosingsChartResponseDTO]` |

---

## 3. Parâmetros de query

| Nome | Tipo | Obrigatório | Default | Descrição |
|---|---|---|---|---|
| `month` | int (1–12) | não | mês corrente UTC | Mês do encerramento (filtra `closed_at`). |
| `year` | int (≥2000, ≤2100) | não | ano corrente UTC | Ano do encerramento. |
| `level` | enum (`N1` \| `N2` \| `N3`) | não | — | Filtra por nível **do agente** que encerrou (snapshot). |

Exemplos:

```
GET /api/tickets/dashboard/agent-closings
GET /api/tickets/dashboard/agent-closings?month=5&year=2026
GET /api/tickets/dashboard/agent-closings?month=5&year=2026&level=N2
GET /api/tickets/dashboard/agent-closings?level=N3
```

---

## 4. Estrutura da resposta

```ts
type AgentClosingsChartResponse = {
  month: number;               // 1..12 (eco do filtro, ou mês corrente)
  year: number;                // yyyy (eco ou ano corrente)
  level: "N1" | "N2" | "N3" | null;  // eco do filtro
  generated_at: string;        // ISO 8601 UTC

  agents: Array<{
    agent_id: string | null;   // UUID; null apenas em "Outros"
    agent_name: string;
    issue_count: number;       // "Ticket" (azul) no gráfico
    access_count: number;      // "Liberação de acesso" (laranja)
    new_feature_count: number; // "Features" (roxo)
    total: number;             // soma dos 3 counters
    is_aggregate: boolean;     // true apenas no bucket "Outros"
  }>;
};
```

Envelope:

```json
{
  "data": { /* ... */ },
  "meta": { "timestamp": "...", "success": true }
}
```

---

## 5. Exemplo completo

Reproduz o cenário da imagem da equipe de produto:

```json
{
  "data": {
    "month": 5,
    "year": 2026,
    "level": null,
    "generated_at": "2026-05-19T12:00:00Z",
    "agents": [
      {
        "agent_id": "0f7d7c4f-7b5b-45cb-9d85-6f3c69f0b5d2",
        "agent_name": "Angelina",
        "issue_count": 4000,
        "access_count": 7000,
        "new_feature_count": 2500,
        "total": 13500,
        "is_aggregate": false
      },
      {
        "agent_id": "4b8b9bd2-6042-43f5-b5a3-6b36fdfaf9a8",
        "agent_name": "Julia",
        "issue_count": 2200,
        "access_count": 5000,
        "new_feature_count": 1200,
        "total": 8400,
        "is_aggregate": false
      },
      {
        "agent_id": "97f0c9b8-e4b0-41a2-83d4-e5f600000001",
        "agent_name": "Mafe",
        "issue_count": 3200,
        "access_count": 2000,
        "new_feature_count": 1700,
        "total": 6900,
        "is_aggregate": false
      }
    ]
  },
  "meta": { "timestamp": "...", "success": true }
}
```

> Agentes ordenados por `total` desc, com empate desempate por `agent_name` asc.

---

## 6. Mapeamento direto para o gráfico

| Elemento do gráfico | Campo da resposta |
|---|---|
| Eixo Y (rótulo do agente) | `agents[i].agent_name` |
| Barra azul ("Ticket") | `agents[i].issue_count` |
| Barra roxa ("Features") | `agents[i].new_feature_count` |
| Barra laranja ("Liberação de acesso") | `agents[i].access_count` |
| Label de total / tooltip | `agents[i].total` |
| Filtro de mês exibido | `month` (1-12) |
| Filtro de ano exibido | `year` |

Renderização (pseudo):

```ts
chart.yAxis = data.agents.map(a => a.agent_name);
chart.series = [
  { name: "Ticket",              data: data.agents.map(a => a.issue_count) },
  { name: "Features",            data: data.agents.map(a => a.new_feature_count) },
  { name: "Liberação de acesso", data: data.agents.map(a => a.access_count) },
];
```

---

## 7. Regras de inclusão e exclusão

### Inclui

- Tickets com `status = finished`
- Cuja transição foi feita via `PATCH /api/tickets/{id}` (preferida) ou `PATCH /api/tickets/{id}/status` (legacy)
- Dentro do range `[primeiro dia do mês, primeiro dia do mês seguinte)` em UTC
- Com `closed_by_agent` populado (havia agente ativo na hora do fechamento)
- Opcionalmente, com `closed_by_agent.level == level` quando filtro fornecido

### Exclui

- `status = cancelled` (cancelados não contam como encerramento)
- `status = open`, `awaiting_assignment`, `in_progress`, `waiting_for_*` (não terminais)
- Tickets antigos do banco que foram finalizados **antes** desse PR e não têm `closed_at` ou `closed_by_agent` populado
- Tickets finalizados **sem** agente ativo no momento (rara, mas possível via PATCH genérico) — ficam fora do gráfico porque não há a quem atribuir

> **Implicação**: o total de tickets do agente no gráfico **pode ser menor** que o total real de tickets `finished` do período se houver tickets legacy ou sem agente. Isso é por design.

---

## 8. Casos limite

### 8.1 Nenhum encerramento no período

```json
{
  "data": {
    "month": 5,
    "year": 2026,
    "level": null,
    "generated_at": "...",
    "agents": []
  },
  "meta": { "timestamp": "...", "success": true }
}
```

Front renderiza estado vazio.

### 8.2 Período no futuro

Aceito. Retorna `agents: []`. Não há erro de validação.

### 8.3 Bucket "Outros"

Quando há mais de 10 agentes:
- Lista tem exatamente 11 entradas (10 individuais + 1 "Outros").
- "Outros" é sempre o **último** item.
- `agent_id` é `null` — não use como chave de drill-down.
- Counters por tipo são somas dos agentes fora do top 10.
- Recomendação visual: cor cinza, sem clique.

### 8.4 Agente com apenas um tipo de ticket

Os outros counters vêm com `0`. Front renderiza barras de tamanho zero (ou omite, conforme design).

### 8.5 Filtro de nível com 0 matches

`agents: []`. Mesmo tratamento de "Nenhum encerramento".

### 8.6 Snapshot vs estado atual do agente

`agent_name` e o `level` filtrado refletem o **snapshot** do agente no momento do fechamento. Se o agente mudou de nível depois, o filtro `level=N1` ainda traz fechamentos antigos quando o agente era N1.

---

## 9. Erros

Mesmo padrão dos outros dashboards.

| Status | Quando ocorre | Reação do frontend |
|---|---|---|
| `422 Unprocessable Entity` | `month` fora de [1,12], `year` fora de [2000,2100], `level` fora de N1/N2/N3, ou tipo inválido. | Validar no client antes do request. |
| `403 Forbidden` | Sem `Authorization` ou sem `ticket:read`. | Redirecionar para login ou exibir "sem acesso". |
| `500 Internal Server Error` | Falha inesperada. | Mensagem genérica + retry. |

---

## 10. Quick checklist para o frontend

- [ ] `GET /api/tickets/dashboard/agent-closings` com Bearer token.
- [ ] Defaults: `month`/`year` = mês/ano atual.
- [ ] Renderizar 3 séries de barras por agente, na ordem: **Ticket** (issue), **Features** (new_feature), **Liberação de acesso** (access).
- [ ] Agentes ordenados como vêm no payload (total desc).
- [ ] Tratar `agents=[]` como "sem encerramentos no período".
- [ ] "Outros" sempre por último, sem drill-down.
- [ ] Tratar 422 → mensagem, 403 → login, 500 → retry.

---

## 11. Versionamento

| Versão | Data | Mudança |
|---|---|---|
| 1.0 | 2026-05-19 | Versão inicial do contrato. |
