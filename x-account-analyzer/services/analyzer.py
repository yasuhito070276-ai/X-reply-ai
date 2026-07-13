"""ルールベース分析。

AI を使わずに、キーワードと正規表現で投稿を分類・要素抽出する。
AI 分析（ai_analyzer.py）が使えない環境でも、この モジュールだけで
アプリの基本機能がすべて動く。
"""
from __future__ import annotations

import re

import pandas as pd

from models.schemas import CATEGORIES, PostAnalysis

# ---------------------------------------------------------------
# カテゴリー分類キーワード（カテゴリー名: [(キーワード, 重み), ...]）
# ---------------------------------------------------------------
CATEGORY_KEYWORDS: dict[str, list[tuple[str, float]]] = {
    "販売": [
        ("募集開始", 3), ("販売開始", 3), ("発売しました", 3), ("購入はこちら", 3),
        ("残り", 1.5), ("先着", 2), ("値上げ", 2), ("特典", 1.5), ("〆切", 2),
        ("締め切り", 2), ("価格", 1.5), ("円で販売", 3), ("お申し込み", 2), ("購入", 1.5),
    ],
    "商品告知": [
        ("リリース", 2), ("新商品", 3), ("講座", 1.5), ("コンサル", 1.5),
        ("Brain", 2), ("サービスを開始", 3), ("商品を作", 2), ("公開しました", 2),
        ("noteを公開", 2.5), ("noteで公開", 2.5), ("有料note", 3), ("近日公開", 2.5),
        ("販売中", 2), ("発売", 2),
    ],
    "外部誘導": [
        ("プロフィールのリンク", 3), ("プロフのリンク", 3), ("固定ツイート", 2), ("固定ポスト", 2),
        ("公式LINE", 3), ("LINE登録", 3), ("メルマガ", 2.5), ("登録はこちら", 3),
        ("受け取ってください", 2), ("プレゼント", 1.5), ("無料配布", 2.5), ("詳しくはこちら", 2),
        ("リンクから", 2), ("こちらから", 1.5),
    ],
    "フォロー訴求": [
        ("フォローしてね", 3), ("フォローお願い", 3), ("フォローすると", 2.5),
        ("フォロー必須", 2.5), ("いいねした人", 2), ("拡散希望", 2), ("RTお願い", 2),
        ("フォロバ", 2), ("相互", 1.5),
    ],
    "実績": [
        ("達成", 2), ("突破", 2), ("万円", 1.5), ("収益", 1.5), ("売上", 1.5),
        ("実績", 2), ("成果", 1.5), ("記録更新", 2), ("過去最高", 2),
    ],
    "権威付け": [
        ("元・", 2), ("歴10年", 2), ("年の経験", 2), ("資格", 1.5), ("メディア掲載", 3),
        ("監修", 2.5), ("取材", 2), ("受賞", 2.5), ("認定", 1.5),
    ],
    "教育": [
        ("とは", 1), ("本質", 2), ("理由", 1), ("なぜ", 1), ("大切なこと", 1.5),
        ("マインド", 1.5), ("考え方", 1.5), ("学び", 1.5), ("気づき", 1.5), ("重要", 1),
    ],
    "ノウハウ": [
        ("方法", 1.5), ("コツ", 2), ("手順", 2), ("ステップ", 2), ("テンプレ", 2.5),
        ("やり方", 2), ("使い方", 1.5), ("選", 1), ("チェックリスト", 2.5), ("解説", 1.5),
        ("初心者向け", 1.5), ("まとめ", 1),
    ],
    "共感": [
        ("わかる", 1.5), ("ですよね", 1.5), ("悩み", 1.5), ("不安", 1.5), ("つらい", 2),
        ("しんどい", 2), ("疲れた", 1.5), ("同じ気持ち", 2.5), ("あるある", 2), ("大丈夫", 1),
    ],
    "ストーリー": [
        ("昔の私", 2.5), ("あの頃", 2), ("過去の自分", 2.5), ("きっかけ", 1.5),
        ("挫折", 2), ("失敗談", 2.5), ("振り返る", 1.5), ("1年前", 1.5), ("当時", 1.5),
        ("変われた", 1.5),
    ],
    "日常": [
        ("おはよう", 1.5), ("今日は", 1), ("ランチ", 2), ("カフェ", 1.5), ("天気", 1.5),
        ("休日", 1.5), ("散歩", 2), ("子ども", 1), ("おやすみ", 1.5),
    ],
    "意見・主張": [
        ("と思う", 1), ("べき", 1.5), ("断言", 2.5), ("正直", 1.5), ("ぶっちゃけ", 2),
        ("持論", 2.5), ("あえて言う", 2.5), ("反対", 1.5),
    ],
    "問題提起": [
        ("ではないでしょうか", 1.5), ("どうして", 1), ("問題", 1.5), ("危険", 2),
        ("注意", 1.5), ("もったいない", 1.5), ("落とし穴", 2.5), ("勘違い", 2),
    ],
    "交流": [
        ("ありがとうございます", 1.5), ("感謝", 1.5), ("リプ", 1), ("企画", 1.5),
        ("参加", 1), ("絡んで", 2), ("教えてください", 1.5), ("募集します", 1),
    ],
}

