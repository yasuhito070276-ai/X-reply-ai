"""数値分析モジュール。

インプレッションがないデータでは、いいね・返信・リポストから
「推定エンゲージメント指標」を作る（is_estimated=True で明示）。
平均値と中央値の両方を返し、バズ投稿に引っ張られないようにする。
"""
from __future__ import annotations

import pandas as pd

ENGAGE_COLS = ["likes", "replies", "reposts", "bookmarks", "quotes"]


def has_impressions(df: pd.DataFrame) -> bool:
    return "impressions" in df.columns and df["impressions"].notna().sum() > 0


def add_engagement_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """エンゲージメント関連の列を追加する。

    戻り値: (DataFrame, is_estimated)
    is_estimated=True の場合、impressions が無いため推定指標を使っている。
    """
    out = df.copy()
    for col in ENGAGE_COLS:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    out["total_engagement"] = out[ENGAGE_COLS].sum(axis=1)
    # 重み付きスコア（返信・リポストはいいねより重い行動として扱う）
    out["engagement_score"] = (
        out["likes"] + out["replies"] * 2 + out["reposts"] * 3
        + out["bookmarks"] * 2 + out["quotes"] * 2
    )

    estimated = not has_impressions(out)
    if estimated:
        out["engagement_rate"] = None
    else:
        imp = pd.to_numeric(out["impressions"], errors="coerce")
        out["engagement_rate"] = (out["total_engagement"] / imp.replace(0, pd.NA) * 100).astype(float)

    if "followers_count" in out.columns and out["followers_count"].notna().sum() > 0:
        fol = pd.to_numeric(out["followers_count"], errors="coerce")
        out["reaction_per_follower"] = (out["total_engagement"] / fol.replace(0, pd.NA) * 100).astype(float)
    else:
        out["reaction_per_follower"] = None
    return out, estimated


def compute_engagement_rate(likes: float, replies: float, reposts: float, impressions: float) -> float | None:
    """単一投稿のエンゲージメント率（%）。impressions が 0 以下なら None。"""
    if impressions is None or impressions <= 0:
        return None
    return (likes + replies + reposts) / impressions * 100


