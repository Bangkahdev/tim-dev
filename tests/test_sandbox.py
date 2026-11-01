import pytest

from backend import sandbox


def test_safe_env_drops_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-rahasia")
    monkeypatch.setenv("EMAIL_PASSWORD", "sandi")
    env = sandbox.safe_env({"EXTRA": "tidak"})
    assert "OPENAI_API_KEY" not in env
    assert "EMAIL_PASSWORD" not in env
    assert "EXTRA" not in env
    assert env["PYTHONUNBUFFERED"] == "1"


def test_redact_hides_secret_values(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-rahasia")
    text = sandbox.redact("key sk-rahasia dan password=hunter2")
    assert "sk-rahasia" not in text
    assert "hunter2" not in text


def test_validate_command_rejects_unknown_executable():
    with pytest.raises(ValueError):
        sandbox.validate_command("curl http://example.com")


def test_validate_command_rejects_traversal_and_metacharacters():
    with pytest.raises(ValueError):
        sandbox.validate_command("python ../escape.py")
    with pytest.raises(ValueError):
        sandbox.validate_command("python -c 'x; rm -rf /'")


def test_validate_command_accepts_allowlisted():
    assert sandbox.validate_command("python -m pytest -q") == ["python", "-m", "pytest", "-q"]
