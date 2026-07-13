"""レポート画面。17セクションのMarkdownレポート生成とダウンロード。"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from components import common
from database import db as dbm
from services import ai_analyzer as ai
from services import csv_importer
from services import metrics as mt
from services import phases as ph
from services import report_generator as rg

st.set_page_config(page_title="レポート", page_icon="📄", layout="wide")
st.title("📄 分析レポート")

dataset_id = common.select_dataset_sidebar()
if dataset_id is None:
    st.stop()

posts, analysis, merged, estimated = common.load_merged(dataset_id)
if posts.empty:
    st.info("このデータセットには投稿がありません。")
    st.stop()

conn = common.get_conn()
datasets = {d["id"]: d for d in dbm.list_datasets(conn)}
account_name = datasets.get(dataset_id, {}).get("name", "不明")
revenue_date = common.get_revenue_date(dataset_id)

# AIレポートを含めるかどうか
providers = ai.available_providers()
use_ai = False
provider = None
if len(providers) > 1:
    choice = st.selectbox(
        "レポートにAI分析を含めますか？（API利用料が発生します）",
        ["含めない（ルールベースのみ）"] + [p for p in providers if p != "AIを使用しない（ルールベース）"],
    )
    if choice != "含めない（ルールベースのみ）":
        use_ai = True
        provider = choice
else:
    st.caption("AIキーが未設定のため、ルールベースのレポートを生成します。")

if st.button("📝 レポートを生成する", type="primary"):
    with st.spinner("レポートを生成中…"):
        merged_local = merged.copy()
        merged_local["created_at"] = pd.to_datetime(merged_local["created_at"], utc=True)

        overview = mt.overview_stats(posts, estimated)
        cat_stats = mt.category_stats(posts, analysis)
        phases_df = ph.detect_phases(merged_local, pd.Timestamp(revenue_date) if revenue_date else None)
        key_dates = ph.detect_key_dates(merged_local)
        sales_start = key_dates["sales_start"].strftime("%Y-%m-%d") if key_dates["sales_start"] is not None else None
        tops = mt.top_posts(posts, analysis, n=5)

        comparison30 = comparison7 = None
        if revenue_date:
            pivot = pd.Timestamp(revenue_date).tz_localize("UTC")
            comparison30 = mt.compare_periods(posts, pivot, days=30)
            comparison7 = mt.compare_periods(posts, pivot, days=7)

        ai_sections = st.session_state.get("ai_period_summary")
        ai_zero = st.session_state.get("ai_zero_to_one")
        if use_ai and provider:
            try:
                context_parts = [
                    f"アカウント: {account_name}",
                    f"概要: {overview}",
                    f"カテゴリー統計:\n{cat_stats.to_string()}",
                    f"初収益日: {revenue_date or '未設定'}",
                ]
                if ai_sections:
                    context_parts.append(f"期間要約:\n{ai_sections}")
                if ai_zero:
                    context_parts.append(f"0→1分析:\n{ai_zero}")
                ai_report = ai.generate_report_sections(conn, provider, "\n\n".join(context_parts))
                ai_sections = (ai_sections or "") + "\n\n" + ai_report
            except ai.AIError as e:
                st.error(f"AIレポート生成に失敗したため、ルールベースのみで生成します: {e}")

        report_md = rg.build_report(
            account_name=account_name,
            merged=merged_local,
            overview=overview,
            cat_stats=cat_stats,
            phases_df=phases_df,
            comparison30=comparison30,
            comparison7=comparison7,
            revenue_date=revenue_date,
            sales_start=sales_start,
            top_posts_dict=tops,
            ai_sections=ai_sections,
            ai_zero_to_one=ai_zero,
        )
        st.session_state["report_md"] = report_md

        # exports フォルダにも保存
        exports_dir = Path(__file__).resolve().parent.parent / "exports"
        exports_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c for c in account_name if c.isalnum() or c in "-_@")[:40] or "report"
        out_path = exports_dir / f"report_{safe_name}_{stamp}.md"
        out_path.write_text(report_md, encoding="utf-8")
        st.session_state["report_path"] = str(out_path)

if st.session_state.get("report_md"):
    report_md = st.session_state["report_md"]
    if st.session_state.get("report_path"):
        st.success(f"保存しました: `{st.session_state['report_path']}`")

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "📥 Markdownをダウンロード",
            data=report_md.encode("utf-8"),
            file_name="x_account_report.md",
            mime="text/markdown",
        )
    with c2:
        export_df = merged.copy()
        if "category_secondary" in export_df.columns:
            export_df["category_secondary"] = export_df["category_secondary"].apply(
                lambda v: "、".join(v) if isinstance(v, list) else (v or "")
            )
        st.download_button(
            "📥 分析データ（CSV）をダウンロード",
            data=csv_importer.export_safe_csv(export_df),
            file_name="x_account_analysis.csv",
            mime="text/csv",
        )

    st.divider()
    st.markdown(report_md)
