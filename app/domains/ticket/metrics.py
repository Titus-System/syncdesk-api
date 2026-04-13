from app.core.metrics.prometheus import prometheus

tickets_created_total = prometheus.register_counter(
    "domain_tickets_created_total", "Total tickets created", ["source", "criticality"]
)

tickets_status_changed_total = prometheus.register_counter(
    "domain_tickets_status_changed_total",
    "Total ticket status transitions",
    ["from_status", "to_status"],
)