# ---------------------------------------------------------------
# 初収益・成約候補の検出
# ---------------------------------------------------------------
REVENUE_KEYWORDS = [
    "初収益", "初成約", "初めて売れた", "はじめて売れた", "1件売れた", "一件売れた",
    "初報酬", "収益発生", "売上発生", "購入されました", "申し込みが入", "成約しました",
    "初案件", "0→1", "0→1", "ゼロイチ", "報酬が発生", "売れました",
]
# 「初」を含む＝初収益の可能性がより高いキーワード
FIRST_REVENUE_MARKERS = ["初収益", "初成約", "初めて", "はじめて", "初報酬", "初案件", "0→1", "0→1", "ゼロイチ", "人生初"]
# 文脈での加点（本人の報告らしさ）
CONTEXT_POSITIVE = ["しました", "されました", "いただきました", "発生", "ついに", "やっと", "嬉しい", "うれしい", "感謝", "ありがとう"]
# 文脈での減点（ノウハウ解説・一般論の可能性）
CONTEXT_NEGATIVE = ["方法", "するには", "ためには", "コツ", "解説", "とは", "したいなら", "したい人", "ステップ"]

MONEY_RE = re.compile(r"(?:[0-9０-９,，.]+)\s*(?:万円|円|万)")
FOLLOWER_RE = re.compile(r"フォロワー[^0-9０-９]{0,6}([0-9０-９,，.]+)\s*(?:人|名|万人)?")
NUMBER_ACHIEVE_RE = re.compile(r"([0-9０-９,，.]+)\s*(?:万円|円|人|名|件|部|DL|ダウンロード|PV|いいね)")
URL_RE = re.compile(r"https?://\S+")

PRODUCT_WORDS = ["note", "Brain", "教材", "講座", "コンサル", "商品", "サービス", "コンテンツ", "tips", "電子書籍", "Kindle", "セミナー", "スクール"]
LINE_WORDS = ["公式LINE", "LINE登録", "LINEで", "ライン登録", "LINE@", "LINEに"]
NOTE_WORDS = ["note", "ノート販売"]
MAILMAG_WORDS = ["メルマガ", "メールマガジン", "メール講座", "無料メール"]
FOLLOW_CTA_WORDS = ["フォロー", "フォロバ"]
CTA_PATTERNS = [
    ("フォロー", "フォロー訴求"),
    ("いいね", "いいね訴求"),
    ("リプ", "リプ訴求"),
    ("保存", "保存訴求"),
    ("ブックマーク", "保存訴求"),
    ("プロフ", "プロフィール誘導"),
    ("リンク", "リンク誘導"),
    ("登録", "登録誘導"),
    ("DM", "DM誘導"),
    ("受け取", "受け取り誘導"),
    ("チェック", "確認訴求"),
]

