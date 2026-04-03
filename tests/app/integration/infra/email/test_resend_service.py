import pytest

from app.core.config import get_settings
from app.core.email.schemas import ResetPasswordEmailParams, WelcomeEmailParams
from app.infra.email.resend_service import ResendEmailService

settings = get_settings()
RUN_RESEND_INTEGRATION = settings.RUN_RESEND_INTEGRATION_TESTS
RESEND_TEST_TO_EMAIL = settings.RESEND_TEST_TO_EMAIL.strip()

SHOULD_RUN = RUN_RESEND_INTEGRATION and bool(RESEND_TEST_TO_EMAIL)

pytestmark = pytest.mark.skipif(
    not SHOULD_RUN,
    reason=(
        "Optional test skipped. Set RUN_RESEND_INTEGRATION_TESTS=1 and "
        "RESEND_TEST_TO_EMAIL to run against the live Resend API."
    ),
)


@pytest.mark.asyncio
async def test_resend_service_send_welcome_email_live() -> None:
	service = ResendEmailService()
	params = WelcomeEmailParams(
		user_name="Integration Test",
		user_email=RESEND_TEST_TO_EMAIL,
		one_time_password="A1B2C3",
		login_url="https://syncdesk.pro/login",
	)

	await service.send_welcome_email(
		to=RESEND_TEST_TO_EMAIL,
		email_params=params,
	)


@pytest.mark.asyncio
async def test_resend_service_send_reset_email_live() -> None:
	service = ResendEmailService()
	params = ResetPasswordEmailParams(
		user_email=RESEND_TEST_TO_EMAIL,
		reset_url="https://syncdesk.pro/reset?token=integration-test",
	)

	await service.send_reset_email(
		to=RESEND_TEST_TO_EMAIL,
		email_params=params,
	)


@pytest.mark.asyncio
async def test_resend_service_send_internal_method_live() -> None:
    service = ResendEmailService()

    await service._send(
        to=RESEND_TEST_TO_EMAIL,
        subject="SyncDesk integration test: direct send",
        html="<p>SyncDesk integration test email: direct _send method</p>",
    )
