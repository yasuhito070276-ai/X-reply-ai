"""X アカウント 0→1 分析ツール — ホーム画面。

起動方法:  streamlit run app.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from components import common
from database import db as dbm
from services import csv_importer

st.set_page_config(page_title="Xアカウント 0→1 分析ツール", page_icon="📊", layout="wide")

st.title("📊 Xアカウント 0→1 分析ツール")

st.markdown(
    """
参考にしたい X アカウントの投稿データを時系列で分析し、
**どうやって認知・フォロワー・信頼を積み上げ、初収益（0→1）を達成したのか** を解き明かすツールです。

#### 使い方（3ステップ）

1. **データ取り込み** — CSVファイルをアップロード（または X 公式APIで取得）
2. **分析画面を見る** — 概要 / 時系列 / 投稿分析 / 0→1分析 を確認
3. **レポート生成** — 17セクションの分析レポートをMarkdownでダウンロード

#### 大切なこと

- 🔒 データはすべて **あなたのPCの中（SQLite）** に保存されます
- 🚫 無許可のスクレイピングは行いません。CSVか **X公式API** のみ対応です
- 🤖 AI分析は任意です。**APIキーがなくてもルールベース分析で全機能が動きます**
- 📤 AI分析を使う場合のみ、投稿テキストが選択したAI事業者（Anthropic / OpenAI）に送信されます
"""
)

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("🆕 新規分析を始める")
    st.markdown("左のメニューから **「データ取り込み」** を開いて、CSVをアップロードしてください。")
    st.download_button(
        "📄 CSVテンプレートをダウンロード",
        data=csv_importer.template_csv(),
        file_name="template_posts.csv",
        mime="text/csv",
        help="必須列: post_id, created_at, text。日本語の列名でも取り込み時にマッピングできます。",
    )
    sample_path = Path(__file__).parent / "sample_data" / "sample_posts.csv"
    if sample_path.exists():
        st.download_button(
            "🧪 架空のサンプルデータをダウンロード（動作確認用）",
            data=sample_path.read_bytes(),
            file_name="sample_posts.csv",
            mime="text/csv",
        )

with col2:
    st.subheader("💾 保存済みの分析")
    conn = common.get_conn()
    datasets = dbm.list_datasets(conn)
    if not datasets:
        st.info("保存済みのデータはまだありません。")
    else:
        for d in datasets:
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.markdown(f"**{d['name']}**（{d['post_count']}件 / {d['source']}）")
            if c2.button("開く", key=f"open_{d['id']}"):
                st.session_state["dataset_id"] = d["id"]
                st.switch_page("pages/2_📊_概要.py")
            if c3.button("削除", key=f"del_{d['id']}"):
                st.session_state[f"confirm_del_{d['id']}"] = True
            if st.session_state.get(f"confirm_del_{d['id']}"):
                st.warning(f"「{d['name']}」を削除しますか？ この操作は取り消せません。")
                if st.button("はい、削除します", key=f"del_yes_{d['id']}"):
                    dbm.delete_dataset(conn, d["id"])
                    st.session_state.pop(f"confirm_del_{d['id']}", None)
                    st.rerun()

st.divider()
st.caption(
    "⚠️ 本ツールの分析は投稿テキストと公開指標に基づく推定です。"
    "初収益日などは投稿の自己申告に基づく候補であり、正確性を保証するものではありません。"
)
