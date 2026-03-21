import pytest
from fastapi import HTTPException

from app.auth import verify_token


class TestVerifyToken:
    def test_valid_token(self):
        result = verify_token(
            credential="correct-token", admin_token="correct-token"
        )
        assert result is True

    def test_invalid_token(self):
        with pytest.raises(HTTPException) as exc_info:
            verify_token(
                credential="wrong-token", admin_token="correct-token"
            )
        assert exc_info.value.status_code == 401

    def test_empty_token(self):
        with pytest.raises(HTTPException) as exc_info:
            verify_token(credential="", admin_token="correct-token")
        assert exc_info.value.status_code == 401

    def test_no_admin_token_configured(self):
        with pytest.raises(HTTPException) as exc_info:
            verify_token(credential="any-token", admin_token="")
        assert exc_info.value.status_code == 401
