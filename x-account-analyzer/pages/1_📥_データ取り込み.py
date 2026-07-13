"""データ取り込み画面（CSV アップロード / X 公式 API）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from components import common
from database import db as dbm
from services import csv_importer, x_api

st.set_page_config(page_title="データ取り込み", page_icon="📥", layout="wide")
st.title("📥 データ取り込み")

conn = common.get_conn()

tab_csv, tab_api = st.tabs(["📄 CSVアップロード（推奨）", "🔑 X公式API"])

# ------------------------------------------------------------------
# CSV アップロード
# ------------------------------------------------------------------
with tab_csv:
    st.markdown(
        f"""
必須列は **post_id / created_at / text** の3つです（日本語列名でもOK。下でマッピングできます）。
ファイルサイズ上限: {csv_importer.MAX_FILE_SIZE_MB}MB
"""
    )
    uploaded = st.file_uploader("CSVファイルを選択", type=["csv"])

    if uploaded is not None:
        try:
            raw_df = csv_importer.read_csv_bytes(uploaded.getvalue())
        except ValueError as e:
            st.error(str(e))
            st.stop()

        st.success(f"読み込みOK: {len(raw_df)}行 × {len(raw_df.columns)}列")
        st.markdown("#### 1. 列マッピング")
        st.caption("CSVの列を、分析で使う項目に対応付けます。自動で推測していますが、必要なら変更してください。")

        suggested = csv_importer.suggest_mapping(list(raw_df.columns))
        csv_columns = ["（使わない）"] + list(raw_df.columns)

        mapping: dict[str, str | None] = {}
        cols = st.columns(3)
        labels = {
            "post_id": "投稿ID（必須）", "created_at": "投稿日時（必須）", "text": "本文（必須）",
            "impressions": "インプレッション", "likes": "いいね", "replies": "返信",
            "reposts": "リポスト", "bookmarks": "ブックマーク", "quotes": "引用",
            "url": "投稿URL", "media_type": "メディア種別", "followers_count": "フォロワー数",
        }
        for i, (internal, label) in enumerate(labels.items()):
            default = suggested.get(internal)
            idx = csv_columns.index(default) if default in csv_columns else 0
            with cols[i % 3]:
                chosen = st.selectbox(label, csv_columns, index=idx, key=f"map_{internal}")
            mapping[internal] = None if chosen == "（使わない）" else chosen

        st.markdown("#### 2. プレビュー")
        st.dataframe(raw_df.head(5), use_container_width=True)

        st.markdown("#### 3. 取り込み")
        default_name = Path(uploaded.name).stem
        dataset_name = st.text_input("データセット名（アカウント名など）", value=default_name, max_chars=100)

        if st.button("✅ この内容で取り込む", type="primary"):
            try:
                normalized, warnings = csv_importer.normalize_posts(raw_df, mapping)
            except ValueError as e:
                st.error(str(e))
                st.stop()
            if normalized.empty:
                st.error("取り込める行がありませんでした。列マッピングと日付形式を確認してください。")
                st.stop()
            for w in warnings:
                st.warning(w)
            dataset_id = dbm.create_dataset(conn, dataset_name.strip() or default_name, source="csv")
            inserted, skipped = dbm.insert_posts(conn, dataset_id, normalized)
            st.session_state["dataset_id"] = dataset_id
            st.success(f"取り込み完了: {inserted}件を保存しました（重複スキップ: {skipped}件）。")
            st.info("左メニューの「概要」から分析結果を確認できます。初回はルールベース分析が自動で実行されます。")

# ------------------------------------------------------------------
# X 公式 API
# ------------------------------------------------------------------
with tab_api:
    st.markdown(
        """
**X公式API（API v2）** で公開投稿を取得します。無許可スクレイピングは行いません。

- `.env` ファイルに `X_BEARER_TOKEN` の設定が必要です（設定方法はREADME参照）
- 無料プランでは取得できない場合があります。その場合はCSV方式をご利用ください
- インプレッション数は、APIの権限によっては取得できないことがあります
"""
    )
    if not x_api.is_configured():
        st.warning(
            "X_BEARER_TOKEN が設定されていないため、この機能は使えません。"
            "`.env.example` を `.env` にコピーしてトークンを設定するか、CSVアップロードをご利用ください。"
        )
    else:
        st.success("X APIトークンが設定されています。")
        username = st.text_input("ユーザー名（@は不要）", placeholder="例: example_user")
        c1, c2 = st.columns(2)
        with c1:
            max_posts = st.number_input("取得件数の上限", min_value=10, max_value=3200, value=500, step=10)
            include_rt = st.checkbox("リポストを含める", value=False)
        with c2:
            date_range = st.date_input("取得期間（任意・空欄で全期間）", value=(), help="開始日と終了日を選択")
            include_replies = st.checkbox("返信を含める", value=False)

        if st.button("🚀 取得を開始", type="primary", disabled=not username):
            try:
                with st.spinner("ユーザー情報を取得中…"):
                    user = x_api.get_user_by_username(username)
                st.info(
                    f"対象: {user.get('name')}（@{user.get('username')}） / "
                    f"フォロワー {user.get('public_metrics', {}).get('followers_count', '?')}人"
                )
                start_time = end_time = None
                if isinstance(date_range, tuple) and len(date_range) == 2:
                    start_time = f"{date_range[0].isoformat()}T00:00:00Z"
                    end_time = f"{date_range[1].isoformat()}T23:59:59Z"

                progress = st.progress(0, text="投稿を取得中…")

                def on_progress(n):
                    progress.progress(min(n / max_posts, 1.0), text=f"投稿を取得中… {n}件")

                partial_posts = []
                try:
                    posts = x_api.fetch_user_tweets(
                        user["id"], max_posts=int(max_posts),
                        include_retweets=include_rt, include_replies=include_replies,
                        start_time=start_time, end_time=end_time,
                        progress_callback=on_progress,
                    )
                except x_api.XApiError as e:
                    partial_posts = getattr(e, "partial", [])
                    if not partial_posts:
                        raise
                    st.warning(f"{e.message} 取得済みの {len(partial_posts)}件のみ保存します。")
                    posts = partial_posts

                if not posts:
                    st.warning("投稿を取得できませんでした。期間設定やユーザー名を確認してください。")
                else:
                    df = pd.DataFrame(posts)
                    followers = user.get("public_metrics", {}).get("followers_count")
                    if followers is not None:
                        df["followers_count"] = followers
                    dataset_id = dbm.create_dataset(conn, f"@{user.get('username')}", source="api")
                    inserted, skipped = dbm.insert_posts(conn, dataset_id, df)
                    st.session_state["dataset_id"] = dataset_id
                    st.success(f"取得完了: {inserted}件を保存しました（重複スキップ: {skipped}件）。")
            except x_api.XApiError as e:
                st.error(e.message)
                if e.suggest_csv:
                    st.info("💡 CSVアップロード方式なら、APIの契約プランに関係なく分析できます。")
