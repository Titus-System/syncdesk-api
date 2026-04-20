from app.core.metrics.prometheus import prometheus

ws_connections_active = prometheus.register_gauge(
    "domain_live_chat_connections_active", "Currently active WebSocket connections"
)

messages_broadcast_total = prometheus.register_counter(
    "domain_live_chat_messages_broadcast_total", "Total messages broadcast in chat rooms"
)

chat_messages_total = prometheus.register_counter(
    "domain_live_chat_messages_sent_total", "Total messages sent in chat rooms"
)

listener_conversations_created_total = prometheus.register_counter(
    "domain_live_chat_listener_conversations_created_total",
    "Conversations created by event listeners",
    ["event"],
)

listener_conversations_closed_total = prometheus.register_counter(
    "domain_live_chat_listener_conversations_closed_total",
    "Conversations closed by event listeners",
    ["event"],
)
