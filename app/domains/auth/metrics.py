from app.core.metrics.prometheus import prometheus

login_total = prometheus.register_counter(
    "domain_auth_login_total", "Total login attempts", ["status"]
)

registration_total = prometheus.register_counter(
    "domain_auth_registration_total", "Total user registrations", ["method"]
)

token_refresh_total = prometheus.register_counter(
    "domain_auth_token_refresh_total", "Total token refresh attempts", ["status"]
)

password_reset_total = prometheus.register_counter(
    "domain_password_reset_total", "Total password reset operations", ["stage"]
)
