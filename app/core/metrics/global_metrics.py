from .prometheus import prometheus

request_count = prometheus.register_counter(
    "app_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)

request_latency = prometheus.register_histogram(
    "app_request_latency_seconds", "HTTP request latency", ["method", "endpoint"]
)

error_count = prometheus.register_counter(
    "app_errors_total", "Total errors in the application", ["endpoint", "exception_type"]
)

system_memory_usage = prometheus.register_gauge(
    "system_memory_usage_percentage", "System memory usage percentage", ["type"]
)

system_memory_bytes = prometheus.register_gauge(
    "system_memory_bytes", "System memory in bytes", ["type"]
)

system_cpu_usage = prometheus.register_gauge(
    "system_cpu_usage_percentage", "System CPU usage percentage"
)

system_cpu_count = prometheus.register_gauge(
    "system_cpu_count", "Number of CPU cores"
)

job_runs = prometheus.register_counter(
    "background_job_runs_total", "Total number of background jobs executed", ["job_name"]
)

job_failures = prometheus.register_counter(
    "background_job_failures_total", "Number of failed executions of background jobs", ["job_name"]
)

job_duration = prometheus.register_histogram(
    "background_job_duration_seconds",
    "Execution duration of background jobs in seconds",
    ["job_name"],
)

db_pool_size = prometheus.register_gauge(
    "db_postgres_poolsize", "Total connections in the pool"
)

db_pool_checked_out = prometheus.register_gauge(
    "db_postgres_pool_checked_out", "Connections currently in use"
)

db_pool_overflow = prometheus.register_gauge(
    "db_postgres_pool_overflow", "Connections beyond pool size"
)

db_query_latency = prometheus.register_histogram(
    "db_postgres_query_duration_seconds",
    "PostgreSQL query execution time",
    ["operation"],
)

mongo_command_latency = prometheus.register_histogram(
    "db_mongo_command_duration_seconds",
    "MongoDB command execution time",
    ["command", "collection"],
)