def posts_per_period(df: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    """期間ごとの投稿数。freq: D=日 / W=週 / M=月"""
    if df.empty:
        return pd.DataFrame(columns=["period", "count"])
    s = df.set_index(pd.to_datetime(df["created_at"], utc=True)).resample(freq).size()
    out = s.reset_index()
    out.columns = ["period", "count"]
    return out


def category_stats(df: pd.DataFrame, analysis: pd.DataFrame) -> pd.DataFrame:
    """カテゴリー別の投稿数・構成比・平均/中央値の反応。"""
    if analysis.empty:
        return pd.DataFrame()
    merged = df.merge(analysis[["post_id", "category_primary"]], on="post_id", how="left")
    merged["category_primary"] = merged["category_primary"].fillna("その他")

    agg_map = {"post_id": "count", "likes": ["mean", "median"],
               "replies": ["mean", "median"], "reposts": ["mean", "median"]}
    if has_impressions(merged):
        agg_map["impressions"] = ["mean", "median"]
    if "engagement_rate" in merged.columns and merged["engagement_rate"].notna().any():
        agg_map["engagement_rate"] = ["mean", "median"]
    if "engagement_score" in merged.columns:
        agg_map["engagement_score"] = ["mean", "median"]

    g = merged.groupby("category_primary").agg(agg_map)
    g.columns = ["_".join(c).strip("_") for c in g.columns]
    g = g.rename(columns={"post_id_count": "投稿数"})
    g["構成比(%)"] = (g["投稿数"] / g["投稿数"].sum() * 100).round(1)
    return g.sort_values("投稿数", ascending=False).round(1)


def weekday_hour_stats(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """曜日別・時間帯別の平均反応。"""
    d = df.copy()
    dt = pd.to_datetime(d["created_at"], utc=True)
    d["weekday"] = dt.dt.dayofweek
    d["hour"] = dt.dt.hour
    weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
    wd = d.groupby("weekday")["engagement_score"].agg(["count", "mean", "median"]).round(1)
    wd.index = [weekday_names[i] for i in wd.index]
    hr = d.groupby("hour")["engagement_score"].agg(["count", "mean", "median"]).round(1)
    return wd, hr


def compare_flag_groups(df: pd.DataFrame, analysis: pd.DataFrame, flag_col: str) -> pd.DataFrame:
    """あり/なし比較（外部リンク・CTAなど）。flag_col は analysis 側の bool 列。"""
    if analysis.empty or flag_col not in analysis.columns:
        return pd.DataFrame()
    merged = df.merge(analysis[["post_id", flag_col]], on="post_id", how="left")
    merged[flag_col] = merged[flag_col].fillna(False)
    g = merged.groupby(flag_col)["engagement_score"].agg(["count", "mean", "median"]).round(1)
    g.index = ["なし" if not i else "あり" for i in g.index]
    return g


def compare_periods(df: pd.DataFrame, pivot_date: pd.Timestamp, days: int = 30) -> dict:
    """基準日（初収益日など）の直前 days 日間と、その前 days 日間を比較する。"""
    dt = pd.to_datetime(df["created_at"], utc=True)
    pivot = pd.Timestamp(pivot_date)
    if pivot.tzinfo is None:
        pivot = pivot.tz_localize("UTC")

    recent = df[(dt >= pivot - pd.Timedelta(days=days)) & (dt < pivot)]
    prior = df[(dt >= pivot - pd.Timedelta(days=days * 2)) & (dt < pivot - pd.Timedelta(days=days))]

    def summarize(sub: pd.DataFrame) -> dict:
        if sub.empty:
            return {"posts": 0, "posts_per_day": 0.0, "avg_engagement": 0.0, "median_engagement": 0.0}
        return {
            "posts": int(len(sub)),
            "posts_per_day": round(len(sub) / days, 2),
            "avg_engagement": round(float(sub["engagement_score"].mean()), 1),
            "median_engagement": round(float(sub["engagement_score"].median()), 1),
        }

    return {"days": days, "recent": summarize(recent), "prior": summarize(prior),
            "recent_df": recent, "prior_df": prior}


def top_posts(df: pd.DataFrame, analysis: pd.DataFrame, n: int = 10) -> dict[str, pd.DataFrame]:
    """「伸びた投稿」を複数の観点で抽出する。"""
    result: dict[str, pd.DataFrame] = {}
    d = df.copy()

    if has_impressions(d):
        result["インプレッション上位"] = d.nlargest(n, "impressions")
    result["いいね上位"] = d.nlargest(n, "likes")
    result["リプ上位"] = d.nlargest(n, "replies")
    result["リポスト上位"] = d.nlargest(n, "reposts")
    if "engagement_rate" in d.columns and d["engagement_rate"].notna().any():
        result["エンゲージメント率上位"] = d.nlargest(n, "engagement_rate")

    # 同時期（前後14日）の中央値と比べて異常に伸びた投稿
    dt = pd.to_datetime(d["created_at"], utc=True)
    d = d.assign(_dt=dt).sort_values("_dt")
    rolling_median = (
        d.set_index("_dt")["engagement_score"].rolling("28D", center=False).median()
    )
    d["rolling_median"] = rolling_median.values
    d["vs_median_ratio"] = d["engagement_score"] / d["rolling_median"].replace(0, pd.NA)
    outliers = d[d["vs_median_ratio"] >= 3].nlargest(n, "vs_median_ratio")
    result["同時期比の異常値投稿"] = outliers.drop(columns=["_dt"])

    # 外れ値を除いた安定的な高反応投稿（上位5%を除いた中で上位）
    if len(d) > 20:
        cutoff = d["engagement_score"].quantile(0.95)
        stable = d[d["engagement_score"] < cutoff].nlargest(n, "engagement_score")
        result["安定的な高反応投稿"] = stable.drop(columns=["_dt"], errors="ignore")

    if d["reaction_per_follower"].notna().any():
        result["フォロワー比反応率上位"] = d.nlargest(n, "reaction_per_follower").drop(columns=["_dt"], errors="ignore")
    return result


def overview_stats(df: pd.DataFrame, estimated: bool) -> dict:
    """概要画面用の基本統計。"""
    if df.empty:
        return {}
    dt = pd.to_datetime(df["created_at"], utc=True)
    days = max((dt.max() - dt.min()).days, 1)
    stats = {
        "total_posts": int(len(df)),
        "period_start": dt.min().strftime("%Y-%m-%d"),
        "period_end": dt.max().strftime("%Y-%m-%d"),
        "period_days": days,
        "posts_per_day": round(len(df) / days, 2),
        "avg_engagement": round(float(df["engagement_score"].mean()), 1),
        "median_engagement": round(float(df["engagement_score"].median()), 1),
        "avg_likes": round(float(df["likes"].mean()), 1),
        "median_likes": round(float(df["likes"].median()), 1),
        "is_estimated": estimated,
    }
    if has_impressions(df):
        stats["avg_impressions"] = round(float(df["impressions"].mean()), 1)
        stats["median_impressions"] = round(float(df["impressions"].median()), 1)
    return stats
