from core.safe_env import safe_subprocess_env


def test_rahasia_tidak_diteruskan():
    source = {
        "PATH": "/usr/bin", "HOME": "/home/x",
        "SMTP_PASSWORD": "rahasia", "DEPLOY_WEBHOOK_TOKEN": "t", "BANGKAH_API_TOKEN": "t",
        "OPENAI_API_KEY": "sk-x", "ANTHROPIC_API_KEY": "sk-y", "MAIL_API_TOKEN": "m",
    }
    env = safe_subprocess_env(source=source)
    assert env == {"PATH": "/usr/bin", "HOME": "/home/x"}


def test_extra_ditambahkan_dan_case_windows():
    env = safe_subprocess_env({"PYTHONUNBUFFERED": "1"}, source={"Path": "C:\\x", "SystemRoot": "C:\\W", "SECRET": "s"})
    assert env["Path"] == "C:\\x" and env["SystemRoot"] == "C:\\W"
    assert env["PYTHONUNBUFFERED"] == "1" and "SECRET" not in env
