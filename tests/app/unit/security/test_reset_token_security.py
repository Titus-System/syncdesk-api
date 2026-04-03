import os
from types import SimpleNamespace

import pytest

from app.core import security as security_module
from app.core.security import ResetTokenSecurity


@pytest.fixture
def patched_reset_token_settings(monkeypatch: pytest.MonkeyPatch) -> str:
	# Tests should be deterministic even when env vars are missing.
	secret = os.getenv("RESET_TOKEN_HMAC_SECRET") or "mock-reset-token-hmac-secret"
	fake_settings = SimpleNamespace(RESET_TOKEN_HMAC_SECRET=secret)
	monkeypatch.setattr(security_module, "get_settings", lambda: fake_settings)
	return secret


def test_generate_token_returns_non_empty_string(
	patched_reset_token_settings: str,
) -> None:
	service = ResetTokenSecurity()

	token = service.generate_token()

	assert isinstance(token, str)
	assert token
	assert len(token) >= 32


def test_hash_token_is_deterministic_and_not_plain_text(
	patched_reset_token_settings: str,
) -> None:
	service = ResetTokenSecurity()
	token = "plain-token-value"

	first_hash = service.hash_token(token)
	second_hash = service.hash_token(token)

	assert first_hash == second_hash
	assert first_hash != token
	assert len(first_hash) == 64


def test_verify_returns_true_for_matching_token(
	patched_reset_token_settings: str,
) -> None:
	service = ResetTokenSecurity()
	token = "correct-token"
	stored_hash = service.hash_token(token)

	assert service.verify(token, stored_hash) is True


def test_verify_returns_false_for_non_matching_token(
	patched_reset_token_settings: str,
) -> None:
	service = ResetTokenSecurity()
	stored_hash = service.hash_token("correct-token")

	assert service.verify("wrong-token", stored_hash) is False


def test_uses_mock_secret_when_env_secret_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.delenv("RESET_TOKEN_HMAC_SECRET", raising=False)
	mock_secret = "mock-reset-token-hmac-secret"
	fake_settings = SimpleNamespace(RESET_TOKEN_HMAC_SECRET=mock_secret)
	monkeypatch.setattr(security_module, "get_settings", lambda: fake_settings)

	service = ResetTokenSecurity()

	assert service.secret == mock_secret.encode()
