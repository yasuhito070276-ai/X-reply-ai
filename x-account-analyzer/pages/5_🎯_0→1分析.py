"""0→1（初収益）分析画面。候補の確認・確定と、初収益前の行動変化の分析。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from components import common
from services import metrics as mt

st.set_page_config(page_title="0→1分析", page_icon="🎯", layout="wide")
st.title("🎯 0→1（初収益）分析")

dataset_id = common.select_dataset_sidebar()
if dataset_id is None:
    st.stop()

posts, analysis, merged, estimated = common.load_merged(dataset_id)
if posts.empty:
    st.info("このデータセットには投稿がありません。")
    st.stop()

merged["created_at"] = pd.to_datetime(merged["created_at"], utc=True)
revenue_date = common.get_revenue_date(dataset_id)

# ------------------------------------------------------------------
# 初収益候補の一覧と確定
# ------------------------------------------------------------------
st.subheader("💰 初収益候補の投稿")

if revenue_date:
    c1, c2 = st.columns([3, 1])
    c1.success(f"初収益日: **{revenue_date}**（設定済み）")
    if c2.button("設定を解除"):
        common.set_revenue_date(dataset_id, None)
        st.rerun()

candidates = merged[merged.get("is_revenue_candidate", pd.Series(False)).fillna(False).astype(bool)]
candidates = candidates.sort_values("revenue_confidence", ascending=False)

if candidates.empty:
    st.info("初収益候補の投稿は検出されませんでした。下の手動設定をご利用ください。")
else:
    st.caption(f"{len(candidates)}件の候補が見つかりました。内容を確認し、初収益日として設定してください。")
    for _, row in candidates.head(10).iterrows():
        date_str = row["created_at"].strftime("%Y-%m-%d")
        conf = float(row.get("revenue_confidence", 0))
        with st.expander(f"📌 {date_str} — 確信度 {conf:.0%}", expanded=False):
            st.markdown(f"> {str(row['text'])[:500]}")
            st.caption(f"該当理由: {row.get('revenue_reason', '')}")
            if isinstance(row.get("url"), str) and row["url"]:
                st.caption(f"投稿URL: {row['url']}")

            # 前後7日間の投稿
            pivot = row["created_at"]
            around = merged[
                (merged["created_at"] >= pivot - pd.Timedelta(days=7))
                & (merged["created_at"] <= pivot + pd.Timedelta(days=7))
                & (merged["post_id"] != row["post_id"])
            ]
            st.markdown(f"**前後7日間の投稿（{len(around)}件）**")
            for _, a in around.head(10).iterrows():
                st.caption(f"{a['created_at'].strftime('%m/%d')} [{a.get('category_primary', '?')}] {str(a['text'])[:60]}")

            # 前後30日間の傾向
            before30 = merged[(merged["created_at"] >= pivot - pd.Timedelta(days=30)) & (merged["created_at"] < pivot)]
            after30 = merged[(merged["created_at"] > pivot) & (merged["created_at"] <= pivot + pd.Timedelta(days=30))]
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**前30日**: {len(before30)}件")
                if not before30.empty:
                    st.caption("、".join(f"{k} {v}件" for k, v in before30["category_primary"].value_counts().head(3).items()))
            with c2:
                st.markdown(f"**後30日**: {len(after30)}件")
                if not after30.empty:
                    st.caption("、".join(f"{k} {v}件" for k, v in after30["category_primary"].value_counts().head(3).items()))

            if st.button(f"✅ {date_str} を初収益日として設定する", key=f"set_rev_{row['post_id']}"):
                common.set_revenue_date(dataset_id, date_str)
                st.rerun()

with st.expander("✏️ 初収益日を手動で設定する"):
    manual = st.date_input("初収益日", value=None, key="manual_revenue")
    if st.button("この日付で設定する") and manual:
        common.set_revenue_date(dataset_id, manual.isoformat())
        st.rerun()

st.divider()

# ------------------------------------------------------------------
# 初収益前の行動変化
# ------------------------------------------------------------------
st.subheader("📊 初収益前の行動変化")

if not revenue_date:
    st.info("初収益日を設定すると、直前30日 / 7日の行動変化を分析できます。")
    st.stop()

pivot = pd.Timestamp(revenue_date).tz_localize("UTC")
common.estimated_badge(estimated)

for days in (30, 7):
    comp = mt.compare_periods(posts, pivot, days=days)
    r, p = comp["recent"], comp["prior"]
    st.markdown(f"#### 直前{days}日間 vs その前{days}日間")
    c1, c2, c3 = st.columns(3)
    c1.metric("投稿数", f"{r['posts']}件", delta=r["posts"] - p["posts"])
    c2.metric("1日平均投稿数", r["posts_per_day"], delta=round(r["posts_per_day"] - p["posts_per_day"], 2))
    c3.metric("平均反応スコア", r["avg_engagement"], delta=round(r["avg_engagement"] - p["avg_engagement"], 1))

# カテゴリー・行動の変化
recent_m = merged[(merged["created_at"] >= pivot - pd.Timedelta(days=30)) & (merged["created_at"] < pivot)]
prior_m = merged[(merged["created_at"] >= pivot - pd.Timedelta(days=60)) & (merged["created_at"] < pivot - pd.Timedelta(days=30))]

st.markdown("#### 増えた行動・減った行動（直前30日 vs その前30日）")
rc = recent_m["category_primary"].value_counts()
pc = prior_m["category_primary"].value_counts()
all_cats = sorted(set(rc.index) | set(pc.index))
diff_rows = []
for cat in all_cats:
    a, b = int(rc.get(cat, 0)), int(pc.get(cat, 0))
    diff_rows.append({"カテゴリー": cat, "その前30日": b, "直前30日": a, "増減": a - b})
diff_df = pd.DataFrame(diff_rows).sort_values("増減", ascending=False)
st.dataframe(diff_df, use_container_width=True, hide_index=True)

increased = diff_df[diff_df["増減"] > 0]["カテゴリー"].tolist()
decreased = diff_df[diff_df["増減"] < 0]["カテゴリー"].tolist()
new_actions = diff_df[(diff_df["その前30日"] == 0) & (diff_df["直前30日"] > 0)]["カテゴリー"].tolist()

c1, c2, c3 = st.columns(3)
with c1:
    st.markdown("**📈 増えた行動**")
    st.write("、".join(increased) if increased else "なし")
with c2:
    st.markdown("**📉 減った行動**")
    st.write("、".join(decreased) if decreased else "なし")
with c3:
    st.markdown("**🆕 新しく始めた行動**")
    st.write("、".join(new_actions) if new_actions else "なし")

# 販売導線
st.markdown("#### 🛒 販売導線（直前30日間）")
funnel = []
for label, col in [("外部リンク", "has_external_link"), ("LINE誘導", "has_line"),
                   ("note誘導", "has_note"), ("メルマガ誘導", "has_mailmag"),
                   ("商品言及", "has_product_mention"), ("フォロー訴求", "has_follow_cta")]:
    if col in recent_m.columns:
        a = int(recent_m[col].fillna(False).astype(bool).sum())
        b = int(prior_m[col].fillna(False).astype(bool).sum())
        funnel.append({"導線": label, "その前30日": b, "直前30日": a, "増減": a - b})
st.dataframe(pd.DataFrame(funnel), use_container_width=True, hide_index=True)

# 要因の整理（ルールベース）
st.markdown("#### 🔍 要因の整理（ルールベース推定）")
sales_posts = recent_m[recent_m["category_primary"].isin(["販売", "商品告知"])]
st.markdown(
    f"""
- **直接要因（推定）**: 直前30日間の販売・商品告知投稿 **{len(sales_posts)}件** と、
  外部誘導 **{int(recent_m.get('has_external_link', pd.Series(dtype=bool)).fillna(False).astype(bool).sum())}件** の組み合わせ
- **間接要因（推定）**: それ以前に積み上げた
  教育 {int((merged['category_primary'] == '教育').sum())}件 /
  ノウハウ {int((merged['category_primary'] == 'ノウハウ').sum())}件 /
  共感 {int((merged['category_primary'] == '共感').sum())}件 の投稿による信頼形成
- **再現可能な施策**: 投稿頻度の維持、無料の価値提供 → 商品告知 → 販売の順序
- **再現困難な要素**: 発信者固有の実績・経歴・人脈（権威付け {int((merged['category_primary'] == '権威付け').sum())}件）
"""
)
st.caption("※ これはデータに基づく推定です。より詳しい分析は「AI分析」ページで実行できます。")
