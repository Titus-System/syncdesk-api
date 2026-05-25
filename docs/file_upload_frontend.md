# Integração frontend ↔ backend para arquivos no chat

Este documento descreve **exatamente** o que o frontend (web ou mobile) precisa fazer para enviar e exibir arquivos em mensagens do chat e como funciona o fluxo de avatar. É o complemento prático de [`docs/file_upload.md`](file_upload.md), que cobre a arquitetura interna.

Toda integração assume que o usuário **já está autenticado** (Bearer token JWT no header `Authorization` em todas as chamadas REST e no handshake do WebSocket).

---

## 1. Visão geral do pipeline

Independente de contexto (chat ou avatar), o fluxo de **upload** é sempre o mesmo, em 3 passos:

```
┌────────────┐  1. presign  ┌─────────────┐
│  Frontend  │ ───────────► │   Backend   │  gera URL + policy
│            │              └─────────────┘
│            │  2. POST file
│            │ ─────────────► MinIO (S3)   sobe os bytes direto
│            │
│            │  3. confirm  ┌─────────────┐
│            │ ───────────► │   Backend   │  head_object + transição
└────────────┘              └─────────────┘
```

E o de **leitura**:

```
┌────────────┐  GET download-url  ┌─────────────┐
│  Frontend  │ ───────────────────►│   Backend   │  retorna URL presigned (5 min)
│            │                     └─────────────┘
│            │  GET <download URL>
│            │ ───────────────────► MinIO         baixa direto, sem passar pela API
└────────────┘
```

A API **nunca** streama bytes — sempre devolve URLs presigned com validade curta.

---

## 2. Endpoints REST

Todos usam o envelope padrão `{ "data": ..., "meta": { "success": true } }` em sucesso. Em erro, `data` é substituído por `detail` e `meta.success` é `false`.

### 2.1 `POST /api/files/presign-upload`

Inicia o upload. Devolve uma URL assinada para o frontend `POST`ar os bytes direto no MinIO.

**Request**:

```json
{
  "filename": "foto.png",
  "content_type": "image/png",
  "size_bytes": 12345,
  "context": "live_chat_message" | "user_avatar",
  "context_ref": { "conversation_id": "<ObjectId>" }
}
```

- `filename`: 1–255 chars, sem `/` nem `..`.
- `content_type`: deve estar na allow-list do contexto (seção 6).
- `size_bytes`: tamanho exato em bytes; **se mentir, o MinIO rejeita o upload**.
- `context`: `"live_chat_message"` ou `"user_avatar"` (mais contextos não são aceitos).
- `context_ref`:
  - Para `live_chat_message`: obrigatório `{ "conversation_id": "<id da conversa>" }`. O usuário precisa ser participante da conversa, senão retorna 403.
  - Para `user_avatar`: pode mandar `{}` (vazio).

**Response 201**:

```json
{
  "data": {
    "file_id": "8a4b...-uuid",
    "upload_url": "https://files.syncdesk.pro/syncdesk-files",
    "method": "POST",
    "fields": {
      "key": "live_chat/<conv_id>/<file_id>-<slug>",
      "policy": "...",
      "x-amz-algorithm": "AWS4-HMAC-SHA256",
      "x-amz-credential": "...",
      "x-amz-date": "...",
      "x-amz-signature": "..."
    },
    "expires_at": "2026-05-25T10:35:00+00:00",
    "max_size_bytes": 26214400
  }
}
```

**Erros**:

- `400`: tipo de arquivo não permitido, tamanho excede o limite, contexto inválido ou `context_ref` faltando.
- `403`: usuário não é participante da conversa (apenas `live_chat_message`).
- `401`: token inválido/ausente.

### 2.2 `POST <upload_url>` (direto no MinIO, não na API)

Esse é o **único** passo que vai direto pro MinIO, não pra API.

```
POST https://files.syncdesk.pro/syncdesk-files
Content-Type: multipart/form-data
```

O corpo é um multipart com **todos os `fields` retornados pelo presign como campos**, e o arquivo **como último campo, com `name="file"`**.

A ordem importa — política do S3 exige que `file` venha por último.

**Sucesso**: `204 No Content` (ou `200`/`201` dependendo da config).

**Erros comuns**:

- `400` com `EntityTooLarge`: `size_bytes` declarado no presign não bate com o upload real.
- `403` com `SignatureDoesNotMatch`: algum field foi modificado, ou o `content_type` do upload é diferente do declarado.
- `400` com `EntityTooSmall`: arquivo vazio.

### 2.3 `POST /api/files/{file_id}/confirm`

Após o upload no MinIO chegar a `204`, chame isso pra que o backend valide o `head_object` e transicione o status de `pending` → `uploaded`. **Só depois desse passo o file_id pode ser usado em mensagens.**

**Response 200**:

```json
{
  "data": { "file_id": "8a4b...", "status": "uploaded" }
}
```

**Erros**:

- `409 Conflict`: bytes ainda não chegaram no MinIO (cliente esqueceu o passo 2.2) ou o storage caiu. Pode tentar de novo após o upload completar.
- `403`: usuário não é o uploader.
- `404`: file_id não existe.

