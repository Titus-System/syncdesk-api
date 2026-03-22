## WebSocket Chat Endpoint

**URL**

```
ws://<host>/api/live_chat/room/{conversation_id}
```

**Description**

Establishes a persistent WebSocket connection to send and receive real-time chat messages within a specific conversation.

For the sake of simplicity, this endpoint uses the conversation_id to identify a chat room.

---

## Connection Lifecycle

### 1. Client connects

The client opens a WebSocket connection to:

```
/api/live_chat/room/{conversation_id}
```

If the conversation exists (or is created implicitly), the server registers the client in the room and begins streaming messages.

Immediately after joining, the server sends a system confirmation message to the newly connected client indicating that the room join succeeded.

Example:

```json
{
  "data": {
    "id": "uuid",
    "conversation_id": "4634862c-af46-4bcd-b793-d39e4e37bb12",
    "sender_id": "System",
    "timestamp": "2026-03-22T01:53:44Z",
    "type": "text",
    "content": "Joined to chat room 4634862c-af46-4bcd-b793-d39e4e37bb12"
  },
  "meta": {
    "success": true,
    "request_id": "request-id"
  }
}
```

---

## Message Format

All messages exchanged through this connection are JSON.

---

## Client → Server Messages

The client sends chat messages using the following schema:

```json
{
  "type": "text",
  "content": "Hello world",
  "mime_type": "text/plain",
  "filename": "optional-file-name.txt",
  "responding_to": "optional-message-uuid"
}
```

### Fields

| Field   | Type   | Required | Description                                      |
| ------- | ------ | -------- | ------------------------------------------------ |
| type    | "text" or "file" | yes      | Message type (either "text" or "file") |
| content | string | yes      | Message body                                     |
| mime_type | string | no       | MIME type of the content (e.g., `text/plain`)    |
| filename | string | no       | Original file name if the message contains a file |
| responding_to | string | no       | UUID of the message being replied to (if applicable) |

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
    "id": "c3684603-7026-4366-85fa-3619ce2a0fcd",
    "conversation_id": "4634862c-af46-4bcd-b793-d39e4e37bb12",
    "sender_id": "user-123",
    "timestamp": "2026-03-22T01:53:44.106614Z",
    "type": "text",
    "content": "Hello world"
  },
  "meta": {
    "timestamp": "2026-03-22T01:53:44.106753+00:00",
    "success": true,
    "request_id": "request-id"
  }
}
```

### Notes

* The message is broadcast to **all clients in the room**, including the sender.
* `request_id` is attributed to the conenction on the initial handshake.

---

## Error Response

Sent when the client sends an invalid payload or violates the protocol.

```json
{
  "type": "https://websocket.org/reference/close-codes/",
  "title": "Websocket Error",
  "status": 1003,
  "detail": "Invalid chat message payload. Payload missing required fields: type, content",
  "instance": "/api/live_chat/room/{conversation_id}",
  "meta": {
    "success": false,
    "request_id": "optional-request-id"
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
    "id": "uuid",
    "conversation_id": "uuid",
    "sender_id": "user-123",
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