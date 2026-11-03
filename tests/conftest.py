"""Konfigurasi tes: database terisolasi dan rahasia uji."""

from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="bangkah-tests-")
os.environ.setdefault("BANGKAH_DATA_DIR", os.path.join(_TMP, "data"))
os.environ.setdefault("BANGKAH_DB_PATH", os.path.join(_TMP, "data", "bangkah.db"))
os.environ.setdefault("BANGKAH_PRINT_DIR", os.path.join(_TMP, "prints"))
os.environ.setdefault("BANGKAH_REPORT_DIR", os.path.join(_TMP, "reports"))
os.environ.setdefault("BANGKAH_WORKSPACE_DIR", os.path.join(_TMP, "workspace"))
os.environ.setdefault("BANGKAH_DOCS_DIR", os.path.join(_TMP, "docs"))
os.environ["API_AUTH_TOKEN"] = "test-owner-secret"
os.environ["BANGKAH_SKIP_MODEL_CHECK"] = "1"
os.environ["MAX_REPAIR_ROUNDS"] = "2"

import pytest
from fastapi.testclient import TestClient

from backend import db, settings


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    db.init_db(tmp_path / "bangkah.db")
    for attribute, subdir in (
        ("PRINT_DIR", "prints"),
        ("REPORT_DIR", "reports"),
        ("WORKSPACE_DIR", "workspace"),
        ("ARCHIVE_DIR", "archive"),
        ("DOCS_DIR", "docs"),
    ):
        target = tmp_path / subdir
        target.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(settings, attribute, target)
    yield


@pytest.fixture
def conn():
    with db.transaction() as connection:
        yield connection


@pytest.fixture
def client():
    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def owner_headers(client):
    response = client.post("/api/session", json={"api_auth_token": "test-owner-secret"})
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}
