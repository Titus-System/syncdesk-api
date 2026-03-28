# Live Chat and Conversation Module

## Concurrency and Performance

WebSocket connections are established at `/api/live_chat/room/{chat_id}`. Each connection runs as a separate coroutine on the application's event loop.

The application runs on a single event loop shared across all connections and requests. Coroutines are **concurrent but not parallel**: the event loop executes one coroutine at a time, switching between them at `await` points. This means blocking operations — synchronous I/O, CPU-intensive work — stall the entire event loop and degrade all active connections simultaneously.

Within a single connection, messages are processed sequentially. A second message sent by the same user will not begin processing until the first completes. Messages from other users in the same room are unaffected, as they run in independent coroutines.

The second message is not lost. It is queued in the connection's receive buffer and will be processed after the first message has been fully handled and the coroutine reeturns to the top of the event loop. This ensures messages are handled in order without loss, but it also means that if the first message takes a long time to process, subsequent messages will be delayed.

If a user has, for whatever reason, a message that is taking a long time to process (e.g. an image upload), they can still receive messages from other users as their message is still being processed.


## Chat Management

`ChatManager` is a singleton class responsible for managing active chat rooms, handling user connections, and routing messages to the correct rooms. Chat rooms are created and deleted dynamically as needed.

### In-Memory Chat Rooms

Chat rooms are kept in memory. This assumes the application runs on a single process, which simplifies the architecture and enables fast access with low latency.

Since chat rooms are process-local, they are not shared across processes. If the application is scaled to multiple workers (e.g. via Gunicorn), each worker maintains its own isolated set of chat rooms, which breaks message routing between users connected to different workers.

Chat rooms are also not persistent — they are lost on restart. This is acceptable because messages and conversations are stored in the database; the chat rooms exist only to manage active connections.

### Scaling Considerations

The single-process model is a deliberate tradeoff. Scaling to multiple workers would improve performance under heavy load by distributing connections across CPU cores, but requires replacing the in-memory chat manager with a distributed solution.

The standard approach is a Redis pub/sub broker: when a message arrives, it is published to a Redis channel per room, and each worker subscribes to forward messages to its local connections. This introduces an additional infrastructure dependency but is the conventional solution for horizontally scaled WebSocket applications.

---

## Architecture

The live_chat module is composed of the following main components:

```
live_chat/
├── routers/
│   ├── chat_router.py           # WebSocket endpoints for chat rooms
│   └── conversation_router.py   # HTTP endpoints for conversation CRUD
├── services/
│   └── conversation_service.py  # Business logic for conversations/messages
├── repositories/
│   └── conversation_repository.py # Database access for conversations/messages
├── entities.py                  # Pydantic/Beanie models for Conversation, ChatMessage
├── schemas.py                   # Pydantic DTOs for request/response validation
├── chat_manager.py              # In-memory chat room manager (singleton)
├── dependencies.py              # FastAPI dependency injection wiring
├── exceptions.py                # Domain-specific exceptions
```

### Message Flow

1. **Create Conversation**: Client sends HTTP POST to `/api/conversations/` to create a conversation.
2. **Connect WebSocket**: Client connects to `/api/live_chat/room/{chat_id}` using the conversation ID.
3. **Send/Receive Messages**: Messages are exchanged in real time. Each message is validated (including content size limits via `MAX_CHAT_MESSAGE_CONTENT_SIZE` setting), persisted, and broadcast to all participants in the room.
4. **Room Lifecycle**: Chat rooms are created on demand and deleted when empty.

## Data Models

### Conversation
- `id` (ObjectId): Unique identifier
- `service_session_id` (ObjectId): Associated service session
- `client_id` (UUID): Client user
- `agent_id` (UUID, optional): Agent user
- `parent_id` (ObjectId, optional): Parent conversation (for threading)
- `children_ids` (list[ObjectId]): Child conversations
- `started_at` (datetime): Start timestamp
- `finished_at` (datetime, optional): End timestamp
- `messages` (list[ChatMessage]): List of chat messages

