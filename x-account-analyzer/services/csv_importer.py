"""CSV インポート機能。

- 日本語列名の自動マッピング
- 日付の正規化
- 重複投稿の排除
- CSV 数式インジェクション対策（エクスポート用サニタイズ）
"""
from __future__ import annotations

import io

import pandas as pd

MAX_FILE_SIZE_MB = 30

# 内部列名 → 受け付ける列名の候補（小文字比較）
COLUMN_ALIASES: dict[str, list[str]] = {
    "post_id": ["post_id", "id", "tweet_id", "投稿id", "ツイートid", "ポストid"],
    "created_at": ["created_at", "date", "datetime", "time", "日時", "投稿日", "投稿日時", "日付", "作成日時"],
    "text": ["text", "body", "content", "本文", "テキスト", "投稿内容", "投稿本文", "ツイート本文", "ポスト本文"],
    "impressions": ["impressions", "impression", "views", "インプレッション", "インプレッション数", "表示回数", "閲覧数"],
    "likes": ["likes", "like", "favorite_count", "いいね", "いいね数"],
    "replies": ["replies", "reply", "reply_count", "返信", "返信数", "リプライ", "リプライ数", "リプ数"],
    "reposts": ["reposts", "repost", "retweets", "retweet_count", "リポスト", "リポスト数", "リツイート", "リツイート数", "rt数"],
    "bookmarks": ["bookmarks", "bookmark", "ブックマーク", "ブックマーク数", "保存数"],
    "quotes": ["quotes", "quote", "quote_count", "引用", "引用数"],
    "url": ["url", "link", "permalink", "投稿url", "リンク"],
    "media_type": ["media_type", "media", "メディア", "メディア種別", "画像有無"],
    "followers_count": ["followers_count", "followers", "フォロワー", "フォロワー数"],
}

REQUIRED_COLUMNS = ["post_id", "created_at", "text"]
NUMERIC_COLUMNS = ["impressions", "likes", "replies", "reposts", "bookmarks", "quotes", "followers_count"]

TEMPLATE_COLUMNS = [
    "post_id", "created_at", "text", "impressions", "likes", "replies",
    "reposts", "bookmarks", "quotes", "url", "media_type", "followers_count",
]


def suggest_mapping(columns: list[str]) -> dict[str, str | None]:
    """CSV の列名から内部列名への対応を推測する。

    戻り値: {内部列名: CSVの列名 or None}
    """
    mapping: dict[str, str | None] = {}
    normalized = {str(c).strip().lower(): c for c in columns}
    for internal, aliases in COLUMN_ALIASES.items():
        found = None
        for alias in aliases:
            if alias in normalized:
                found = normalized[alias]
                break
        mapping[internal] = found
    return mapping


def read_csv_bytes(data: bytes) -> pd.DataFrame:
    """CSV バイト列を DataFrame として読み込む（UTF-8 / Shift_JIS 両対応）。"""
    if len(data) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValueError(
            f"ファイルサイズが大きすぎます（上限 {MAX_FILE_SIZE_MB}MB）。"
            "期間を分けて複数のCSVに分割してください。"
        )
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=encoding, dtype=str)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSVの文字コードを判定できませんでした。UTF-8で保存し直してください。")


def normalize_posts(df: pd.DataFrame, mapping: dict[str, str | None]) -> tuple[pd.DataFrame, list[str]]:
    """列マッピングを適用し、投稿データを正規化する。

    戻り値: (正規化済み DataFrame, 警告メッセージのリスト)
    """
    warnings: list[str] = []

    missing = [c for c in REQUIRED_COLUMNS if not mapping.get(c)]
    if missing:
        raise ValueError(
            "必須列が見つかりません: " + ", ".join(missing)
            + "。列マッピングで対応する列を選択してください。"
        )

    out = pd.DataFrame()
    for internal in TEMPLATE_COLUMNS:
        src = mapping.get(internal)
        out[internal] = df[src] if src and src in df.columns else None

    # 型の正規化
    out["post_id"] = out["post_id"].astype(str).str.strip()
    out["text"] = out["text"].astype(str)

    # 日付
    parsed = pd.to_datetime(out["created_at"], errors="coerce", utc=True, format="mixed")
    n_bad_dates = int(parsed.isna().sum())
    if n_bad_dates:
        warnings.append(f"日付を読み取れない行が {n_bad_dates} 件あり、除外しました。")
    out["created_at"] = parsed

    # 数値
    for col in NUMERIC_COLUMNS:
        out[col] = pd.to_numeric(
            out[col].astype(str).str.replace(",", "", regex=False), errors="coerce"
        )

    # 無効行の除外
    before = len(out)
    out = out.dropna(subset=["created_at"])
    out = out[out["post_id"].str.len() > 0]
    out = out[out["text"].str.strip().str.len() > 0]
    n_dropped = before - len(out) - n_bad_dates
    if n_dropped > 0:
        warnings.append(f"post_id または本文が空の行を {n_dropped} 件除外しました。")

    # 重複排除（同じ post_id は最初の1件を残す）
    dup = int(out.duplicated(subset=["post_id"]).sum())
    if dup:
        warnings.append(f"重複した post_id を {dup} 件除外しました。")
        out = out.drop_duplicates(subset=["post_id"], keep="first")

    out = out.sort_values("created_at").reset_index(drop=True)
    out["created_at"] = out["created_at"].dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    return out, warnings


def sanitize_cell(value):
    """CSV 数式インジェクション対策。= + - @ で始まる文字列に ' を付ける。"""
    if isinstance(value, str) and value and value[0] in ("=", "+", "-", "@", "\t"):
        return "'" + value
    return value


def export_safe_csv(df: pd.DataFrame) -> bytes:
    """数式インジェクション対策を施した CSV バイト列を返す。"""
    safe = df.copy()
    for col in safe.columns:
        safe[col] = safe[col].map(sanitize_cell)
    return safe.to_csv(index=False).encode("utf-8-sig")


def template_csv() -> bytes:
    """CSV テンプレート（見本1行つき）を返す。"""
    sample = pd.DataFrame([
        {
            "post_id": "1234567890",
            "created_at": "2025-01-15 09:00",
            "text": "投稿の本文をここに入れます",
            "impressions": 1500,
            "likes": 30,
            "replies": 5,
            "reposts": 8,
            "bookmarks": 12,
            "quotes": 1,
            "url": "https://x.com/user/status/1234567890",
            "media_type": "image",
            "followers_count": 500,
        }
    ], columns=TEMPLATE_COLUMNS)
    return sample.to_csv(index=False).encode("utf-8-sig")
