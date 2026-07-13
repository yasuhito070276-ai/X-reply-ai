"""X API エラー処理のテスト（実際の API は呼ばない。httpx MockTransport 使用）。"""
import httpx
import pytest

from services import x_api


def _mock_client(handler):
    transport = httpx.MockTransport(handler)
    return httpx.Client(base_url=x_api.API_BASE, transport=transport,
                        headers={"Authorization": "Bearer test"})


def test_no_token_raises(monkeypatch):
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    with pytest.raises(x_api.XApiError) as e:
        x_api.get_user_by_username("someone")
    assert e.value.suggest_csv is True


def test_error_401(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "bad-token")

    def handler(request):
        return httpx.Response(401, json={"title": "Unauthorized"})

    monkeypatch.setattr(x_api, "_client", lambda token: _mock_client(handler))
    with pytest.raises(x_api.XApiError) as e:
        x_api.get_user_by_username("someone")
    assert "認証に失敗" in e.value.message
    assert "bad-token" not in e.value.message  # 秘密情報を含めない


def test_error_403_suggests_csv(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "token")

    def handler(request):
        return httpx.Response(403, json={"title": "Forbidden"})

    monkeypatch.setattr(x_api, "_client", lambda token: _mock_client(handler))
    with pytest.raises(x_api.XApiError) as e:
        x_api.get_user_by_username("someone")
    assert e.value.suggest_csv is True
    assert "CSV" in e.value.message


def test_error_429_rate_limit(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "token")

    def handler(request):
        return httpx.Response(429, json={}, headers={"x-rate-limit-reset": "9999999999"})

    monkeypatch.setattr(x_api, "_client", lambda token: _mock_client(handler))
    with pytest.raises(x_api.XApiError) as e:
        x_api.fetch_user_tweets("123", max_posts=10)
    assert "レート制限" in e.value.message
    assert e.value.partial == []  # 部分結果が保持される


def test_fetch_tweets_pagination(monkeypatch):
    """ページネーションで複数ページを取得し、内部形式に変換できる。"""
    monkeypatch.setenv("X_BEARER_TOKEN", "token")
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json={
                "data": [{"id": "1", "text": "投稿1", "created_at": "2025-01-01T00:00:00Z",
                          "public_metrics": {"like_count": 5, "reply_count": 1,
                                             "retweet_count": 2, "quote_count": 0,
                                             "impression_count": 100}}],
                "meta": {"next_token": "page2"},
            })
        return httpx.Response(200, json={
            "data": [{"id": "2", "text": "投稿2", "created_at": "2025-01-02T00:00:00Z",
                      "public_metrics": {"like_count": 3}}],
            "meta": {},
        })

    monkeypatch.setattr(x_api, "_client", lambda token: _mock_client(handler))
    posts = x_api.fetch_user_tweets("123", max_posts=10)
    assert len(posts) == 2
    assert posts[0]["post_id"] == "1"
    assert posts[0]["likes"] == 5
    assert posts[0]["impressions"] == 100
    assert posts[1]["impressions"] is None  # 権限がない場合は None
