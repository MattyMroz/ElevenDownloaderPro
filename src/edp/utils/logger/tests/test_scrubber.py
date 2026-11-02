from __future__ import annotations

import pytest
from loguru._recattrs import RecordException

from ..scrubber import scrub_message, scrub_patcher, set_url_route_prefixes


class TestScrubMessage:
    @pytest.mark.parametrize(
        "raw",
        [
            pytest.param("api_key=sk-1234567890abcdef", id="api_key_eq"),
            pytest.param("api-key: sk-1234567890abcdef", id="api-key_colon"),
            pytest.param("apikey=secret123", id="apikey_eq"),
            pytest.param("secret_key=mykey", id="secret_key"),
            pytest.param("access_key=awskey", id="access_key"),
            pytest.param("access-key: val", id="access-key_colon"),
        ],
    )
    def test_api_key_patterns_masked(self, raw: str) -> None:
        result = scrub_message(raw)
        assert "***" in result
        for secret in ("sk-1234567890abcdef", "secret123", "mykey", "awskey", "val"):
            if secret in raw:
                assert secret not in result

    def test_bearer_token_masked(self) -> None:
        result = scrub_message("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload")
        assert "Bearer ***" in result
        assert "eyJhbGciOiJIUzI1NiJ9" not in result

    def test_bearer_case_insensitive(self) -> None:
        result = scrub_message("bearer MyToken123")
        assert "***" in result
        assert "MyToken123" not in result

    def test_openai_key_masked(self) -> None:
        key = "sk-" + "a" * 48
        result = scrub_message(f"Using key {key}")
        assert "sk-***" in result
        assert key not in result

    def test_short_sk_not_masked(self) -> None:
        result = scrub_message("sk-short")
        assert "sk-short" in result

    def test_google_api_key_masked(self) -> None:
        key = "AIza" + "B" * 35
        result = scrub_message(f"key={key}")
        assert "AIza***" in result
        assert key not in result

    @pytest.mark.parametrize(
        "raw",
        [
            pytest.param("password=secret123", id="password"),
            pytest.param("passwd: s3cret!", id="passwd"),
            pytest.param("pwd=hunter2", id="pwd"),
        ],
    )
    def test_password_masked(self, raw: str) -> None:
        result = scrub_message(raw)
        assert "***" in result

    @pytest.mark.parametrize(
        "raw",
        [
            pytest.param("token=abc123def", id="token"),
            pytest.param("auth: myauth", id="auth"),
        ],
    )
    def test_token_auth_masked(self, raw: str) -> None:
        result = scrub_message(raw)
        assert "***" in result

    def test_hex_key_masked(self) -> None:
        key = "a1b2c3d4e5f67890a1b2c3d4e5f67890"
        result = scrub_message(f"elevenlabs key: {key}")
        assert "***" in result
        assert key not in result

    def test_pure_digit_hex_not_masked(self) -> None:
        key = "1" * 32
        result = scrub_message(f"hash: {key}")
        assert key in result

    def test_pure_letter_hex_not_masked(self) -> None:
        key = "a" * 32
        result = scrub_message(f"hash: {key}")
        assert key in result

    def test_safe_message_unchanged(self) -> None:
        msg = "Processing file file_001.txt with 3 records"
        assert scrub_message(msg) == msg

    def test_empty_string(self) -> None:
        assert scrub_message("") == ""

    def test_multiple_secrets_in_one_message(self) -> None:
        msg = "api_key=secret123 password=hunter2"
        result = scrub_message(msg)
        assert "secret123" not in result
        assert "hunter2" not in result
        assert result.count("***") >= 2


def test_registered_routes_preserve_paths_but_scrub_secrets() -> None:
    set_url_route_prefixes(())
    try:
        assert scrub_message("GET /api/v1/projects") == "GET projects"
        set_url_route_prefixes(("/api/",))
        assert scrub_message("GET /api/v1/projects token=hidden") == "GET /api/v1/projects token=***"
        assert scrub_message("file /private/files/input.txt") == "file input.txt"
        set_url_route_prefixes(())
        assert scrub_message("GET /api/v1/projects") == "GET projects"
    finally:
        set_url_route_prefixes(())


class TestScrubPatcher:
    def test_patches_record_message(self) -> None:
        record: dict = {"message": "token=secret123"}  # type: ignore[type-arg]
        scrub_patcher(record)  # type: ignore[arg-type]
        assert "secret123" not in record["message"]
        assert "***" in record["message"]

    def test_safe_message_unchanged(self) -> None:
        record: dict = {"message": "Hello world"}  # type: ignore[type-arg]
        scrub_patcher(record)  # type: ignore[arg-type]
        assert record["message"] == "Hello world"

    def test_patches_nested_structured_values(self) -> None:
        record: dict = {  # type: ignore[type-arg]
            "message": "request failed",
            "extra": {
                "api_key": "plain-secret",
                "context": {"authorization": "Bearer hidden", "attempt": 2},
                "items": ["token=private", "safe"],
            },
            "exception": None,
        }
        scrub_patcher(record)  # type: ignore[arg-type]
        assert record["extra"]["api_key"] == "***"
        assert record["extra"]["context"]["authorization"] == "***"
        assert record["extra"]["context"]["attempt"] == 2
        assert record["extra"]["items"] == ["token=***", "safe"]

    def test_patches_exception_message(self) -> None:
        error = RuntimeError("api_key=exception-secret")
        record: dict = {  # type: ignore[type-arg]
            "message": "request failed",
            "extra": {},
            "exception": RecordException(RuntimeError, error, error.__traceback__),
        }
        scrub_patcher(record)  # type: ignore[arg-type]
        assert "exception-secret" not in str(record["exception"].value)
        assert "api_key=***" in str(record["exception"].value)
