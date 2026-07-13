"""アプリ全体で使うデータ型の定義（pydantic）。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# 投稿カテゴリー（主分類・副分類で共通）
CATEGORIES = [
    "共感", "ストーリー", "教育", "ノウハウ", "実績", "権威付け", "日常",
    "意見・主張", "問題提起", "交流", "販売", "商品告知", "外部誘導",
    "フォロー訴求", "その他",
]


class Post(BaseModel):
    """1件の投稿。CSV / X API のどちらから来てもこの形に揃える。"""

    post_id: str
    created_at: datetime
    text: str
    impressions: Optional[float] = None
    likes: Optional[float] = None
    replies: Optional[float] = None
    reposts: Optional[float] = None
    bookmarks: Optional[float] = None
    quotes: Optional[float] = None
    url: Optional[str] = None
    media_type: Optional[str] = None
    followers_count: Optional[float] = None

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("本文（text）が空です")
        return v


class PostAnalysis(BaseModel):
    """1件の投稿の分析結果。"""

    post_id: str
    category_primary: str = "その他"
    category_secondary: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""

    hook: str = ""                    # 冒頭のフック
    theme: str = ""                   # 投稿テーマ
    assumed_reader: str = ""          # 想定読者
    reader_problem: str = ""          # 読者の悩み
    promised_future: str = ""         # 提示している未来
    emotion: str = ""                 # 感情
    structure: str = ""               # 文章構成
    cta: str = ""                     # CTA

    has_external_link: bool = False
    has_product_mention: bool = False
    has_line: bool = False
    has_note: bool = False
    has_mailmag: bool = False
    has_follow_cta: bool = False

    achievement_numbers: str = ""     # 実績数値
    sales_numbers: str = ""           # 売上数値
    follower_numbers: str = ""        # フォロワー数値

    is_revenue_candidate: bool = False    # 初収益報告の可能性
    revenue_confidence: float = 0.0
    revenue_reason: str = ""
    is_deal_report: bool = False          # 成約報告の可能性
    reproducibility: str = "中"           # 再現性の高低（高/中/低）

    @field_validator("confidence", "revenue_confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))
