## Conversation vs Chat

* **Conversation**: A conversation is a persistent record of an interaction between a client and an agent. It contains metadata such as participants, timestamps, and message history. Conversations are stored in the database and have a unique `chat_id` (ObjectId).

* **Chat**: A chat refers to the real-time exchange of messages that occurs within a conversation. The chat happens over a WebSocket connection that is associated with a specific conversation (`chat_id`).

> The conversation_id is used to validate and authorize access to the WebSocket chat room. Only participants of the conversation can connect to the corresponding chat room and exchange messages.

> For the sake of simplicity, the conversation_id is the same as the chat_id, since the chat rooms are not persisted in the database and are directly tied to the conversation records.


## Starting a Chat

Before connecting to the WebSocket, the user **must create a conversation**. The `chat_id` used in the WebSocket URL corresponds to the ID of the open conversation.

### 1. Create a conversation

Send an HTTP `POST` request to `/api/conversations/` with the following payload:

```json
{
  "ticket_id": "<ObjectId of the ticket>",
  "client_id": "<UUID of the client user>",
  "agent_id": "<UUID of the agent>", // optional
  "parent_id": "<ObjectId of the parent conversation>", // optional
  "sequential_index": 0 // optional, used for threading/scaled conversations
}
```

**Success response:**

```json
{
  "data": {
    "id": "6601e2b8e1b2c8a1f0a1b2c3", // <--- chat_id/conversation_id
    "ticket_id": "65f0e2b8e1b2c8a1f0a1b2c2",
    "client_id": "b1e2b8e1-b2c8-a1f0-a1b2-c3d4e5f6a7b8",
    "agent_id": "c2e3b9e2-b3c9-a2f1-b2c3-d4e5f6a7b8c9",
    "sequential_index": 0,
    "parent_id": null,
    "children_ids": [],
    "started_at": "2026-03-25T12:00:00Z",
    "finished_at": null
  },
  "meta": {
    "timestamp": "2026-03-25T21:58:35.229069+00:00",
    "success": true,
    "request_id": "e44ca66a-b86c-46fe-89cb-e82752ab3cdc"
  }
}
```

The `data.id` field is the `conversation_id` (ObjectId) that will be used to open the WebSocket.

### 2. Connect to the WebSocket

Open the connection to:

```
ws://<host>/api/live_chat/room/{chat_id}
```
> Use the `conversation_id` obtained in step 1 as the `{chat_id}` in the URL.
> 
> The user will only be able to connect if they are a participant in the conversation (client or agent).

### 3. Send and receive messages

After connecting, send messages according to the schema documented below. All messages and responses use the `chat_id` obtained in step 1.

---

## Connection Lifecycle

### 1. Client connects

The client opens a WebSocket connection to:

```
/api/live_chat/room/{chat_id}
```

If the conversation exists (or is created implicitly), the server registers the client in the room and begins streaming messages.

Immediately after joining, the server sends a system confirmation message to the newly connected client indicating that the room join succeeded.

Example:

```json
{
  "data": {
    "id": "6601e2b8e1b2c8a1f0a1b2c3",
    "conversation_id": "6601e2b8e1b2c8a1f0a1b2c3",
    "sender_id": "System",
    "timestamp": "2026-03-22T01:53:44Z",
    "type": "text",
    "content": "Joined to chat room 4634862c-af46-4bcd-b793-d39e4e37bb12"
  },
  "meta": {
    "timestamp": "2026-03-25T21:58:35.229069+00:00",
    "success": true,
    "request_id": "request-id"
  }
}
```

---

### 2. Client → Server Messages

The client sends chat messages using the following schema:

```json
{
  "type": "text",
  "content": "Hello world",
  "mime_type": "text/plain",
  "filename": "optional-file-name.txt",
  "responding_to": "optional-message-objectid"
}
```

> If type or content are missing, the server responds with an error message: "Payload missing required fields: type, content".
>
> if the payload contains extra fields, the server ignores them and processes the message as normal.
> 
> if type is not "text" or "file", the server responds with an error message: "Input should be 'text' or 'file'".
> 
> if type is "file", the content field should contain the file data encoded as a base64 string, and the mime_type field should specify the MIME type of the file (e.g., "application/pdf"). The filename field is optional but can be included to provide the original name of the file.
> If the filename is not provided for a file message, the server assigns a default filename.
> 
> If type is "text", the mime_type and filename field must not be included. If they are included, the server responds with an error message: "Invalid payload for text message. mime_type and filename fields are not allowed for text messages".
>


### Fields

| Field   | Type   | Required | Description                                      |
| ------- | ------ | -------- | ------------------------------------------------ |
| type    | "text" or "file" | yes      | Message type (either "text" or "file") |
| content | string | yes      | Message body                                     |
| mime_type | string | no       | MIME type of the content (e.g., `text/plain`)    |
| filename | string | no       | Original file name if the message contains a file |
| responding_to | string | no       | ObjectId (24-char hex) of the message being replied to (if applicable) |

