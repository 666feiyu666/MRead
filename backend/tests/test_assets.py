"""Upload validation: real bytes, real extraction, readable errors."""

from __future__ import annotations

import io

from tests.conftest import ARTICLE_TEXT, PNG_1PX


def test_fake_image_is_refused(client, case):
    response = client.post(
        f"/api/cases/{case['id']}/assets",
        data={"kind": "image", "title": "not really an image"},
        files={"file": ("x.png", b"GIF89a not a png at all", "image/png")},
    )
    assert response.status_code == 400
    assert "PNG, JPEG, or WebP" in response.json()["detail"]


def test_pdf_without_text_asks_for_pasted_text(client, case):
    from pypdf import PdfWriter

    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(buffer)

    response = client.post(
        f"/api/cases/{case['id']}/assets",
        data={"kind": "article", "title": "a scan"},
        files={"file": ("scan.pdf", buffer.getvalue(), "application/pdf")},
    )
    assert response.status_code == 400
    assert "paste the text" in response.json()["detail"]


def test_pasted_text_is_stored_and_returned(client, case):
    created = client.post(
        f"/api/cases/{case['id']}/assets",
        data={"kind": "article", "title": "pasted", "pasted_text": ARTICLE_TEXT},
    )
    assert created.status_code == 200
    fetched = client.get(f"/api/assets/{created.json()['id']}").json()
    assert "Later colophons" in fetched["text"]


def test_image_metadata_never_leaks_bytes_or_storage_path(client, case):
    created = client.post(
        f"/api/cases/{case['id']}/assets",
        data={"kind": "image", "title": "detail"},
        files={"file": ("detail.png", PNG_1PX, "image/png")},
    )
    body = created.json()
    assert body["mime"] == "image/png"
    assert "stored_path" not in body
    assert "text_content" not in body


def test_unknown_kind_is_refused(client, case):
    response = client.post(
        f"/api/cases/{case['id']}/assets",
        data={"kind": "video", "title": "nope", "pasted_text": "x"},
    )
    assert response.status_code == 400
