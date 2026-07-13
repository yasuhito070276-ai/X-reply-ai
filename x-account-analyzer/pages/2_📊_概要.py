"""概要画面。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from components import common
from services import metrics as mt
from services import phases as ph

st.set_page_config(page_title="概要", page_icon="📊", layout="wide")
st.title("📊 概要")

dataset_id = common.select_dataset_sidebar()
if dataset_id is None:
    st.stop()

posts, analysis, merged, estimated = common.load_merged(dataset_id)
if posts.empty:
    st.info("このデータセットには投稿がありません。")
    st.stop()

overview = mt.overview_stats(posts, estimated)
common.estimated_badge(estimated)

c1, c2, c3, c4 = st.columns(4)
c1.metric("投稿総数", f"{overview['total_posts']}件")
c2.metric("分析期間", f"{overview['period_days']}日")
c3.metric("1日平均投稿数", overview["posts_per_day"])
top_cat = merged["category_primary"].value_counts()
c4.metric("最も多いカテゴリー", top_cat.index[0] if not top_cat.empty else "—")

st.caption(f"期間: {overview['period_start']} 〜 {overview['period_end']}")

c1, c2, c3, c4 = st.columns(4)
label = "反応スコア（推定）" if estimated else "反応スコア"
c1.metric(f"平均{label}", overview["avg_engagement"])
c2.metric(f"中央値{label}", overview["median_engagement"])
c3.metric("平均いいね", overview["avg_likes"])
c4.metric("中央値いいね", overview["median_likes"])
if "avg_impressions" in overview:
    c1, c2, _, _ = st.columns(4)
    c1.metric("平均インプレッション", overview["avg_impressions"])
    c2.metric("中央値インプレッション", overview["median_impressions"])

st.divider()

# 初収益候補・販売開始
revenue_date = common.get_revenue_date(dataset_id)
key_dates = ph.detect_key_dates(merged)

c1, c2 = st.columns(2)
with c1:
    st.subheader("💰 初収益")
    if revenue_date:
        st.success(f"初収益日（設定済み）: **{revenue_date}**")
    elif key_dates["first_revenue_candidate"] is not None:
        st.warning(
            f"初収益候補日（未確定）: **{key_dates['first_revenue_candidate'].strftime('%Y-%m-%d')}**\n\n"
            "「0→1分析」画面で候補を確認して確定してください。"
        )
    else:
        st.info("初収益候補は検出されていません。「0→1分析」画面で手動設定できます。")
with c2:
    st.subheader("🛒 販売開始（推定）")
    if key_dates["sales_start"] is not None:
        st.success(f"販売開始推定日: **{key_dates['sales_start'].strftime('%Y-%m-%d')}**")
        st.caption("販売・商品告知カテゴリーの投稿が最初に現れた日")
    else:
        st.info("販売・商品告知カテゴリーの投稿は検出されていません。")

st.divider()
st.subheader("カテゴリー構成")
cat_counts = merged["category_primary"].value_counts()
st.bar_chart(cat_counts)