READER_RE = re.compile(r"([ぁ-んァ-ヶ一-龠a-zA-Z0-9ー]{1,12}(?:したい人|できない人|な人|の方|初心者|ママ|パパ|会社員|主婦|フリーランス|学生))")
PROBLEM_RE = re.compile(r"([ぁ-んァ-ヶ一-龠a-zA-Z0-9ー]{1,16}(?:できない|わからない|分からない|続かない|伸びない|売れない|稼げない|不安|悩み|悩んで))")
FUTURE_RE = re.compile(r"([ぁ-んァ-ヶ一-龠a-zA-Z0-9ー、]{1,20}(?:できるように|なれる|になれます|が手に入る|を実現|自由|叶う|稼げるように))")

EMOTION_WORDS = {
    "喜び": ["嬉しい", "うれしい", "楽しい", "幸せ", "最高", "ワクワク", "感動"],
    "感謝": ["ありがとう", "感謝"],
    "不安・悩み": ["不安", "悩み", "つらい", "しんどい", "怖い", "焦り"],
    "怒り・問題意識": ["許せない", "おかしい", "危険", "注意", "もったいない"],
    "決意": ["決めた", "頑張る", "がんばる", "挑戦", "宣言"],
}


def _find_keywords(text: str, keywords: list[tuple[str, float]]) -> tuple[float, list[str]]:
    score = 0.0
    hits = []
    for kw, weight in keywords:
        if kw and kw in text:
            score += weight
            hits.append(kw)
    return score, hits


def classify_post(text: str) -> dict:
    """投稿を分類し、主分類1つ + 副分類最大2つを返す。"""
    scores: dict[str, tuple[float, list[str]]] = {}
    for cat, kws in CATEGORY_KEYWORDS.items():
        s, hits = _find_keywords(text, kws)
        if s > 0:
            scores[cat] = (s, hits)

    if URL_RE.search(text):
        s, hits = scores.get("外部誘導", (0.0, []))
        scores["外部誘導"] = (s + 1.5, hits + ["URLあり"])

    if not scores:
        return {
            "category_primary": "その他",
            "category_secondary": [],
            "confidence": 0.3,
            "reason": "分類キーワードに該当なし",
        }

    ranked = sorted(scores.items(), key=lambda x: x[1][0], reverse=True)
    primary, (primary_score, primary_hits) = ranked[0]
    secondary = [c for c, _ in ranked[1:3]]
    # ルールベースの確信度は最大 0.9 に制限（AI分析との区別のため）
    confidence = round(min(0.9, 0.4 + primary_score * 0.08), 2)
    reason = f"キーワード一致: {', '.join(primary_hits[:5])}"
    return {
        "category_primary": primary,
        "category_secondary": secondary,
        "confidence": confidence,
        "reason": reason,
    }


def detect_revenue_candidate(text: str) -> dict:
    """初収益・成約報告の候補かどうかを文脈込みで判定する。"""
    hits = [kw for kw in REVENUE_KEYWORDS if kw in text]
    if not hits:
        return {"is_revenue_candidate": False, "revenue_confidence": 0.0,
                "revenue_reason": "", "is_deal_report": False}

    score = 0.35 + 0.1 * min(len(hits), 3)
    reasons = [f"キーワード: {', '.join(hits)}"]

    first_markers = [m for m in FIRST_REVENUE_MARKERS if m in text]
    if first_markers:
        score += 0.15
        reasons.append(f"『初』を示す表現: {', '.join(first_markers[:3])}")

    pos = [w for w in CONTEXT_POSITIVE if w in text]
    if pos:
        score += 0.1
        reasons.append("本人の報告らしい文脈")

    if MONEY_RE.search(text):
        score += 0.1
        reasons.append("金額の記載あり")

    neg = [w for w in CONTEXT_NEGATIVE if w in text]
    if neg:
        score -= 0.25
        reasons.append(f"ノウハウ解説の可能性（{', '.join(neg[:3])}）")

    score = max(0.0, min(1.0, score))
    is_candidate = score >= 0.4
    return {
        "is_revenue_candidate": is_candidate,
        "revenue_confidence": round(score, 2),
        "revenue_reason": " / ".join(reasons),
        "is_deal_report": is_candidate or ("成約" in text or "申し込み" in text),
    }


