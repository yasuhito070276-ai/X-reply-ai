"""Streamlit ページ共通の部品。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from database import db as dbm
from services import analyzer
from services import metrics as mt


# グラフ用の固定カテゴリカルパレット（色覚多様性を考慮した検証済み配色）
CHART_COLORS = [
    "#2a78d6", "#1baf7a", "#eda100", "#008300",
    "#4a3aa7", "#e34948", "#e87ba4", "#eb6834",
]
CHART_GRAY = "#898781"  # 「その他」やまとめ用
CHART_PRIMARY = CHART_COLORS[0]


def category_color_map(categories: list[str]) -> dict[str, str]:
    """カテゴリー名 → 色の固定対応。8色を超えた分はグレーにまとめる。"""
    mapping = {}
    for i, cat in enumerate(categories):
        mapping[cat] = CHART_COLORS[i] if i < len(CHART_COLORS) else CHART_GRAY
    return mapping


@st.cache_resource
def get_conn():
    """アプリ全体で共有する SQLite 接続。"""
    return dbm.get_conn()


def select_dataset_sidebar() -> int | None:
    """サイドバーにデータセット選択を表示し、選択中の ID を返す。"""
    conn = get_conn()
    datasets = dbm.list_datasets(conn)
    st.sidebar.markdown("### 📂 分析対象データ")
    if not datasets:
        st.sidebar.info("データがまだありません。「データ取り込み」からCSVをアップロードしてください。")
        return None

    options = {f"{d['name']}（{d['post_count']}件）": d["id"] for d in datasets}
    default_idx = 0
    current = st.session_state.get("dataset_id")
    ids = list(options.values())
    if current in ids:
        default_idx = ids.index(current)
    label = st.sidebar.selectbox("データセット", list(options.keys()), index=default_idx)
    dataset_id = options[label]
    st.session_state["dataset_id"] = dataset_id
    return dataset_id


def ensure_rule_analysis(conn, dataset_id: int, posts_df: pd.DataFrame) -> pd.DataFrame:
    """未分析の投稿にルールベース分析を実行して保存し、分析結果を返す。

    AI 分析済み（engine='ai'）の結果は上書きしない。
    """
    existing = dbm.fetch_analysis_df(conn, dataset_id)
    done_ids = set(existing["post_id"].astype(str)) if not existing.empty else set()
    todo = posts_df[~posts_df["post_id"].astype(str).isin(done_ids)]
    if not todo.empty:
        with st.spinner(f"ルールベース分析を実行中…（{len(todo)}件）"):
            results = analyzer.analyze_posts_df(todo)
            dbm.save_analysis(conn, dataset_id, results.to_dict("records"), engine="rule")
        existing = dbm.fetch_analysis_df(conn, dataset_id)
    return existing


def load_merged(dataset_id: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, bool]:
    """投稿 + 分析結果 + エンゲージメント列を結合した DataFrame を返す。

    戻り値: (posts_df, analysis_df, merged_df, is_estimated)
    """
    conn = get_conn()
    posts = dbm.fetch_posts_df(conn, dataset_id)
    if posts.empty:
        return posts, pd.DataFrame(), pd.DataFrame(), True
    analysis = ensure_rule_analysis(conn, dataset_id, posts)
    posts_e, estimated = mt.add_engagement_columns(posts)
    posts_e["post_id"] = posts_e["post_id"].astype(str)
    analysis = analysis.copy()
    analysis["post_id"] = analysis["post_id"].astype(str)
    merged = posts_e.merge(analysis, on="post_id", how="left")
    if "category_primary" in merged.columns:
        merged["category_primary"] = merged["category_primary"].fillna("その他")
    return posts_e, analysis, merged, estimated


def get_revenue_date(dataset_id: int) -> str | None:
    return dbm.get_setting(get_conn(), dataset_id, "first_revenue_date")


def set_revenue_date(dataset_id: int, value: str | None) -> None:
    dbm.set_setting(get_conn(), dataset_id, "first_revenue_date", value)


def estimated_badge(is_estimated: bool) -> None:
    if is_estimated:
        st.caption("⚠️ インプレッションデータがないため、いいね・返信・リポストによる **推定指標** を使用しています。")
