from app.core.metrics.prometheus import prometheus

file_uploads_total = prometheus.register_counter(
    "domain_files_uploads_total",
    "File upload lifecycle events grouped by status and context.",
    ["status", "context"],
)

file_confirms_total = prometheus.register_counter(
    "domain_files_confirms_total",
    "Outcomes of upload confirmation calls grouped by result and context.",
    ["result", "context"],
)

file_deletes_total = prometheus.register_counter(
    "domain_files_deletes_total",
    "Soft-delete operations on file objects, grouped by context.",
    ["context"],
)

file_download_urls_total = prometheus.register_counter(
    "domain_files_download_urls_total",
    "Presigned download URLs issued grouped by context.",
    ["context"],
)

file_upload_size_bytes = prometheus.register_histogram(
    "domain_files_upload_size_bytes",
    "Declared size in bytes of file uploads at presign time, grouped by context.",
    ["context"],
)
