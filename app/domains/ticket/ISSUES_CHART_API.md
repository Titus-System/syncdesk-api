# API do Gráfico Tickets (Falhas) por Produto — Referência para Frontend

Documento de contrato da rota `GET /api/tickets/dashboard/issues-by-product`. Cobre request, response, semântica de cada campo, mapeamento para o gráfico de linhas, casos limite e tratamento de erros.

**Audiência:** equipe de frontend implementando o gráfico de linhas de tickets (falhas) por produto ao longo do tempo.

---

## 1. Visão geral

Rota de **uma única chamada por tela**. Devolve o eixo X (lista de meses), o eixo Y implícito (counts) e uma série por produto.

- **Tipo fixo:** apenas tickets `type=issue` (falhas).
- **Métrica:** tickets que **entraram** (criados) no intervalo, contados pelo `creation_date`. **Inclui finalizados e cancelados** — o que importa é a entrada.
- **Granularidade:** mês civil (ponto por mês).
- **Janela padrão:** últimos 6 meses civis, incluindo o atual.
- **Janela máxima:** 12 meses (proteção).
- **Atualização:** tempo real (sem cache).
- **Escopo:** global por default; filtrável por cliente (`company_id`).

---

## 2. Endpoint

```
GET /api/tickets/dashboard/issues-by-product
```

| Item | Valor |
|---|---|
| Método | `GET` |
| URL | `/api/tickets/dashboard/issues-by-product` |
| Content-Type | `application/json` |
| Status de sucesso | `200 OK` |
| Permissão | `ticket:read` |
| Autenticação | Sessão autenticada (Bearer token) |

---

## 3. Parâmetros de query

| Nome | Tipo | Obrigatório | Default | Descrição |
|---|---|---|---|---|
| `company_id` | UUID | não | — | Quando presente, filtra apenas tickets cujo `client.company.id` for igual. |
| `date_from` | string (ISO 8601, `YYYY-MM-DD`) | não | primeiro dia do mês 5 atrás | Truncada para o **primeiro dia do mês**. |
| `date_to` | string (ISO 8601, `YYYY-MM-DD`) | não | último dia do mês atual | Truncada para o **último dia do mês**. |

Exemplos:

```
GET /api/tickets/dashboard/issues-by-product
GET /api/tickets/dashboard/issues-by-product?company_id=4b8b9bd2-6042-43f5-b5a3-6b36fdfaf9a8
GET /api/tickets/dashboard/issues-by-product?date_from=2026-01-01&date_to=2026-05-31
GET /api/tickets/dashboard/issues-by-product?company_id=...&date_from=2026-01-01&date_to=2026-05-31
```

> Quando só um dos `date_from`/`date_to` for enviado, o outro é completado com o default.

---

## 4. Estrutura da resposta

```ts
type IssuesByProductChartResponse = {
  period_start: string;   // ISO date (YYYY-MM-DD), primeiro dia do primeiro mês
  period_end: string;     // ISO date (YYYY-MM-DD), último dia do último mês
  company_id: string | null;  // eco do filtro
  months: string[];       // eixo X: ex. ["2026-01", "2026-02", ...]
  generated_at: string;   // ISO 8601 UTC do momento da agregação
  series: Array<{
    product: string;
    total: number;        // soma dos counts da série
    points: Array<{
      month: string;      // mesmo formato YYYY-MM, alinhado a `months`
      count: number;      // tickets criados nesse mês
    }>;
  }>;
};
```

Envelope da API (igual ao dashboard):

```json
{
  "data": { /* IssuesByProductChartResponse */ },
  "meta": { "timestamp": "...", "success": true }
}
```

---

## 5. Exemplo completo de resposta

Reproduz o cenário da imagem da equipe de produto (Janeiro–Maio/2026):

```json
{
  "data": {
    "period_start": "2026-01-01",
    "period_end": "2026-05-31",
    "company_id": null,
    "months": ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"],
    "generated_at": "2026-05-19T12:00:00Z",
    "series": [
      {
        "product": "Produto 2",
        "total": 75,
        "points": [
          { "month": "2026-01", "count": 10 },
          { "month": "2026-02", "count": 12 },
          { "month": "2026-03", "count": 16 },
          { "month": "2026-04", "count": 17 },
          { "month": "2026-05", "count": 20 }
        ]
      },
      {
        "product": "Produto 1",
        "total": 61,
        "points": [
          { "month": "2026-01", "count": 12 },
          { "month": "2026-02", "count": 14 },
          { "month": "2026-03", "count": 7 },
          { "month": "2026-04", "count": 18 },
          { "month": "2026-05", "count": 10 }
        ]
      },
      {
        "product": "Produto 3",
        "total": 44,
        "points": [
          { "month": "2026-01", "count": 8 },
          { "month": "2026-02", "count": 8 },
          { "month": "2026-03", "count": 5 },
          { "month": "2026-04", "count": 10 },
          { "month": "2026-05", "count": 13 }
        ]
      }
    ]
  },
  "meta": { "timestamp": "2026-05-19T12:00:00.123Z", "success": true }
}
```

> A ordem do `series` é **total desc** (produto mais "ruidoso" primeiro). Para empates, ordem alfabética por nome.

---

## 6. Referência de campos

### 6.1 Período e eixo X

