from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .schemas import ResetPasswordEmailParams, WelcomeEmailParams

EMAIL_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

template_env = Environment(
    loader=FileSystemLoader(str(EMAIL_TEMPLATES_DIR)), autoescape=select_autoescape(["html", "xml"])
)


def render_template(template_name: str, **context: Any) -> str:
    template = template_env.get_template(template_name)
    return template.render(**context)


def render_password_reset_email(params: ResetPasswordEmailParams) -> str:
    return render_template("reset_password_email.html", **params.model_dump())


def render_welcome_email(params: WelcomeEmailParams) -> str:
    return render_template("welcome_email.html", **params.model_dump())
