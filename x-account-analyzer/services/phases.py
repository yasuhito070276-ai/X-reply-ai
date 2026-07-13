"""時系列フェーズ分析。

投稿履歴をイベント（最初の外部誘導・商品言及・販売開始・初収益）と
カテゴリー構成の変化から、フェーズに自動分割する。
根拠が弱い区間は「推定」ラベルを付ける。
"""
from __future__ import annotations

import pandas as pd

PHASES = [
    "発信開始期", "認知獲得期", "共感形成期", "信頼構築期", "教育期",
    "商品準備期", "販売開始期", "初収益達成期", "拡大期",
]

# 各フェーズを特徴づける主分類カテゴリー
PHASE_HINT_CATEGORIES = {
    "認知獲得期": ["ノウハウ", "フォロー訴求", "交流"],
    "共感形成期": ["共感", "ストーリー", "日常"],
    "信頼構築期": ["実績", "権威付け", "教育"],
    "教育期": ["教育", "意見・主張", "問題提起"],
}


def detect_key_dates(merged: pd.DataFrame) -> dict:
    """販売開始・商品言及開始などの重要イベント日を検出する。"""
    dates: dict[str, pd.Timestamp | None] = {
        "first_post": None, "first_external": None, "first_product": None,
        "sales_start": None, "first_revenue_candidate": None,
    }
    if merged.empty:
        return dates
    d = merged.sort_values("created_at")
    dates["first_post"] = d["created_at"].iloc[0]

    ext = d[d.get("has_external_link", pd.Series(False, index=d.index)).fillna(False).astype(bool)]
    if not ext.empty:
        dates["first_external"] = ext["created_at"].iloc[0]

    # 販売開始: 単発の誤検出を避けるため、14日以内に2件以上の
    # 販売・商品告知投稿が集中する最初の時点を採用する
    sales = d[d["category_primary"].isin(["販売", "商品告知"])]
    sales_dates = list(sales["created_at"])
    for i, sd in enumerate(sales_dates):
        cluster = [x for x in sales_dates if sd <= x <= sd + pd.Timedelta(days=14)]
        if len(cluster) >= 2:
            dates["sales_start"] = sd
            break
    else:
        if sales_dates:  # クラスタがなければ最初の1件（根拠は弱い）
            dates["sales_start"] = sales_dates[0]

    # 商品準備の開始: 販売開始前60日以内の商品言及があればそれを優先する
    prod = d[d.get("has_product_mention", pd.Series(False, index=d.index)).fillna(False).astype(bool)]
    if not prod.empty:
        if dates["sales_start"] is not None:
            near = prod[
                (prod["created_at"] >= dates["sales_start"] - pd.Timedelta(days=60))
                & (prod["created_at"] < dates["sales_start"])
            ]
            dates["first_product"] = near["created_at"].iloc[0] if not near.empty else None
        else:
            dates["first_product"] = prod["created_at"].iloc[0]

    rev = d[d.get("is_revenue_candidate", pd.Series(False, index=d.index)).fillna(False).astype(bool)]
    if not rev.empty:
        best = rev.sort_values(["revenue_confidence", "created_at"], ascending=[False, True])
        dates["first_revenue_candidate"] = best["created_at"].iloc[0]
    return dates


def _dominant_phase(sub: pd.DataFrame) -> tuple[str, float]:
    """期間内の主分類構成から、最も当てはまるフェーズ名と強さを返す。"""
    if sub.empty:
        return "教育期", 0.0
    counts = sub["category_primary"].value_counts(normalize=True)
    best_phase, best_score = "教育期", 0.0
    for phase, cats in PHASE_HINT_CATEGORIES.items():
        score = sum(counts.get(c, 0.0) for c in cats)
        if score > best_score:
            best_phase, best_score = phase, score
    return best_phase, best_score


def detect_phases(merged: pd.DataFrame, revenue_date: pd.Timestamp | None = None) -> pd.DataFrame:
    """フェーズ区分を返す。

    戻り値の列: phase, start, end, estimated(bool), basis(判定根拠)
    merged は posts と analysis を post_id で結合した DataFrame。
    """
    if merged.empty:
        return pd.DataFrame(columns=["phase", "start", "end", "estimated", "basis"])

    d = merged.sort_values("created_at").reset_index(drop=True)
    d["created_at"] = pd.to_datetime(d["created_at"], utc=True)
    start = d["created_at"].iloc[0]
    end = d["created_at"].iloc[-1]
    dates = detect_key_dates(d)

    if revenue_date is not None:
        revenue_date = pd.Timestamp(revenue_date)
        if revenue_date.tzinfo is None:
            revenue_date = revenue_date.tz_localize("UTC")
    else:
        revenue_date = dates["first_revenue_candidate"]

    sales_start = dates["sales_start"]
    first_product = dates["first_product"]

    phases: list[dict] = []

    def add(phase: str, s, e, estimated: bool, basis: str):
        if s is not None and e is not None and s < e:
            phases.append({"phase": phase, "start": s, "end": e,
                           "estimated": estimated, "basis": basis})

    # 1. 発信開始期: 最初の30日間（または全体の10%の短い方）
    opening_end = min(start + pd.Timedelta(days=30), start + (end - start) * 0.15)
    add("発信開始期", start, opening_end, False, "発信開始からの初期期間")

    # 2. 中間期間: 商品準備期の前まで、4週間ごとに主分類からフェーズを推定
    mid_end = first_product or sales_start or revenue_date or end
    mid_end = max(mid_end, opening_end) if mid_end is not None else end
    cursor = opening_end
    while cursor < mid_end:
        seg_end = min(cursor + pd.Timedelta(days=28), mid_end)
        sub = d[(d["created_at"] >= cursor) & (d["created_at"] < seg_end)]
        phase, score = _dominant_phase(sub)
        basis = f"期間内の主分類構成（一致度 {score:.0%}）"
        estimated = score < 0.5
        # 直前と同じフェーズなら結合
        if phases and phases[-1]["phase"] == phase and phases[-1]["start"] >= opening_end:
            phases[-1]["end"] = seg_end
        else:
            add(phase, cursor, seg_end, estimated, basis)
        cursor = seg_end

    # 3. 商品準備期: 最初の商品言及 〜 販売開始
    if first_product is not None and sales_start is not None and first_product < sales_start:
        add("商品準備期", first_product, sales_start, False, "商品言及の開始〜販売カテゴリー投稿の開始")

    # 4. 販売開始期: 販売開始 〜 初収益（または終端）
    if sales_start is not None:
        sale_end = revenue_date if (revenue_date is not None and revenue_date > sales_start) else end
        add("販売開始期", sales_start, sale_end, False, "販売・商品告知カテゴリーの初出現")

    # 5. 初収益達成期・拡大期
    if revenue_date is not None and revenue_date <= end:
        ach_end = min(revenue_date + pd.Timedelta(days=14), end)
        add("初収益達成期", revenue_date, ach_end, revenue_date == dates["first_revenue_candidate"],
            "初収益日（候補検出または手動設定）")
        if ach_end < end:
            add("拡大期", ach_end, end, True, "初収益後の期間")

    result = pd.DataFrame(phases)
    if not result.empty:
        result = result.sort_values("start").reset_index(drop=True)
    return result
