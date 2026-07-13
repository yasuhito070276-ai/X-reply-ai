"""CSV インポートのテスト。"""
import pandas as pd
import pytest

from services import csv_importer as ci


def _make_csv_bytes(rows: list[dict]) -> bytes:
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8")


def test_read_csv_bytes_utf8():
    data = _make_csv_bytes([{"post_id": "1", "created_at": "2025-01-01", "text": "テスト投稿"}])
    df = ci.read_csv_bytes(data)
    assert len(df) == 1
    assert df["text"].iloc[0] == "テスト投稿"


def test_file_size_limit():
    big = b"a" * (ci.MAX_FILE_SIZE_MB * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="ファイルサイズ"):
        ci.read_csv_bytes(big)


def test_japanese_column_mapping():
    """日本語列名が自動でマッピングされる。"""
    mapping = ci.suggest_mapping(["投稿ID", "投稿日時", "本文", "いいね数", "インプレッション数"])
    assert mapping["post_id"] == "投稿ID"
    assert mapping["created_at"] == "投稿日時"
    assert mapping["text"] == "本文"
    assert mapping["likes"] == "いいね数"
    assert mapping["impressions"] == "インプレッション数"


def test_normalize_with_japanese_columns():
    df = pd.DataFrame([
        {"投稿ID": "100", "投稿日時": "2025-01-01 09:00", "本文": "こんにちは", "いいね数": "10"},
        {"投稿ID": "101", "投稿日時": "2025-01-02 09:00", "本文": "おはよう", "いいね数": "1,200"},
    ])
    mapping = ci.suggest_mapping(list(df.columns))
    out, warnings = ci.normalize_posts(df, mapping)
    assert len(out) == 2
    assert out["likes"].iloc[1] == 1200  # カンマ入り数値も読める
    assert out["created_at"].iloc[0].startswith("2025-01-01")


def test_duplicate_posts_removed():
    df = pd.DataFrame([
        {"post_id": "1", "created_at": "2025-01-01", "text": "A"},
        {"post_id": "1", "created_at": "2025-01-01", "text": "A（重複）"},
        {"post_id": "2", "created_at": "2025-01-02", "text": "B"},
    ])
    mapping = ci.suggest_mapping(list(df.columns))
    out, warnings = ci.normalize_posts(df, mapping)
    assert len(out) == 2
    assert any("重複" in w for w in warnings)


def test_invalid_dates_dropped():
    df = pd.DataFrame([
        {"post_id": "1", "created_at": "2025-01-01", "text": "OK"},
        {"post_id": "2", "created_at": "日付ではない", "text": "NG"},
    ])
    mapping = ci.suggest_mapping(list(df.columns))
    out, warnings = ci.normalize_posts(df, mapping)
    assert len(out) == 1
    assert any("日付" in w for w in warnings)


def test_missing_required_column_raises():
    df = pd.DataFrame([{"post_id": "1", "created_at": "2025-01-01"}])  # text なし
    mapping = ci.suggest_mapping(list(df.columns))
    with pytest.raises(ValueError, match="必須列"):
        ci.normalize_posts(df, mapping)


def test_csv_injection_sanitized():
    """数式インジェクション対策: = で始まるセルに ' が付く。"""
    df = pd.DataFrame([{"text": "=SUM(A1:A9)", "normal": "安全なテキスト"}])
    out = ci.export_safe_csv(df).decode("utf-8-sig")
    assert "'=SUM(A1:A9)" in out
    assert "安全なテキスト" in out