### 2.4 `GET /api/files/{file_id}/download-url`

Pede uma URL presigned para baixar.

**Response 200**:

```json
{
  "data": {
    "url": "https://files.syncdesk.pro/syncdesk-files/<key>?X-Amz-Algorithm=...&X-Amz-Signature=...&X-Amz-Expires=300",
    "expires_at": "2026-05-25T10:35:00+00:00"
  }
}
```

O frontend usa essa `url` direto em `<img src>`, `<video src>`, `<audio src>` ou `fetch`. Não precisa autenticar — a assinatura no query string já autoriza.

**Autorização**:

- Para `live_chat_message`: o usuário precisa ser **participante da conversa** OU ter role `admin`. Caso contrário, `403`.
- Para `user_avatar`: qualquer usuário autenticado pode pedir.

**Erros**:

- `404`: file_id desconhecido ou ainda em `pending`/`deleted`.
- `403`: usuário não tem permissão (ver acima).

### 2.5 `DELETE /api/files/{file_id}`

Soft-delete. O blob continua no MinIO até o job de retenção; do ponto de vista do frontend, o arquivo "some" (download URL passa a dar 404).

**Response 200**:

```json
{
  "data": { "file_id": "8a4b...", "status": "deleted" }
}
```

**Autorização**: apenas o uploader ou um admin.

---

## 3. Enviando um arquivo no chat (passo a passo)

Cenário: usuário escolheu um PDF para anexar numa conversa.

### Passo 1 — Presign

```ts
const presign = await fetch(`${API_BASE}/api/files/presign-upload`, {
  method: "POST",
  headers: {
    "Authorization": `Bearer ${accessToken}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    filename: file.name,
    content_type: file.type,           // ex: "application/pdf"
    size_bytes: file.size,
    context: "live_chat_message",
    context_ref: { conversation_id: conversationId },
  }),
});

if (!presign.ok) {
  // Trate 400 (tipo/tamanho), 403 (não participante), 401, etc.
  throw new Error(`Presign falhou: ${presign.status}`);
}

const { data } = await presign.json();
const { file_id, upload_url, fields } = data;
```

### Passo 2 — Upload direto no MinIO

```ts
const formData = new FormData();
// IMPORTANTE: todos os fields PRIMEIRO, file por ÚLTIMO.
for (const [k, v] of Object.entries(fields)) {
  formData.append(k, v as string);
}
formData.append("file", file);

const uploadResp = await fetch(upload_url, {
  method: "POST",
  body: formData,
  // NÃO passar Authorization aqui — a URL é presigned.
});

if (!uploadResp.ok) {
  // 400 EntityTooLarge / 403 SignatureDoesNotMatch
  const body = await uploadResp.text();
  throw new Error(`Upload MinIO falhou: ${uploadResp.status} ${body}`);
}
```

### Passo 3 — Confirm

```ts
const confirm = await fetch(`${API_BASE}/api/files/${file_id}/confirm`, {
  method: "POST",
  headers: { "Authorization": `Bearer ${accessToken}` },
});