---

#### Note on MIME Types

> A MIME type (Multipurpose Internet Mail Extensions) is a label that identifies the format of a file or data. It tells the receiver how to interpret the content being transferred.
> 
> Format: `type/subtype` — e.g., `text/html`, `application/json`, `image/png`.
>
>Common examples:
>
>| MIME Type | Meaning |
>|---|---|
>| `text/plain` | Plain text |
>| `text/html` | HTML document |
>| `application/json` | JSON data |
>| `application/octet-stream` | Generic binary |
>| `multipart/form-data` | Form with file uploads |

---

# Server → Client Messages

The server sends two types of responses:

```
success messages
error messages
```

These messages follow the same structure of the success and error messages returnedd for HTTP requests, but are sent through the WebSocket connection instead of HTTP responses.

---

## Success Response

Sent when a message is accepted and broadcast to the room.

```json
{
  "data": {
    "id": "6601e2b8e1b2c8a1f0a1b2c3",
    "conversation_id": "6601e2b8e1b2c8a1f0a1b2c3",
    "sender_id": "uuid-of-sender",
    "timestamp": "2026-03-22T01:53:44.106614Z",
    "type": "text",
    "content": "Hello world",
    "mime_type": null,
    "filename": null,
    "responding_to": null
  },
  "meta": {
    "timestamp": "2026-03-22T01:53:44.106753+00:00",
    "success": true,
    "request_id": "request-uuid"
  }
}
```

### Fields

| Field           | Type   | Description                                      |
| --------------- | ------ | ------------------------------------------------ |
| id              | string | Unique identifier for the message (ObjectId)     |
| conversation_id | string | Identifier for the conversation (ObjectId)       |
| sender_id       | string | Identifier for the sender (UUID)                 |
| timestamp       | string | ISO 8601 timestamp of when the message was sent   |
| type            | string | Type of message (e.g., "text", "file") |
| content         | string | The actual message content                       |
| meta.timestamp  | string | ISO 8601 timestamp of when the server processed the message |
| meta.success    | boolean | Indicates if the message was successfully processed |
| meta.request_id | string | Optional identifier for tracing the request (UUID) |


### Notes

* The message is broadcast to **all clients in the room**, including the sender.
* `request_id` is attributed to the conenction on the initial handshake.
* `sender_id` is the UUID of the client that sent the message. For system messages (e.g., join confirmation), `sender_id` is set to "System".
* The user id is taken at the initial connection handshake and associated with the WebSocket connection. All messages sent through that connection are attributed to that user id.

---

## Error Response

Sent when the client sends an invalid payload or violates the protocol.

```json
{
  "type": "https://websocket.org/reference/close-codes/",
  "title": "Websocket Error",
  "status": 1003,
  "detail": "Invalid chat message payload. Payload missing required fields: type, content",
  "instance": "/api/live_chat/room/{chat_id}",
  "meta": {
    "success": false,
    "request_id": "optional-request-uuid"
  }
}
```

### Error Code

| Code | Meaning                            |
| ---- | ---------------------------------- |
| 1003 | Unsupported or invalid data format |

The connection **remains open** after recoverable errors such as invalid payload structure.

---

# Example Interaction

### Client sends

```json
{
  "type": "text",
  "content": "Hi everyone"
}
```

### Server broadcasts

```json
{
  "data": {
    "id": "6601e2b8e1b2c8a1f0a1b2c3",
    "conversation_id": "6601e2b8e1b2c8a1f0a1b2c3",
    "sender_id": "uuid-of-sender",
    "timestamp": "2026-03-22T01:53:44Z",
    "type": "text",
    "content": "Hi everyone"
  },
  "meta": {
    "success": true
  }
}
```

---

# Invalid Message Example

### Client sends

```json
{
  "content": "missing type"
}
```

### Server responds

```json
{
    "type": "https://websocket.org/reference/close-codes/",
    "title": "Websocket Error",
    "status": 1003,
    "detail": "Invalid chat message payload. Payload missing required fields: type, content",
    "instance": "/api/live_chat/room/4634862c-af46-4bcd-b793-d39e4e37bb12",
    "meta": {
        "timestamp": "2026-03-22T20:23:13.517550+00:00",
        "success": false,
        "request_id": "db1acdbc-0c7d-48d0-92d9-3e53f01b1208"
    }
}
```

Connection remains active and the client may continue sending messages.

---

# Disconnection

The server closes the connection only in the following cases:

* client disconnects
* network failure
* unrecoverable protocol violation

Normal validation errors do **not** close the connection.

---

# Summary

| Direction       | Message Type    | Purpose                    |
| --------------- | --------------- | -------------------------- |
| Client → Server | chat message    | send new message           |
| Server → Client | success payload | broadcast accepted message |
| Server → Client | error payload   | notify invalid input       |

---