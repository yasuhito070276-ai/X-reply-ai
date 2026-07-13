"""数値分析のテスト。"""
import pandas as pd

from services import metrics as mt


def test_engagement_rate():
    rate = mt.compute_engagement_rate(likes=10, replies=5, reposts=5, impressions=1000)
    assert rate == 2.0


def test_engagement_rate_zero_impressions():
    assert mt.compute_engagement_rate(10, 5, 5, 0) is None
    assert mt.compute_engagement_rate(10, 5, 5, None) is None


def test_add_engagement_columns_with_impressions(sample_posts_df):
    out, estimated = mt.add_engagement_columns(sample_posts_df)
    assert estimated is False
    assert "engagement_rate" in out.columns
    assert out["engagement_rate"].notna().all()


def test_add_engagement_columns_estimated():
    """impressions がない場合は推定指標になる。"""
    df = pd.DataFrame([
        {"post_id": "1", "created_at": "2025-01-01T00:00:00+00:00", "text": "a",
         "likes": 10, "replies": 2, "reposts": 1},
    ])
    out, estimated = mt.add_engagement_columns(df)
    assert estimated is True
    assert out["engagement_score"].iloc[0] == 10 + 2 * 2 + 1 * 3


def test_compare_periods(sample_posts_df):
    out, _ = mt.add_engagement_columns(sample_posts_df)
    result = mt.compare_periods(out, pd.Timestamp("2025-03-15", tz="UTC"), days=30)
    # 直前30日 (2/13〜3/14): post 4, 5 の2件
    assert result["recent"]["posts"] == 2
    # その前30日 (1/14〜2/12): post 3 の1件
    assert result["prior"]["posts"] == 1


def test_overview_stats(sample_posts_df):
    out, estimated = mt.add_engagement_columns(sample_posts_df)
    stats = mt.overview_stats(out, estimated)
    assert stats["total_posts"] == 6
    assert stats["period_start"] == "2025-01-01"
    assert stats["period_end"] == "2025-03-15"
    assert stats["median_likes"] > 0


def test_median_not_dragged_by_outlier():
    """中央値がバズ投稿に引っ張られないことを確認する。"""
    rows = [{"post_id": str(i), "created_at": f"2025-01-{i+1:02d}T00:00:00+00:00",
             "text": "a", "likes": 10, "replies": 0, "reposts": 0} for i in range(9)]
    rows.append({"post_id": "buzz", "created_at": "2025-01-11T00:00:00+00:00",
                 "text": "buzz", "likes": 100000, "replies": 0, "reposts": 0})
    out, _ = mt.add_engagement_columns(pd.DataFrame(rows))
    stats = mt.overview_stats(out, True)
    assert stats["median_likes"] == 10
    assert stats["avg_likes"] > 1000