if (!confirm.ok) {
  // 409: tente de novo após o upload propagar; raríssimo.
  throw new Error(`Confirm falhou: ${confirm.status}`);
}
```

### Passo 4 — Enviar a mensagem via WebSocket

A esta altura o `file_id` está `uploaded` e pode ser referenciado. No socket aberto em `/api/live_chat/room/{chat_id}`:

```ts
ws.send(JSON.stringify({
  type: "file",
  content: "Anexei o arquivo solicitado",  // texto livre que acompanha
  filename: file.name,
  mime_type: file.type,
  file_id: file_id,
}));
```

**Regras estritas para `type=file`**:

- `mime_type`, `filename` e `file_id` são **todos obrigatórios**. Faltando qualquer um, o servidor responde com erro WS código `1003` e a mensagem **não** é entregue.
- O `file_id` precisa:
  - Ter sido confirmado (`status=uploaded`)
  - Pertencer ao próprio sender
  - Ter sido criado com `context=live_chat_message`
  - Ter sido criado para **esta mesma conversa** (o backend valida o `conversation_id` embutido no `object_key`)
- Para `type=text`, `mime_type`, `filename` e `file_id` **não podem ser enviados**. Se vierem, o servidor rejeita.

### Passo 5 — Recebimento (do lado do sender e dos outros participantes)

Todos os WS abertos na mesma conversa recebem o broadcast:

```json
{
  "data": {
    "id": "<message UUID>",
    "conversation_id": "<conv ObjectId>",
    "sender_id": "<user UUID>",
    "type": "file",
    "content": "Anexei o arquivo solicitado",
    "filename": "foo.pdf",
    "mime_type": "application/pdf",
    "file_id": "<file UUID>",
    "timestamp": "2026-05-25T10:30:00+00:00"
  },
  "meta": { "success": true }
}
```

O frontend usa o `file_id` para pedir o download URL (próxima seção).

---

## 4. Exibindo um arquivo recebido

Quando uma mensagem `type=file` chega (seja em tempo real via WS ou via paginação do histórico), o frontend pega o `file_id` e:

```ts
const dl = await fetch(`${API_BASE}/api/files/${file_id}/download-url`, {
  headers: { "Authorization": `Bearer ${accessToken}` },
});
const { data } = await dl.json();
// data.url é uma URL presigned, válida por 5 minutos
```

E usa `data.url` diretamente:

```tsx
{mime_type.startsWith("image/") && <img src={data.url} alt={filename} />}
{mime_type.startsWith("audio/") && <audio src={data.url} controls />}
{mime_type === "application/pdf" && (
  <a href={data.url} target="_blank" rel="noopener">Abrir PDF</a>
)}
```

**Importante**: a URL é one-time-ish (válida 5 min). Se o usuário deixar a aba aberta por mais tempo e clicar pra ver o anexo, é melhor **rebuscar** a URL no clique do que segurar a versão antiga.

---

## 5. Paginação do histórico

Conversas antigas trazem mensagens com `file_id` já preenchido na rota:

```
GET /api/conversations/ticket/{ticket_id}/messages?page=1&limit=50
```

Cada mensagem `type=file` no JSON da resposta vem com `file_id` (UUID string) e os outros campos. O frontend faz o mesmo `GET /api/files/{file_id}/download-url` para exibir.

**Compatibilidade com mensagens antigas**: documentos anteriores à introdução do `file_id` chegam com `file_id: null` (campo opcional). Se sua UI já lidava com `type=file` antes (improvável, pois esse caminho não estava em uso), trate `file_id: null` como "anexo não-acessível".

---

## 6. Validação de tipos e tamanhos (allow-list)

Aplicada no presign — `400 Bad Request` se violar.

| Contexto | MIME types permitidos | Tamanho máx |
|---|---|---|
| `live_chat_message` | `image/png`, `image/jpeg`, `image/webp`, `image/gif`, `application/pdf`, `audio/mpeg`, `audio/ogg`, `audio/webm` | 25 MiB |
| `user_avatar` | `image/png`, `image/jpeg`, `image/webp` | 2 MiB |

Validar no frontend antes do presign (para feedback rápido) é boa prática, mas o backend é a fonte da verdade.

---

## 7. Fluxo de avatar (user_avatar)

Idêntico ao do chat, com 3 diferenças:

1. `context: "user_avatar"`, `context_ref: {}` no presign.
2. Não há mensagem de chat — depois do confirm, o frontend simplesmente atualiza o perfil do usuário (a integração com `users.avatar_file_id` é a próxima PR; até lá, o `file_id` precisa ser guardado no client).
3. Qualquer usuário autenticado pode pedir download de qualquer avatar (não há restrição de participação).

**Object key determinístico**: cada usuário tem um único avatar persistente em `avatars/users/{user_id}.{ext}`. Trocar de avatar simplesmente sobrescreve o blob anterior no MinIO (o registro antigo no DB fica como `deleted`, o novo como `uploaded`). Não é preciso deletar manualmente o avatar antigo antes de subir um novo.

---

## 8. Códigos de erro do WebSocket

Em respostas com `meta.success: false`, o campo `status` carrega o close code WebSocket:

| `status` | Significado | Como tratar |
|---|---|---|
| `1003` | Payload inválido — validação de schema, file_id rejeitado, etc. | Mostrar erro ao usuário; conexão continua aberta. |
| `1008` | Violação de política (tamanho excede settings, etc.) | Avisar usuário, conexão continua aberta. |
| `1011` | Erro interno (storage indisponível, etc.) | Tentar de novo; pode precisar reabrir o socket. |

Especificamente para anexos de arquivo, mensagens 1003 vão trazer no `detail` strings como:

- `file_id does not reference a known file`
- `file_id was not uploaded by the sender`
- `file_id has context 'user_avatar', expected 'live_chat_message'`
- `file_id has status 'pending', expected 'uploaded'`
- `file_id belongs to a different conversation`
- `mime_type, filename and file_id are required when type='file'`

Use o `detail` para decidir a UI (ex.: "Confirme o upload antes de enviar" para `status 'pending'`).

---

## 9. Cheat sheet de UX

- **Não envie o arquivo via WS direto**. O canal WS é só para a mensagem que **referencia** o `file_id`. Os bytes vão por HTTP multipart para o MinIO, antes.
- **Não tente reaproveitar `file_id` entre conversas**. Cada anexo é amarrado à conversa em que foi presigned. Reuso é rejeitado.
- **Cuidado com retry de presign**. Se o usuário cancelar o upload depois do presign mas antes do confirm, o `file_id` fica órfão no DB com `status=pending`. Um job de retenção limpa esses depois (PR5); do lado do frontend, basta gerar um novo presign.
- **Exibição com `<img>` não precisa de CORS**, mas `fetch()` precisa. O backend libera todas as origens via `MINIO_API_CORS_ALLOW_ORIGIN=*` em staging.
- **URLs expiram**. Não cacheie a URL de download por mais de uns poucos minutos. Para anexos persistentes na UI, mantenha o `file_id` e refaça o pedido de download URL on-demand.
