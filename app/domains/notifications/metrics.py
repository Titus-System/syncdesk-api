from app.core.metrics.prometheus import prometheus

email_outbox_depth = prometheus.register_gauge(
    "email_outbox_depth",
    "Number of email outbox entries by status",
    ["status"],
)

email_outbox_processed_total = prometheus.register_counter(
    "email_outbox_processed_total",
    "Total email outbox rows processed by outcome",
    ["status"],
)
