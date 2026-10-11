from frugal import redactor


def test_redact_empty_and_none():
    assert redactor.redact(None) == ""
    assert redactor.redact("") == ""


def test_redact_api_key():
    sample = "Exporting API_KEY=abc123456789 to environment"
    res = redactor.redact(sample)
    assert "abc123456789" not in res
    assert "API_KEY=[REDACTED]" in res


def test_redact_password_and_secret():
    sample = "Config error: password : super_secret_pass found in conf"
    res = redactor.redact(sample)
    assert "super_secret_pass" not in res
    assert "password=[REDACTED]" in res


def test_redact_database_url():
    sample = "DATABASE_URL=postgres://user:secret123@db.prod.internal:5432/main"
    res = redactor.redact(sample)
    assert "secret123" not in res
    assert "DATABASE_URL=[REDACTED]" in res


def test_redact_aws_keys():
    sample = "AWS_ACCESS_KEY_ID = AKIAIOSFODNN7EXAMPLE\nAWS_SECRET_ACCESS_KEY = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    res = redactor.redact(sample)
    assert "AKIAIOSFODNN7EXAMPLE" not in res
    assert "wJalrXUtnFEMI" not in res
    assert "AWS_ACCESS_KEY_ID=[REDACTED]" in res
    assert "AWS_SECRET_ACCESS_KEY=[REDACTED]" in res


def test_redact_openai_key():
    sample = "Error calling OpenAI with key sk-1234567890abcdefghijklmnopqrstuv"
    res = redactor.redact(sample)
    assert "sk-1234567890abcdefghijklmnopqrstuv" not in res
    assert "[REDACTED_OPENAI_KEY]" in res


def test_redact_github_token():
    sample = "Cloning with ghp_012345678901234567890123456789012345..."
    res = redactor.redact(sample)
    assert "ghp_012345678901234567890123456789012345" not in res
    assert "[REDACTED_GITHUB_TOKEN]" in res


def test_redact_slack_token():
    sample = "Notification failed: token xoxb-123456789-987654321-abcdefg expired"
    res = redactor.redact(sample)
    assert "xoxb-123456789-987654321-abcdefg" not in res
    assert "[REDACTED_SLACK_TOKEN]" in res


def test_redact_bearer_token():
    sample = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    res = redactor.redact(sample)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in res
    assert "Bearer [REDACTED]" in res