def extract_features(text: str) -> dict:
    """投稿から要素を抽出する（フック・CTA・誘導・数値など）。"""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    hook = (lines[0] if lines else text)[:40]

    # CTA
    tail = text[-100:]
    ctas = [label for kw, label in CTA_PATTERNS if kw in tail]
    cta = "、".join(dict.fromkeys(ctas))

    # 文章構成
    if len(lines) >= 4 and sum(1 for ln in lines if re.match(r"^[・\-①-⑩0-9１-９]", ln)) >= 3:
        structure = "箇条書き・リスト型"
    elif text.strip().endswith(("?", "？")):
        structure = "問いかけ型"
    elif lines and re.search(r"(結論|まず|一番大事)", lines[0]):
        structure = "結論先出し型"
    elif len(text) < 60:
        structure = "短文つぶやき型"
    else:
        structure = "長文説明型"

    # 感情
    emotion = ""
    for label, words in EMOTION_WORDS.items():
        if any(w in text for w in words):
            emotion = label
            break

    reader = READER_RE.search(text)
    problem = PROBLEM_RE.search(text)
    future = FUTURE_RE.search(text)

    money = MONEY_RE.findall(text)
    followers = FOLLOWER_RE.findall(text)
    achieves = NUMBER_ACHIEVE_RE.findall(text)

    has_line = any(w in text for w in LINE_WORDS)
    has_note = any(w in text for w in NOTE_WORDS)
    has_mailmag = any(w in text for w in MAILMAG_WORDS)
    has_product = any(w in text for w in PRODUCT_WORDS)

    return {
        "hook": hook,
        "theme": hook[:20],
        "assumed_reader": reader.group(1) if reader else "",
        "reader_problem": problem.group(1) if problem else "",
        "promised_future": future.group(1) if future else "",
        "emotion": emotion,
        "structure": structure,
        "cta": cta,
        "has_external_link": bool(URL_RE.search(text)),
        "has_product_mention": has_product,
        "has_line": has_line,
        "has_note": has_note,
        "has_mailmag": has_mailmag,
        "has_follow_cta": any(w in text for w in FOLLOW_CTA_WORDS),
        "achievement_numbers": ", ".join(achieves[:5]),
        "sales_numbers": ", ".join(money[:5]),
        "follower_numbers": ", ".join(followers[:3]),
    }


def _reproducibility(analysis: dict) -> str:
    """再現性の高低を推定する。ノウハウ・教育・共感は真似しやすく、
    実績・権威付けは発信者固有の要素が強い。"""
    cat = analysis.get("category_primary", "その他")
    if cat in ("ノウハウ", "教育", "共感", "問題提起", "交流", "フォロー訴求", "外部誘導"):
        return "高"
    if cat in ("実績", "権威付け", "ストーリー"):
        return "低"
    return "中"


def analyze_post(post_id: str, text: str) -> PostAnalysis:
    """1件の投稿の分類 + 要素抽出をまとめて行う。"""
    result: dict = {"post_id": post_id}
    result.update(classify_post(text))
    result.update(extract_features(text))
    result.update(detect_revenue_candidate(text))
    result["reproducibility"] = _reproducibility(result)
    return PostAnalysis(**result)


def analyze_posts_df(posts_df: pd.DataFrame) -> pd.DataFrame:
    """投稿 DataFrame 全体をルールベースで分析し、分析結果 DataFrame を返す。"""
    results = [
        analyze_post(str(row["post_id"]), str(row["text"])).model_dump()
        for _, row in posts_df.iterrows()
    ]
    return pd.DataFrame(results)
