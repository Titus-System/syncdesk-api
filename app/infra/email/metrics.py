from app.core.metrics.prometheus import prometheus

emails_sent_total = prometheus.register_counter(
    "domain_emails_sent_total", "Total emails sent", ["type", "status"]
)
