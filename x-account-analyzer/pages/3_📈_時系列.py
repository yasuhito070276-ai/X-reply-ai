"""時系列画面。投稿数・エンゲージメント・カテゴリー構成の推移とフェーズ区分。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from components import common
from services import metrics as mt
from services import phases as ph

st.set_page_config(page_title="時系列", page_icon="📈", layout="wide")
st.title("📈 時系列分析")

dataset_id = common.select_dataset_sidebar()
if dataset_id is None:
    st.stop()

posts, analysis, merged, estimated = common.load_merged(dataset_id)
if posts.empty:
    st.info("このデータセットには投稿がありません。")
    st.stop()

common.estimated_badge(estimated)

freq_label = st.radio("集計単位", ["日", "週", "月"], index=1, horizontal=True)
freq = {"日": "D", "週": "W", "月": "ME"}[freq_label]

revenue_date = common.get_revenue_date(dataset_id)
key_dates = ph.detect_key_dates(merged)
sales_start = key_dates["sales_start"]

_LAYOUT = dict(
    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified",
)


def add_event_lines(fig: go.Figure) -> None:
    """販売開始・初収益日の縦線をグラフに追加する。"""
    if sales_start is not None:
        fig.add_vline(x=sales_start.timestamp() * 1000, line_dash="dash", line_color="#eda100")
        fig.add_annotation(x=sales_start, y=1, yref="paper", text="販売開始(推定)",
                           showarrow=False, font=dict(color="#eda100", size=11))
    if revenue_date:
        rd = pd.Timestamp(revenue_date).tz_localize("UTC")
        fig.add_vline(x=rd.timestamp() * 1000, line_dash="dash", line_color="#e34948")
        fig.add_annotation(x=rd, y=0.92, yref="paper", text="初収益日",
                           showarrow=False, font=dict(color="#e34948", size=11))


# ---- 投稿数の推移 ----
st.subheader("投稿数の推移")
counts = mt.posts_per_period(posts, freq)
fig = go.Figure(go.Bar(x=counts["period"], y=counts["count"], name="投稿数",
                       marker_color=common.CHART_PRIMARY))
fig.update_layout(**_LAYOUT, yaxis_title="投稿数")
add_event_lines(fig)
st.plotly_chart(fig, use_container_width=True)

# ---- エンゲージメントの推移 ----
label = "反応スコア（推定）" if estimated else "エンゲージメント"
st.subheader(f"{label}の推移")
d = posts.copy()
d["created_at"] = pd.to_datetime(d["created_at"], utc=True)
eng = d.set_index("created_at")["engagement_score"].resample(freq).agg(["mean", "median"]).reset_index()
fig = go.Figure()
fig.add_trace(go.Scatter(x=eng["created_at"], y=eng["mean"], name="平均",
                         line=dict(color=common.CHART_COLORS[0], width=2)))
fig.add_trace(go.Scatter(x=eng["created_at"], y=eng["median"], name="中央値",
                         line=dict(color=common.CHART_COLORS[1], width=2)))
fig.update_layout(**_LAYOUT, yaxis_title=label)
add_event_lines(fig)
st.plotly_chart(fig, use_container_width=True)

# ---- カテゴリー構成の推移 ----
st.subheader("投稿カテゴリーの推移")
m = merged.copy()
m["created_at"] = pd.to_datetime(m["created_at"], utc=True)
top_cats = list(m["category_primary"].value_counts().head(7).index)
m["cat_display"] = m["category_primary"].where(m["category_primary"].isin(top_cats), "その他まとめ")
pivot = (
    m.set_index("created_at").groupby("cat_display").resample(freq).size()
    .unstack(level=0).fillna(0)
)
color_map = common.category_color_map(top_cats)
color_map["その他まとめ"] = common.CHART_GRAY
fig = go.Figure()
for cat in [c for c in top_cats + ["その他まとめ"] if c in pivot.columns]:
    fig.add_trace(go.Bar(x=pivot.index, y=pivot[cat], name=cat, marker_color=color_map[cat]))
fig.update_layout(**_LAYOUT, barmode="stack", yaxis_title="投稿数",
                  legend=dict(orientation="h", y=-0.15))
add_event_lines(fig)
st.plotly_chart(fig, use_container_width=True)

# ---- フェーズ区分 ----
st.subheader("フェーズ区分")
st.caption("投稿カテゴリー構成・商品言及・販売投稿・初収益候補から自動推定しています。「推定」印は根拠が弱い区間です。")
phases_df = ph.detect_phases(merged, pd.Timestamp(revenue_date) if revenue_date else None)
if phases_df.empty:
    st.info("フェーズを判定できるだけのデータがありません。")
else:
    phase_colors = common.category_color_map(list(dict.fromkeys(phases_df["phase"])))
    fig = go.Figure()
    for _, p in phases_df.iterrows():
        fig.add_trace(go.Bar(
            x=[(p["end"] - p["start"]).days or 1], y=["フェーズ"],
            base=[p["start"]], orientation="h",
            name=p["phase"] + ("（推定）" if p["estimated"] else ""),
            marker_color=phase_colors.get(p["phase"], common.CHART_GRAY),
            hovertext=f"{p['phase']}: {p['start'].strftime('%Y-%m-%d')}〜{p['end'].strftime('%Y-%m-%d')}<br>{p['basis']}",
            hoverinfo="text",
        ))
    fig.update_layout(**_LAYOUT, barmode="stack", height=180, xaxis_type="date",
                      legend=dict(orientation="h", y=-0.4), showlegend=True)
    st.plotly_chart(fig, use_container_width=True)

    table = phases_df.copy()
    table["期間"] = table["start"].dt.strftime("%Y-%m-%d") + " 〜 " + table["end"].dt.strftime("%Y-%m-%d")
    table["判定"] = table["estimated"].map({True: "推定", False: "検出"})
    st.dataframe(
        table[["phase", "期間", "判定", "basis"]].rename(columns={"phase": "フェーズ", "basis": "根拠"}),
        use_container_width=True, hide_index=True,
    )
