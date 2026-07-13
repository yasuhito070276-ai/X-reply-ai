"""投稿分析画面。一覧・フィルター・伸びた投稿・CSVエクスポート。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from components import common
from models.schemas import CATEGORIES
from services import csv_importer
from services import metrics as mt

st.set_page_config(page_title="投稿分析", page_icon="📝", layout="wide")
st.title("📝 投稿分析")

dataset_id = common.select_dataset_sidebar()
if dataset_id is None:
    st.stop()

posts, analysis, merged, estimated = common.load_merged(dataset_id)
if posts.empty:
    st.info("このデータセットには投稿がありません。")
    st.stop()

common.estimated_badge(estimated)

tab_list, tab_top, tab_stats = st.tabs(["📋 投稿一覧", "🚀 伸びた投稿", "📐 詳細統計"])

# ------------------------------------------------------------------
with tab_list:
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        f_cats = st.multiselect("カテゴリー", CATEGORIES)
    with c2:
        f_flags = st.multiselect(
            "特徴で絞り込み",
            ["CTAあり", "商品言及あり", "外部リンクあり", "LINE誘導", "note誘導", "メルマガ誘導", "初収益候補のみ"],
        )
    with c3:
        keyword = st.text_input("キーワード検索")
    with c4:
        sort_by = st.selectbox("並び替え", ["投稿日（新しい順）", "投稿日（古い順）", "いいね数", "反応スコア", "インプレッション"])

    view = merged.copy()
    if f_cats:
        view = view[view["category_primary"].isin(f_cats)]
    flag_map = {
        "CTAあり": view.get("cta", pd.Series("", index=view.index)).fillna("").astype(str).str.len() > 0,
        "商品言及あり": view.get("has_product_mention", False),
        "外部リンクあり": view.get("has_external_link", False),
        "LINE誘導": view.get("has_line", False),
        "note誘導": view.get("has_note", False),
        "メルマガ誘導": view.get("has_mailmag", False),
        "初収益候補のみ": view.get("is_revenue_candidate", False),
    }
    for f in f_flags:
        cond = flag_map[f]
        if isinstance(cond, pd.Series):
            view = view[cond.fillna(False).astype(bool)]
    if keyword:
        view = view[view["text"].astype(str).str.contains(keyword, case=False, na=False)]

    sort_map = {
        "投稿日（新しい順）": ("created_at", False), "投稿日（古い順）": ("created_at", True),
        "いいね数": ("likes", False), "反応スコア": ("engagement_score", False),
        "インプレッション": ("impressions", False),
    }
    col, asc = sort_map[sort_by]
    if col in view.columns:
        view = view.sort_values(col, ascending=asc, na_position="last")

    st.caption(f"{len(view)}件 / 全{len(merged)}件")

    display_cols = {
        "created_at": "投稿日時", "category_primary": "主分類", "category_secondary": "副分類",
        "confidence": "確信度", "text": "本文", "impressions": "インプ", "likes": "いいね",
        "replies": "返信", "reposts": "リポスト", "engagement_score": "反応スコア",
        "cta": "CTA", "has_product_mention": "商品言及", "is_revenue_candidate": "初収益候補",
        "reason": "分類理由",
    }
    show = view[[c for c in display_cols if c in view.columns]].rename(columns=display_cols)
    if "投稿日時" in show.columns:
        show["投稿日時"] = pd.to_datetime(show["投稿日時"], utc=True).dt.strftime("%Y-%m-%d %H:%M")
    if "副分類" in show.columns:
        show["副分類"] = show["副分類"].apply(lambda v: "、".join(v) if isinstance(v, list) else (v or ""))
    st.dataframe(show, use_container_width=True, height=500, hide_index=True)

    st.download_button(
        "📥 この一覧をCSVでダウンロード",
        data=csv_importer.export_safe_csv(show),
        file_name="posts_analysis.csv",
        mime="text/csv",
        help="Excelでの数式実行を防ぐ加工を施しています。",
    )

# ------------------------------------------------------------------
with tab_top:
    st.caption("単純ないいね数だけでなく、複数の観点で「伸びた投稿」を抽出します。")
    tops = mt.top_posts(posts, analysis, n=10)
    for name, tdf in tops.items():
        if tdf is None or tdf.empty:
            continue
        with st.expander(f"{name}（{len(tdf)}件）", expanded=(name == "いいね上位")):
            cols = [c for c in ["created_at", "text", "impressions", "likes", "replies",
                                "reposts", "engagement_score", "engagement_rate",
                                "vs_median_ratio", "reaction_per_follower"] if c in tdf.columns]
            t = tdf[cols].copy()
            t["created_at"] = pd.to_datetime(t["created_at"], utc=True).dt.strftime("%Y-%m-%d")
            t = t.rename(columns={
                "created_at": "投稿日", "text": "本文", "impressions": "インプ", "likes": "いいね",
                "replies": "返信", "reposts": "リポスト", "engagement_score": "反応スコア",
                "engagement_rate": "エンゲージ率(%)", "vs_median_ratio": "同時期中央値比",
                "reaction_per_follower": "フォロワー比反応率(%)",
            })
            st.dataframe(t.round(2), use_container_width=True, hide_index=True)

# ------------------------------------------------------------------
with tab_stats:
    st.subheader("カテゴリー別統計")
    cat_stats = mt.category_stats(posts, analysis)
    if not cat_stats.empty:
        rename = {
            "likes_mean": "平均いいね", "likes_median": "中央値いいね",
            "replies_mean": "平均返信", "replies_median": "中央値返信",
            "reposts_mean": "平均リポスト", "reposts_median": "中央値リポスト",
            "impressions_mean": "平均インプ", "impressions_median": "中央値インプ",
            "engagement_rate_mean": "平均エンゲージ率", "engagement_rate_median": "中央値エンゲージ率",
            "engagement_score_mean": "平均反応スコア", "engagement_score_median": "中央値反応スコア",
        }
        st.dataframe(cat_stats.rename(columns=rename), use_container_width=True)

    st.subheader("曜日別・時間帯別の反応")
    wd, hr = mt.weekday_hour_stats(posts)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**曜日別**")
        st.dataframe(wd.rename(columns={"count": "投稿数", "mean": "平均反応", "median": "中央値反応"}))
    with c2:
        st.markdown("**時間帯別**")
        st.dataframe(hr.rename(columns={"count": "投稿数", "mean": "平均反応", "median": "中央値反応"}))

    st.subheader("あり / なし比較")
    for label, col in [("外部リンク", "has_external_link"), ("CTA", "cta")]:
        if col == "cta":
            temp = analysis.copy()
            if "cta" in temp.columns:
                temp["has_cta"] = temp["cta"].fillna("").astype(str).str.len() > 0
                comp = mt.compare_flag_groups(posts, temp, "has_cta")
            else:
                comp = pd.DataFrame()
        else:
            comp = mt.compare_flag_groups(posts, analysis, col)
        if not comp.empty:
            st.markdown(f"**{label}あり / なし**")
            st.dataframe(comp.rename(columns={"count": "投稿数", "mean": "平均反応", "median": "中央値反応"}))
