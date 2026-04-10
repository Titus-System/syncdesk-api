from app.core.metrics.prometheus import prometheus

chatbot_messages_total = prometheus.register_counter(
    "domain_chatbot_messages_total", "Total chatbot messages processed", ["step"]
)

chatbot_tickets_total = prometheus.register_counter(
    "domain_chatbot_tickets_created_total", "Tickets auto-created by chatbot triage"
)
