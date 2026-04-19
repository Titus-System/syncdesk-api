from app.core.metrics.prometheus import prometheus

events_published_total = prometheus.register_counter(
    "events_published_total", "Number of times each event was published", ["event"]
)

event_handler_failures_total = prometheus.register_counter(
    "event_handler_failures_total", "Number of times each handler failed", ["handler"]
)

event_handler_duration_seconds = prometheus.register_histogram(
    "event_handler_duration_seconds", "Handlers execution latency", ["handler"]
)
