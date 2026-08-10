import re

from app.app import create_app


def csrf_from(response):
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', response.get_data(as_text=True))
    assert match
    return match.group(1)


def test_mock_dashboard_database_and_exports(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "MOCK_TIKTOK": True,
            "DATABASE_PATH": tmp_path / "mock.db",
            "EXPORTS_DIR": tmp_path / "exports",
            "SECRET_KEY": "test-secret",
        }
    )
    client = app.test_client()
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "Modo mock ativo" in dashboard.get_data(as_text=True)
    assert "Relatorio TikTok Demo" in dashboard.get_data(as_text=True)

    token = csrf_from(dashboard)
    sync = client.post("/api/sync", headers={"X-CSRF-Token": token})
    assert sync.status_code == 200
    assert sync.json["ok"] is True
    assert sync.json["summary"]["videos_found"] == 12

    json_export = client.post("/api/export/json", headers={"X-CSRF-Token": token})
    csv_export = client.post("/api/export/csv", headers={"X-CSRF-Token": token})
    assert json_export.status_code == 200
    assert csv_export.status_code == 200
    assert json_export.json["filename"].endswith(".json")
    assert csv_export.json["filename"].endswith(".csv")
    assert (tmp_path / "exports" / json_export.json["filename"]).exists()
    assert (tmp_path / "exports" / csv_export.json["filename"]).exists()

    videos = client.get("/videos?sort=engagement")
    assert videos.status_code == 200
    detail = client.get("/videos/1")
    assert detail.status_code == 200
    detail_html = detail.get_data(as_text=True)
    assert 'name="category"' not in detail_html
    assert 'name="format"' not in detail_html
    assert 'name="hook"' not in detail_html
    assert 'name="notes"' not in detail_html