| Campo | Tipo | Descrição |
|---|---|---|
| `period_start` | ISO date | Primeiro dia do primeiro mês do intervalo (após truncamento). |
| `period_end` | ISO date | Último dia do último mês do intervalo (após truncamento). |
| `months` | string[] | Lista ordenada de meses no formato `YYYY-MM`. Frontend usa **isso** como eixo X — não tente inferir a partir de `series`. Quando não há tickets, ainda vem com todos os meses do range. |
| `generated_at` | ISO datetime UTC | Timestamp da agregação. |

### 6.2 `series`

Lista de produtos com pelo menos 1 ticket no período. **Produtos sem nenhum ticket não aparecem.**

| Campo | Tipo | Notas |
|---|---|---|
| `product` | string | Nome do produto, vindo do snapshot `Ticket.product`. Use como chave de cor/linha. |
| `total` | int `>= 0` | Soma dos `count` dos `points`. Útil para ordenar/exibir total na legenda. |
| `points` | array | **Sempre** com o mesmo comprimento e mesma ordem de `months[]`. Mês sem tickets vem com `count = 0`. |

### 6.3 Invariantes

- `len(series[i].points) === len(months)` para qualquer `i`.
- `series[i].points[k].month === months[k]` (ordens alinhadas).
- `series[i].total === sum(series[i].points[*].count)`.
- `series` ordenada por `total` desc, depois por `product` asc (empate).

---

## 7. Mapeamento direto para o gráfico

| Elemento do gráfico de linhas | Campo da resposta |
|---|---|
| Eixo X (rótulos de mês) | `data.months` |
| Cada linha do gráfico | `data.series[i]` |
| Nome do produto na legenda | `data.series[i].product` |
| Pontos da linha (`x = mês`, `y = count`) | `data.series[i].points[k]` (`month` para X, `count` para Y) |
| Total do produto (legenda/tooltip) | `data.series[i].total` |

Renderização (pseudo):

```ts
chart.xAxis = data.months;  // ["2026-01", ...]
chart.series = data.series.map(s => ({
  name: s.product,
  data: s.points.map(p => p.count),  // alinhado por índice com xAxis
}));
```

---

## 8. Casos limite

### 8.1 Nenhum ticket no período

```json
{
  "data": {
    "period_start": "2026-01-01",
    "period_end": "2026-03-31",
    "company_id": null,
    "months": ["2026-01", "2026-02", "2026-03"],
    "generated_at": "...",
    "series": []
  },
  "meta": { "timestamp": "...", "success": true }
}
```

Frontend deve renderizar o eixo X mesmo sem séries (estado "sem dados no período").

### 8.2 Produto com tickets só em alguns meses

Os meses sem tickets vêm com `count = 0`. **Não há gaps** na série — front renderiza linha contínua com pontos em zero.

### 8.3 Apenas um dos `date_from`/`date_to` enviado

Backend completa o outro com o default. Resposta vem normal.

### 8.4 `company_id` inexistente

Não validamos contra Postgres — o pipeline simplesmente retorna `series=[]`. Frontend trata como "sem dados".

### 8.5 Período fora do passado/futuro

Não há restrição além do tamanho da janela. `date_to` no futuro é aceito (resulta em meses futuros com `count = 0`).

### 8.6 Retrocompatibilidade

Campos podem ser **adicionados** ao response sem aviso. Clientes devem aceitar campos desconhecidos. (Contrato v1.)

---

## 9. Erros

Mesmo envelope do dashboard (RFC 7807 adaptado):

```json
{
  "type": "https://httpstatuses.io/422",
  "title": "Validation Error",
  "status": 422,
  "detail": "...",
  "instance": "/api/tickets/dashboard/issues-by-product",
  "errors": [ /* opcional, presente em 422 */ ],
  "meta": { "timestamp": "...", "success": false }
}
```

| Status | Quando ocorre | Reação do frontend |
|---|---|---|
| `422 Unprocessable Entity` | (a) `date_from > date_to`; (b) range maior que 12 meses (`detail` cita "12"); (c) formato inválido em qualquer query param. | Validar no client antes do request. Mostrar mensagem inline se vier do server. |
| `403 Forbidden` | Sem header `Authorization`, token inválido ou usuário sem `ticket:read`. | Redirecionar para login ou exibir "sem acesso". |
| `500 Internal Server Error` | Falha inesperada no Mongo. | Mensagem genérica + retry. Sem side effects. |

---

## 10. Quick checklist para o frontend

- [ ] Endpoint: `GET /api/tickets/dashboard/issues-by-product` com Bearer token.
- [ ] Defaults funcionam sem nenhum query param → últimos 6 meses, todos os clientes.
- [ ] Para filtrar por cliente: `?company_id={uuid}`.
- [ ] Para janela específica: `?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD` (máx 12 meses).
- [ ] Renderizar eixo X usando `data.months[]` (não tentar inferir a partir de `series`).
- [ ] Cada série é uma linha; cores estáveis por `product` (chave de cor).
- [ ] Aceitar `series=[]` como estado "sem dados no período".
- [ ] Esperar pontos com `count=0` em meses vazios (linha contínua, não interpolar).
- [ ] Tratar 422 → mensagem; 403 → login; 500 → retry.

---

## 11. Versionamento

| Versão | Data | Mudança |
|---|---|---|
| 1.0 | 2026-05-19 | Versão inicial do contrato. |

Próximas evoluções discutidas:
- Outras dimensões de agrupamento (por criticidade, por nível de suporte).
- Granularidade configurável (semana/dia).
- Comparação ano-a-ano.
