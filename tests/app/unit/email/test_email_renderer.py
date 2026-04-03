from app.core.email.renderer import render_password_reset_email, render_welcome_email
from app.core.email.schemas import ResetPasswordEmailParams, WelcomeEmailParams


def test_render_password_reset_email_returns_html_with_expected_values() -> None:
	params = ResetPasswordEmailParams(
		user_email="pedro@example.com",
		reset_url="https://syncdesk.pro/reset?token=abc123",
		expiry_minutes=45,
		year=2026,
		support_email="support@syncdesk.pro",
	)

	rendered = render_password_reset_email(params)

	assert isinstance(rendered, str)
	assert "pedro@example.com" in rendered
	assert "https://syncdesk.pro/reset?token=abc123" in rendered
	assert "45 minutos" in rendered
	assert "2026" in rendered
	assert "support@syncdesk.pro" in rendered
	assert "{{ user_email }}" not in rendered
	assert "{{ reset_url }}" not in rendered


def test_render_welcome_email_returns_html_with_expected_values() -> None:
	params = WelcomeEmailParams(
		user_name="Pedro",
		user_email="pedro@example.com",
		one_time_password="A1B2C3",
		login_url="https://syncdesk.pro/login",
		year=2026,
		support_email="support@syncdesk.pro",
	)

	rendered = render_welcome_email(params)

	assert isinstance(rendered, str)
	assert "Bem-vindo ao SyncDesk, Pedro!" in rendered
	assert "pedro@example.com" in rendered
	assert "A1B2C3" in rendered
	assert "https://syncdesk.pro/login" in rendered
	assert "2026" in rendered
	assert "support@syncdesk.pro" in rendered
	assert "{{ user_name }}" not in rendered
	assert "{{ one_time_password }}" not in rendered
