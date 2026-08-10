from urllib.parse import parse_qs, urlparse

from app.tiktok_api import (
    AUTHORIZATION_ENDPOINT,
    TikTokAPI,
    code_challenge_for,
    generate_code_verifier,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.calls = []
        self.responses = [
            FakeResponse({"data": {"videos": [{"id": "one", "view_count": 10}], "cursor": 123, "has_more": True}, "error": {"code": "ok"}}),
            FakeResponse({"data": {"videos": [{"id": "two", "view_count": 20}], "has_more": False}, "error": {"code": "ok"}}),
        ]

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def test_desktop_pkce_uses_tiktoks_hex_sha256_and_scopes():
    verifier = generate_code_verifier()
    challenge = code_challenge_for(verifier)
    assert 43 <= len(verifier) <= 128
    assert len(challenge) == 64
    api = TikTokAPI("client", "secret", "http://localhost:3455/callback/", "user.info.basic,video.list")
    parsed = urlparse(api.authorization_url("state-value", challenge))
    params = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == AUTHORIZATION_ENDPOINT
    assert params["response_type"] == ["code"]
    assert params["code_challenge"] == [challenge]
    assert params["code_challenge_method"] == ["S256"]
    assert params["scope"] == ["user.info.basic,video.list"]


def test_video_list_paginates_with_cursor_and_max_count():
    fake_session = FakeSession()
    api = TikTokAPI("client", "secret", "http://localhost:3455/callback/", "video.list", session=fake_session)
    videos = api.list_videos("access-token")
    assert [video["tiktok_video_id"] for video in videos] == ["one", "two"]
    assert len(fake_session.calls) == 2
    assert fake_session.calls[0][2]["json"] == {"max_count": 20}
    assert fake_session.calls[1][2]["json"] == {"max_count": 20, "cursor": 123}
    assert "view_count" in fake_session.calls[0][2]["params"]["fields"]
