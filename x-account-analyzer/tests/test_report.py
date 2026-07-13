"""レポート生成とフェーズ分析のテスト。"""
import pandas as pd

from services import analyzer
from services import metrics as mt
from services import phases as ph
from services import report_generator as rg


def _build_inputs(sample_posts_df):
    posts, estimated = mt.add_engagement_columns(sample_posts_df)
    analysis = analyzer.analyze_posts_df(posts)
    posts["post_id"] = posts["post_id"].astype(str)
    merged = posts.merge(analysis, on="post_id", how="left")
    merged["created_at"] = pd.to_datetime(merged["created_at"], utc=True)
    return posts, analysis, merged, estimated


def test_detect_key_dates(sample_posts_df):
    _, _, merged, _ = _build_inputs(sample_posts_df)
    dates = ph.detect_key_dates(merged)
    assert dates["first_post"] is not None
    assert dates["sales_start"] is not None
    assert dates["first_revenue_candidate"] is not None
    # 初収益候補は 3/15 の投稿
    assert dates["first_revenue_candidate"].strftime("%Y-%m-%d") == "2025-03-15"


def test_detect_phases(sample_posts_df):
    _, _, merged, _ = _build_inputs(sample_posts_df)
    result = ph.detect_phases(merged)
    assert not result.empty
    assert result["phase"].iloc[0] == "発信開始期"
    assert set(result.columns) >= {"phase", "start", "end", "estimated", "basis"}


def test_build_report_contains_all_sections(sample_posts_df):
    posts, analysis, merged, estimated = _build_inputs(sample_posts_df)
    overview = mt.overview_stats(posts, estimated)
    cat_stats = mt.category_stats(posts, analysis)
    phases_df = ph.detect_phases(merged)
    comp30 = mt.compare_periods(posts, pd.Timestamp("2025-03-15", tz="UTC"), days=30)
    comp7 = mt.compare_periods(posts, pd.Timestamp("2025-03-15", tz="UTC"), days=7)

    report = rg.build_report(
        account_name="テストアカウント",
        merged=merged, overview=overview, cat_stats=cat_stats, phases_df=phases_df,
        comparison30=comp30, comparison7=comp7,
        revenue_date="2025-03-15", sales_start="2025-03-10",
        top_posts_dict=mt.top_posts(posts, analysis, n=3),
    )
    # 17セクションすべてが含まれる
    for i in range(1, 18):
        assert f"## {i}. " in report, f"セクション {i} がレポートにない"
    assert "テストアカウント" in report
    assert "2025-03-15" in report


def test_report_without_revenue_date(sample_posts_df):
    """初収益日未設定でもレポートが生成できる。"""
    posts, analysis, merged, estimated = _build_inputs(sample_posts_df)
    report = rg.build_report(
        account_name="A", merged=merged,
        overview=mt.overview_stats(posts, estimated),
        cat_stats=mt.category_stats(posts, analysis),
        phases_df=ph.detect_phases(merged),
        comparison30=None, comparison7=None,
        revenue_date=None, sales_start=None,
    )
    assert "未確定" in report
