"""SQLite 保存・重複排除のテスト。"""
from database import db as dbm


def test_insert_and_fetch(conn, sample_posts_df):
    ds = dbm.create_dataset(conn, "テスト", "csv")
    inserted, skipped = dbm.insert_posts(conn, ds, sample_posts_df)
    assert inserted == 6
    assert skipped == 0
    df = dbm.fetch_posts_df(conn, ds)
    assert len(df) == 6


def test_duplicate_insert_skipped(conn, sample_posts_df):
    """同じ post_id は二重保存されない。"""
    ds = dbm.create_dataset(conn, "テスト", "csv")
    dbm.insert_posts(conn, ds, sample_posts_df)
    inserted, skipped = dbm.insert_posts(conn, ds, sample_posts_df)
    assert inserted == 0
    assert skipped == 6
    assert len(dbm.fetch_posts_df(conn, ds)) == 6


def test_settings_roundtrip(conn):
    ds = dbm.create_dataset(conn, "テスト", "csv")
    dbm.set_setting(conn, ds, "first_revenue_date", "2025-03-15")
    assert dbm.get_setting(conn, ds, "first_revenue_date") == "2025-03-15"
    dbm.set_setting(conn, ds, "first_revenue_date", None)
    assert dbm.get_setting(conn, ds, "first_revenue_date") is None


def test_analysis_save_and_fetch(conn, sample_posts_df):
    ds = dbm.create_dataset(conn, "テスト", "csv")
    dbm.insert_posts(conn, ds, sample_posts_df)
    dbm.save_analysis(conn, ds, [{"post_id": "1", "category_primary": "共感", "confidence": 0.8}])
    df = dbm.fetch_analysis_df(conn, ds)
    assert len(df) == 1
    assert df["category_primary"].iloc[0] == "共感"
    assert df["engine"].iloc[0] == "rule"


def test_ai_cache(conn):
    key = dbm.cache_key("Anthropic API", "model-x", "プロンプト")
    assert dbm.ai_cache_get(conn, key) is None
    dbm.ai_cache_set(conn, key, "Anthropic API", "model-x", "プロンプト", "応答")
    assert dbm.ai_cache_get(conn, key) == "応答"


def test_delete_dataset(conn, sample_posts_df):
    ds = dbm.create_dataset(conn, "テスト", "csv")
    dbm.insert_posts(conn, ds, sample_posts_df)
    dbm.delete_dataset(conn, ds)
    assert dbm.list_datasets(conn) == []
    assert dbm.fetch_posts_df(conn, ds).empty
