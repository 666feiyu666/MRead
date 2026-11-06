"""Test fixtures: a throwaway data directory, a synchronous fake provider, and a client."""

from __future__ import annotations

import base64
import os
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="mread-tests-")
os.environ["MREAD_DATA_DIR"] = _TMP
os.environ["MREAD_PROFILE"] = "test"
os.environ["MREAD_PROVIDER"] = "fake"
os.environ["MREAD_SYNC_RUNS"] = "1"
os.environ["MREAD_TEXT_ONLY"] = "0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.provider import FakeProvider  # noqa: E402

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8AAAwAB/gC7Kx4AAAAASUVORK5CYII="
)

ARTICLE_TEXT = (
    "The handscroll is usually dated to the Five Dynasties period. "
    "Later colophons describe the scene as a private gathering, not an official audience. "
    "The composition divides the night into four episodes."
)


@pytest.fixture(autouse=True)
def clean_database():
    db.init_db()
    with db.session() as conn:
        for table in ("decisions", "step_records", "runs", "workflows", "profiles", "assets", "cases"):
            conn.execute(f"DELETE FROM {table}")
    yield


@pytest.fixture
def fake(monkeypatch):
    provider = FakeProvider()
    engine.register_provider("fake", provider)
    return provider


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def case(client):
    response = client.post("/api/cases", json={"title": "Night Revels, a detail"})
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def materials(client, case):
    image = client.post(
        f"/api/cases/{case['id']}/assets",
        data={"kind": "image", "title": "Detail of the first episode"},
        files={"file": ("detail.png", PNG_1PX, "image/png")},
    )
    assert image.status_code == 200, image.text
    article = client.post(
        f"/api/cases/{case['id']}/assets",
        data={
            "kind": "article",
            "title": "A note on the handscroll",
            "provenance": "supplied by the researcher",
            "pasted_text": ARTICLE_TEXT,
        },
    )
    assert article.status_code == 200, article.text
    return {"image": image.json(), "article": article.json()}


@pytest.fixture
def profiles(client):
    response = client.post("/api/profiles/seed")
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def workflow(client, case, profiles, materials):
    response = client.post(
        "/api/workflows/template",
        json={
            "case_id": case["id"],
            "profile_ids": [profile["id"] for profile in profiles],
            "material_ids": [materials["image"]["id"], materials["article"]["id"]],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="session", autouse=True)
def _cleanup_tmp():
    yield
    shutil.rmtree(_TMP, ignore_errors=True)
