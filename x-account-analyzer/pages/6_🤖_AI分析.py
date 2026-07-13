"""AI 分析画面。コスト見積 → テスト分析（100件） → 全件分析 → 期間要約 → 0→1詳細分析。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from components import common
from services import ai_analyzer as ai
from services import metrics as mt

st.set_page_config(page_title="AI分析", page_icon="🤖", layout="wide")
st.title("🤖 AI分析")

dataset_id = common.select_dataset_sidebar()
if dataset_id is None:
    st.stop()

posts, analysis, merged, estimated = common.load_merged(dataset_id)
if posts.empty:
    st.info("このデータセットには投稿がありません。")
    st.stop()

conn = common.get_conn()
providers = ai.available_providers()

st.markdown(
    """
AI分析は**任意**です。使わなくてもルールベース分析で全画面が動きます。

⚠️ **AI分析を実行すると、投稿テキストが選択したAI事業者（Anthropic または OpenAI）のサーバーへ送信されます。**
APIの利用料金が発生します。実行前に下の見積もりを確認してください。
"""
)

provider = st.selectbox("AIプロバイダー", providers)

if provider == "AIを使用しない（ルールベース）":
    st.info(
        "ルールベース分析は自動で実行済みです。AI分析を使うには `.env` に "
        "`ANTHROPIC_API_KEY` または `OPENAI_API_KEY` を設定してアプリを再起動してください。"
    )
    st.stop()

model = ai.resolve_model(provider)
st.caption(f"使用モデル: `{model}`（.env の ANTHROPIC_MODEL / OPENAI_MODEL で変更可能）")

# ---- コスト見積 ----
st.subheader("1️⃣ コスト見積もり")
est = ai.estimate_cost(len(posts))
c1, c2, c3, c4 = st.columns(4)
c1.metric("分析対象の投稿数", est["対象投稿数"])
c2.metric("推定バッチ数", est["推定バッチ数"])
c3.metric("推定トークン量", f"{est['推定トークン量']:,}")
c4.metric("推定API呼び出し回数", est["推定API呼び出し回数"])
st.caption("トークン量は概算です。実際の料金は各AI事業者の料金ページで確認してください。")

# 進捗の表示
ai_done = 0
if not analysis.empty and "engine" in analysis.columns:
    ai_done = int((analysis["engine"] == "ai").sum())
st.progress(min(ai_done / max(len(posts), 1), 1.0), text=f"AI分類済み: {ai_done} / {len(posts)}件")

# ---- 投稿分類 ----
st.subheader("2️⃣ 投稿分類（多段階分析の第1段階）")
st.caption("投稿を20件ずつのバッチに分けてAIで分類します。分類済みの投稿はスキップされるため、途中で失敗しても再開できます。")

col1, col2 = st.columns(2)
run_test = col1.button("🧪 テスト分析（最初の100件のみ）", type="secondary")
run_full = col2.button("🚀 全件分析を実行", type="primary",
                       disabled=ai_done == 0 and len(posts) > 100 and not st.session_state.get("test_done"))
if ai_done == 0 and len(posts) > 100:
    col2.caption("まずテスト分析で結果を確認してから全件分析に進んでください。")

if run_test or run_full:
    limit = 100 if run_test else None
    progress = st.progress(0, text="AI分類を実行中…")

    def on_progress(done, total):
        progress.progress(done / max(total, 1), text=f"AI分類中… バッチ {done}/{total}")

    analyzed, skipped, errors = ai.classify_posts_ai(
        conn, provider, posts, dataset_id, limit=limit, progress_callback=on_progress
    )
    progress.progress(1.0, text="完了")
    st.success(f"AI分類が完了しました: 新規 {analyzed}件 / スキップ（分析済み） {skipped}件")
    if run_test:
        st.session_state["test_done"] = True
    for e in errors:
        st.error(e)
    if errors:
        st.info("💡 エラーになったバッチは保存されていません。もう一度実行すると、失敗した分だけ再試行されます（途中から再開）。")
    st.rerun()

st.divider()

# ---- 期間要約と0→1分析 ----
st.subheader("3️⃣ 期間要約（第2〜4段階）")
st.caption("週別のカテゴリー構成と投稿例をAIに渡して、発信内容の変化点を分析します（投稿全文は送信しません）。")
if st.button("📅 期間要約を実行"):
    try:
        with st.spinner("期間要約を生成中…"):
            summary = ai.summarize_periods(conn, provider, merged, freq="W")
        st.session_state["ai_period_summary"] = summary
    except ai.AIError as e:
        st.error(str(e))
if st.session_state.get("ai_period_summary"):
    st.markdown(st.session_state["ai_period_summary"])

st.subheader("4️⃣ 0→1詳細分析（第5段階）")
revenue_date = common.get_revenue_date(dataset_id)
if not revenue_date:
    st.info("先に「0→1分析」画面で初収益日を設定してください。")
else:
    st.caption(f"初収益日 {revenue_date} の前後を詳細分析します。")
    if st.button("🎯 0→1詳細分析を実行"):
        try:
            pivot = pd.Timestamp(revenue_date)
            comp = mt.compare_periods(posts, pivot.tz_localize("UTC"), days=30)
            comp_slim = {"recent": comp["recent"], "prior": comp["prior"]}
            with st.spinner("0→1分析を生成中…"):
                result = ai.analyze_zero_to_one(conn, provider, merged, pivot, comp_slim)
            st.session_state["ai_zero_to_one"] = result
        except ai.AIError as e:
            st.error(str(e))
if st.session_state.get("ai_zero_to_one"):
    st.markdown(st.session_state["ai_zero_to_one"])

st.divider()
st.caption(
    "AI分析の結果はSQLiteにキャッシュされ、同じ内容を二度分析することはありません。"
    "プロンプトとモデル名も保存されるため、後から再現できます。"
)
