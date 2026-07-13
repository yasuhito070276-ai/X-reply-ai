"""X 公式 API（API v2）クライアント。

- 環境変数 X_BEARER_TOKEN が設定されている場合のみ利用できる
- 公開投稿のみを、公式エンドポイントから取得する
- 無許可スクレイピングは行わない
- レート制限（HTTP 429）を検知して分かりやすく案内する

参照エンドポイント（X API v2）:
- GET /2/users/by/username/:username  … ユーザー名から ID を取得
- GET /2/users/:id/tweets             … ユーザーの投稿一覧（ページネーション対応）
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import httpx

API_BASE = "https://api.x.com/2"

TWEET_FIELDS = "created_at,public_metrics,entities,referenced_tweets"
MAX_RESULTS_PER_PAGE = 100  # API v2 の上限


class XApiError(Exception):
    """ユーザーに表示するためのわかりやすい API エラー。"""

    def __init__(self, message: str, suggest_csv: bool = False):
        super().__init__(message)
        self.message = message
        self.suggest_csv = suggest_csv


def get_bearer_token() -> str | None:
    token = os.environ.get("X_BEARER_TOKEN", "").strip()
    return token or None


def is_configured() -> bool:
    return get_bearer_token() is not None


def _friendly_error(resp: httpx.Response) -> XApiError:
    status = resp.status_code
    if status == 401:
        return XApiError(
            "X APIの認証に失敗しました（401）。.env の X_BEARER_TOKEN が正しいか確認してください。"
        )
    if status == 403:
        return XApiError(
            "X APIの権限がありません（403）。現在のAPIプランではこのデータを取得できない可能性があります。"
            "CSVインポート方式をご利用ください。",
            suggest_csv=True,
        )
    if status == 404:
        return XApiError("指定したユーザー名が見つかりませんでした（404）。@を除いたユーザー名を確認してください。")
    if status == 429:
        reset = resp.headers.get("x-rate-limit-reset")
        wait_msg = ""
        if reset and reset.isdigit():
            reset_dt = datetime.fromtimestamp(int(reset), tz=timezone.utc)
            wait_sec = max(0, int((reset_dt - datetime.now(timezone.utc)).total_seconds()))
            wait_msg = f" 約{wait_sec // 60 + 1}分後に再試行できます。"
        return XApiError(
            f"X APIのレート制限に達しました（429）。しばらく待ってから再実行してください。{wait_msg}"
            "取得済みのデータは保存されています。"
        )
    return XApiError(f"X APIエラー（HTTP {status}）が発生しました。時間をおいて再実行してください。")


def _client(token: str) -> httpx.Client:
    return httpx.Client(
        base_url=API_BASE,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )


def get_user_by_username(username: str, token: str | None = None) -> dict:
    """ユーザー名から ID・名前・フォロワー数を取得する。"""
    token = token or get_bearer_token()
    if not token:
        raise XApiError("X_BEARER_TOKEN が設定されていません。CSVインポートをご利用ください。", suggest_csv=True)
    username = username.lstrip("@").strip()
    with _client(token) as client:
        resp = client.get(
            f"/users/by/username/{username}",
            params={"user.fields": "public_metrics,created_at,description"},
        )
    if resp.status_code != 200:
        raise _friendly_error(resp)
    data = resp.json().get("data")
    if not data:
        raise XApiError("ユーザー情報を取得できませんでした。ユーザー名を確認してください。")
    return data


def fetch_user_tweets(
    user_id: str,
    max_posts: int = 500,
    include_retweets: bool = False,
    include_replies: bool = False,
    start_time: str | None = None,
    end_time: str | None = None,
    token: str | None = None,
    progress_callback=None,
    rate_limit_wait: bool = False,
) -> list[dict]:
    """ユーザーの投稿をページネーションで取得し、内部形式の辞書リストで返す。

    progress_callback(取得済み件数) を渡すと進捗を通知する。
    レート制限に達した場合は、それまでに取得できた分を返せるよう
    XApiError に partial 属性として保持する。
    """
    token = token or get_bearer_token()
    if not token:
        raise XApiError("X_BEARER_TOKEN が設定されていません。CSVインポートをご利用ください。", suggest_csv=True)

    exclude = []
    if not include_retweets:
        exclude.append("retweets")
    if not include_replies:
        exclude.append("replies")

    posts: list[dict] = []
    pagination_token: str | None = None

    with _client(token) as client:
        while len(posts) < max_posts:
            params: dict = {
                "max_results": min(MAX_RESULTS_PER_PAGE, max(5, max_posts - len(posts))),
                "tweet.fields": TWEET_FIELDS,
            }
            if exclude:
                params["exclude"] = ",".join(exclude)
            if pagination_token:
                params["pagination_token"] = pagination_token
            if start_time:
                params["start_time"] = start_time
            if end_time:
                params["end_time"] = end_time

            resp = client.get(f"/users/{user_id}/tweets", params=params)

            if resp.status_code == 429 and rate_limit_wait:
                reset = resp.headers.get("x-rate-limit-reset")
                wait_sec = 60
                if reset and reset.isdigit():
                    wait_sec = max(5, int(reset) - int(time.time()) + 2)
                if wait_sec > 900:  # 15分以上待つ場合は中断して部分結果を返す
                    err = _friendly_error(resp)
                    err.partial = posts  # type: ignore[attr-defined]
                    raise err
                time.sleep(wait_sec)
                continue

            if resp.status_code != 200:
                err = _friendly_error(resp)
                err.partial = posts  # type: ignore[attr-defined]
                raise err

            body = resp.json()
            for tweet in body.get("data", []):
                posts.append(_tweet_to_post(tweet, user_id))
            if progress_callback:
                progress_callback(len(posts))

            pagination_token = body.get("meta", {}).get("next_token")
            if not pagination_token:
                break

    return posts[:max_posts]


def _tweet_to_post(tweet: dict, user_id: str) -> dict:
    """API のツイートオブジェクトを内部の投稿形式へ変換する。"""
    metrics = tweet.get("public_metrics", {})
    return {
        "post_id": str(tweet["id"]),
        "created_at": tweet.get("created_at"),
        "text": tweet.get("text", ""),
        "impressions": metrics.get("impression_count"),
        "likes": metrics.get("like_count"),
        "replies": metrics.get("reply_count"),
        "reposts": metrics.get("retweet_count"),
        "bookmarks": metrics.get("bookmark_count"),
        "quotes": metrics.get("quote_count"),
        "url": f"https://x.com/i/web/status/{tweet['id']}",
        "media_type": None,
        "followers_count": None,
    }