### ChatMessage
- `id` (UUID): Unique message ID
- `conversation_id` (ObjectId): Conversation this message belongs to
- `sender_id` (UUID or "System"): Sender
- `timestamp` (datetime): When sent
- `type` ("text" or "file"): Message type
- `content` (str): Message content or base64-encoded file. Size limited by `MAX_CHAT_MESSAGE_CONTENT_SIZE`
- `mime_type` (str, required for files, forbidden for text): MIME type
- `filename` (str, required for files, forbidden for text): File name
- `responding_to` (UUID, optional): Message being replied to

## Authorization

### HTTP Endpoints

| Endpoint | Permission | Additional Rules |
|---|---|---|
| `GET /service_session/{id}` | `chat:read` | Admins can read any session. Non-admin users must be a participant in the most recent conversation of the session. |
| `POST /` | `chat:create` | Agents and admins can create conversations for any client. Non-admin/non-agent users can only create conversations where `client_id` matches their own ID. |
| `PATCH /{chat_id}/set-agent/{agent_id}` | `chat:set_agent` | First assignment: any user with the permission. Reassignment: only the currently assigned agent or an admin. The target `agent_id` must belong to a user with the "agent" role. |

### WebSocket Endpoints

| Endpoint | Permission | Additional Rules |
|---|---|---|
| `/room/{chat_id}` | `chat:add_message` | Only participants of an **open** conversation can connect. Connection is denied (HTTP 403) if the conversation does not exist, is closed, or the user is not a participant. |

---

## Frontend Integration Guide

### 1. Create a Conversation

Send a POST request to `/api/conversations/` with:

```json
{
	"service_session_id": "<ObjectId>",
	"client_id": "<UUID>",
	"agent_id": "<UUID>",
	"parent_id": "<ObjectId>",
	"sequential_index": 0
}
```

The response contains the `id` field, which is the `chat_id` for the WebSocket.

### 2. Connect to WebSocket

Open a WebSocket connection to:

```
ws://<host>/api/live_chat/room/{chat_id}
```

Only participants of an open conversation can connect. The server responds with HTTP 403 if access is denied.

### 3. Send Messages

Send JSON messages with the following schema:

For text:
```json
{
	"type": "text",
	"content": "Hello world"
}
```
For files (both `mime_type` and `filename` are required):
```json
{
	"type": "file",
	"content": "<base64-data>",
	"mime_type": "application/pdf",
	"filename": "document.pdf"
}
```

### 4. Receive Messages

All messages (including your own) are broadcast to all clients in the room. Success and error responses follow the same structure as HTTP responses, with a `data` or `error` payload.

### 5. Error Handling

If a message is invalid, the server responds with an error message but keeps the connection open. Only unrecoverable protocol violations or disconnects close the connection.

## Known Issues and Limitations

- **Single-process only**: In-memory chat rooms are not shared across processes. Scaling horizontally (multi-worker) requires a distributed broker (e.g., Redis pub/sub).
- **No persistence for chat rooms**: Chat rooms are lost on server restart. Only conversation/message history is persisted in the database.
- **Blocking operations**: Any blocking code in message handlers will stall the event loop and impact all connections.
- **No message delivery guarantees**: If a client disconnects before receiving a message, that message is not re-sent.

## Known Issues and Future Improvements

| Severity  | Issue                                                      | Description                                                                                                                        |
|-----------|------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------|
| 🔴 Critical  | Test WebSocket endpoint unsecured                          | `/test/room/{conversation_id}` has no authentication/authorization; must be removed or secured before production.                  |
| 🔴 High      | No logic for conversations >16MB (MongoDB limit)           | Conversations exceeding 16MB will fail to save; needs pagination or splitting.                                                     |
| 🔴 High      | No treatment for files                                     | File messages are accepted as base64 but not processed; needs HTTP endpoint, storage, and URL generation.                          |
| 🟠 Medium    | No logic to handle the scaling of a conversation           | No implementation for creating child conversations.                                                                                |
| 🔵 Low       | Duplicate parent_id validation                             | Both service and repository check parent existence, causing double DB queries.                                                     |
