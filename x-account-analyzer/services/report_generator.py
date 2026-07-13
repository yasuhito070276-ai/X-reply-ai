"""Markdown レポート生成。

ルールベースの分析結果から17セクション構成のレポートを組み立てる。
AI 分析結果（任意）があれば該当セクションに差し込む。
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from services import metrics as mt


def _fmt_top(series: pd.Series, n: int = 3) -> str:
    items = series.head(n)
    return "、".join(f"{idx}（{val}）" for idx, val in items.items()) if not items.empty else "データなし"


def _mode_or_empty(series: pd.Series, empty_msg: str = "データ不足で確認できない") -> str:
    s = series.dropna()
    s = s[s.astype(str).str.strip() != ""]
    if s.empty:
        return empty_msg
    top = s.value_counts().head(3)
    return "、".join(str(i) for i in top.index)


def build_report(
    account_name: str,
    merged: pd.DataFrame,
    overview: dict,
    cat_stats: pd.DataFrame,
    phases_df: pd.DataFrame,
    comparison30: dict | None,
    comparison7: dict | None,
    revenue_date: str | None,
    sales_start: str | None,
    top_posts_dict: dict[str, pd.DataFrame] | None = None,
    ai_sections: str | None = None,
    ai_zero_to_one: str | None = None,
) -> str:
    """17セクションの Markdown レポートを生成する。"""
    lines: list[str] = []
    add = lines.append

    est_note = "（インプレッション未提供のため推定指標を使用）" if overview.get("is_estimated") else ""

    add(f"# Xアカウント分析レポート: {account_name}")
    add(f"\n生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    add(f"分析期間: {overview.get('period_start')} 〜 {overview.get('period_end')}"
        f"（{overview.get('period_days')}日間 / {overview.get('total_posts')}投稿）")

    # 1. エグゼクティブサマリー
    add("\n## 1. エグゼクティブサマリー\n")
    top_cat = cat_stats.index[0] if not cat_stats.empty else "不明"
    add(f"- 総投稿数: **{overview.get('total_posts')}件**、1日平均 {overview.get('posts_per_day')}件")
    add(f"- 最も多い投稿カテゴリー: **{top_cat}**")
    add(f"- 平均エンゲージメントスコア: {overview.get('avg_engagement')} / 中央値: {overview.get('median_engagement')} {est_note}")
    add(f"- 初収益日: **{revenue_date or '未確定（候補検出または手動設定が必要）'}**")
    add(f"- 販売開始推定日: {sales_start or 'データから検出できず'}")

    # 2〜5. ポジショニング・ターゲット・悩み・未来
    add("\n## 2. アカウントのポジショニング\n")
    if not cat_stats.empty:
        top3 = "、".join(cat_stats.index[:3])
        add(f"投稿カテゴリーの中心は「{top3}」。この構成から、"
            f"主に「{top_cat}」を軸にした発信で認知を獲得するポジショニングと推定される。")
    add("※ 投稿データからの推定であり、プロフィール文等は分析対象外。")

    add("\n## 3. 想定ターゲット\n")
    add(f"投稿内で言及されている読者像: {_mode_or_empty(merged.get('assumed_reader', pd.Series(dtype=str)))}")

    add("\n## 4. 読者の悩み\n")
    add(f"投稿から抽出された悩みの表現: {_mode_or_empty(merged.get('reader_problem', pd.Series(dtype=str)))}")

    add("\n## 5. 提示している未来\n")
    add(f"投稿から抽出された未来像の表現: {_mode_or_empty(merged.get('promised_future', pd.Series(dtype=str)))}")

    # 6. 投稿戦略
    add("\n## 6. 投稿戦略\n")
    if not cat_stats.empty:
        add("| カテゴリー | 投稿数 | 構成比 |")
        add("|---|---|---|")
        for idx, row in cat_stats.head(8).iterrows():
            add(f"| {idx} | {int(row['投稿数'])} | {row['構成比(%)']}% |")

    # 7. 時系列フェーズ
    add("\n## 7. 時系列フェーズ\n")
    if phases_df is not None and not phases_df.empty:
        add("| フェーズ | 期間 | 判定 | 根拠 |")
        add("|---|---|---|---|")
        for _, p in phases_df.iterrows():
            mark = "推定" if p["estimated"] else "検出"
            add(f"| {p['phase']} | {p['start'].strftime('%Y-%m-%d')} 〜 {p['end'].strftime('%Y-%m-%d')} | {mark} | {p['basis']} |")
    else:
        add("フェーズを判定するにはデータが不足している。")

    # 8. 伸びた投稿の共通点
    add("\n## 8. 伸びた投稿の共通点\n")
    if top_posts_dict:
        like_top = top_posts_dict.get("いいね上位")
        if like_top is not None and not like_top.empty and "category_primary" in merged.columns:
            top_merged = like_top.merge(
                merged[["post_id", "category_primary"]], on="post_id", how="left", suffixes=("", "_a")
            )
            col = "category_primary_a" if "category_primary_a" in top_merged.columns else "category_primary"
            cats = top_merged[col].value_counts()
            add(f"いいね上位投稿のカテゴリー傾向: {_fmt_top(cats)}")
        for label, tdf in top_posts_dict.items():
            if tdf is not None and not tdf.empty:
                first = tdf.iloc[0]
                add(f"- **{label}** 例: 「{str(first['text'])[:50]}…」")
    else:
        add("データ不足で確認できない。")

    # 9. 信頼形成
    add("\n## 9. 信頼形成の仕組み\n")
    trust = merged[merged.get("category_primary", pd.Series(dtype=str)).isin(["実績", "権威付け", "教育"])] if "category_primary" in merged.columns else pd.DataFrame()
    add(f"実績・権威付け・教育カテゴリーの投稿は計 {len(trust)} 件。")
    if not trust.empty:
        add(f"例: 「{str(trust.iloc[0]['text'])[:60]}…」")

    # 10. 商品と販売導線
    add("\n## 10. 商品と販売導線\n")
    for label, col in [("外部リンク", "has_external_link"), ("LINE誘導", "has_line"),
                       ("note誘導", "has_note"), ("メルマガ誘導", "has_mailmag"),
                       ("商品言及", "has_product_mention")]:
        if col in merged.columns:
            cnt = int(merged[col].fillna(False).astype(bool).sum())
            add(f"- {label}: {cnt}件")
    add(f"- 販売開始推定日: {sales_start or '検出できず'}")

    # 11. 初収益前の変化
    add("\n## 11. 初収益前の変化\n")
    if comparison30 and comparison30["recent"]["posts"] > 0:
        r, p = comparison30["recent"], comparison30["prior"]
        add(f"直前30日: 投稿{r['posts']}件（1日{r['posts_per_day']}件）、平均反応{r['avg_engagement']}")
        add(f"\nその前30日: 投稿{p['posts']}件（1日{p['posts_per_day']}件）、平均反応{p['avg_engagement']}")
        diff = r["posts"] - p["posts"]
        add(f"\n投稿数の変化: {'+' if diff >= 0 else ''}{diff}件")
    else:
        add("初収益日が未設定、またはデータ不足のため比較できない。")
    if comparison7 and comparison7["recent"]["posts"] > 0:
        r, p = comparison7["recent"], comparison7["prior"]
        add(f"\n直前7日 vs その前7日: 投稿 {r['posts']} vs {p['posts']} 件、平均反応 {r['avg_engagement']} vs {p['avg_engagement']}")

    # 12. 0→1達成要因
    add("\n## 12. 0→1達成要因\n")
    if ai_zero_to_one:
        add(ai_zero_to_one)
    elif revenue_date:
        add("（ルールベース分析）初収益直前期の投稿カテゴリーと導線の変化から、"
            "販売投稿と外部誘導の組み合わせが直接要因と推測される。詳細はAI分析で深掘りできる。")
    else:
        add("初収益日が未設定のため分析できない。「0→1分析」画面で設定してほしい。")

    # 13. 再現性の評価
    add("\n## 13. 再現性の評価\n")
    if "reproducibility" in merged.columns:
        rep = merged["reproducibility"].value_counts()
        add(f"再現性「高」の投稿: {rep.get('高', 0)}件 / 「中」: {rep.get('中', 0)}件 / 「低」: {rep.get('低', 0)}件")
        add("\n再現性が高いのはノウハウ・教育・共感系の投稿。実績・権威付けに依存する投稿は発信者固有の要素が強い。")

    # 14. 真似すべきこと
    add("\n## 14. 真似すべきこと\n")
    add("- 投稿頻度を一定に保つ（分析対象の1日平均: " + str(overview.get("posts_per_day")) + "件）")
    if not cat_stats.empty:
        reproducible_cats = [c for c in cat_stats.index if c in ("ノウハウ", "教育", "共感", "交流")]
        if reproducible_cats:
            add(f"- 「{'」「'.join(reproducible_cats[:3])}」カテゴリーを中心にした発信構成")
    add("- 販売前に無料の価値提供（教育・ノウハウ）を積み上げる流れ")

    # 15. 真似すべきでないこと
    add("\n## 15. 真似すべきでないこと\n")
    add("- 発信者固有の実績・経歴（権威付け）をそのまま模倣すること")
    add("- 実績がない段階で実績風の投稿をすること（信頼を損なう）")

    # 16. 7日間の実行計画
    add("\n## 16. 7日間の実行計画\n")
    plan = _seven_day_plan(cat_stats)
    add(plan)

    # 17. 分析上の限界
    add("\n## 17. 分析上の限界\n")
    add("- 本分析は投稿テキストと公開指標のみに基づく。DM・スペース・外部媒体の活動は含まれない。")
    if overview.get("is_estimated"):
        add("- インプレッションデータがないため、エンゲージメントは推定指標を使用している。")
    add("- カテゴリー分類はキーワードベース（またはAI）の推定であり、誤分類の可能性がある。")
    add("- 初収益日は投稿の自己申告に基づく候補であり、実際の収益発生日と異なる可能性がある。")

    if ai_sections:
        add("\n---\n\n# AI分析による補足\n")
        add(ai_sections)

    return "\n".join(lines)


def _seven_day_plan(cat_stats: pd.DataFrame) -> str:
    """分析対象の投稿構成を参考にした7日間プラン。"""
    top_cats = list(cat_stats.index[:4]) if not cat_stats.empty else ["ノウハウ", "共感", "教育", "交流"]

    def pick(preferred: str, fallback: str) -> str:
        return preferred if preferred in top_cats else fallback

    days = [
        ("1日目", "自分の発信テーマと想定読者を1行で決め、自己紹介投稿をする", "ポジショニングの明確化"),
        ("2日目", f"「{pick('ノウハウ', 'ノウハウ')}」投稿を1件（読者がすぐ使えるコツ）", "分析対象の主要カテゴリー"),
        ("3日目", f"「{pick('共感', '共感')}」投稿を1件（読者の悩みを言語化）", "悩みの言語化による共感獲得"),
        ("4日目", "同じジャンルの発信者10人にいいね・リプで交流する", "交流による初期認知の獲得"),
        ("5日目", f"「{pick('教育', '教育')}」投稿を1件（考え方・マインド）", "信頼形成につながる教育投稿"),
        ("6日目", "自分の過去の失敗と学びをストーリーで投稿する", "ストーリーによる人間味の提示"),
        ("7日目", "1週間の反応を振り返り、反応が良かった型を翌週の軸にする", "データに基づく改善サイクル"),
    ]
    lines = ["| 日 | やること | 参考にした要素 |", "|---|---|---|"]
    lines += [f"| {d} | {action} | {basis} |" for d, action, basis in days]
    return "\n".join(lines)
