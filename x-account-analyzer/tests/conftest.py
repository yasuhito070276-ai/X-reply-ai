"""pytest 共通設定とテスト用の架空データ。"""
import sys
from pathlib import Path

import pandas as pd
import pytest

# プロジェクトルートを import パスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import db as dbm


@pytest.fixture
def conn():
    """テスト用のインメモリ SQLite 接続。"""
    c = dbm.get_conn(":memory:")
    yield c
    c.close()


@pytest.fixture
def sample_posts_df() -> pd.DataFrame:
    """架空の投稿データ（実在アカウントとは無関係）。"""
    rows = [
        {"post_id": "1", "created_at": "2025-01-01T08:00:00+00:00",
         "text": "はじめまして。未経験からデザインを勉強中です。よろしくお願いします！",
         "impressions": 500, "likes": 5, "replies": 1, "reposts": 0,
         "bookmarks": 0, "quotes": 0, "url": None, "media_type": None, "followers_count": 30},
        {"post_id": "2", "created_at": "2025-01-10T12:00:00+00:00",
         "text": "デザイン初心者がやりがちな失敗5選\n・フォントを使いすぎる\n・色を増やしすぎる\n・余白を怖がる\n・参考を見ない\n・完成させない",
         "impressions": 2000, "likes": 40, "replies": 5, "reposts": 8,
         "bookmarks": 20, "quotes": 1, "url": None, "media_type": None, "followers_count": 60},
        {"post_id": "3", "created_at": "2025-02-01T20:00:00+00:00",
         "text": "勉強が続かなくて自己嫌悪になる…そんな自分を責めないでください。悩みは皆同じです。",
         "impressions": 3000, "likes": 80, "replies": 12, "reposts": 15,
         "bookmarks": 10, "quotes": 2, "url": None, "media_type": None, "followers_count": 150},
        {"post_id": "4", "created_at": "2025-03-01T19:00:00+00:00",
         "text": "公式LINEを開設しました。登録者限定でチェックリストを無料配布します。プロフィールのリンクからどうぞ。https://example.com/line",
         "impressions": 1500, "likes": 25, "replies": 3, "reposts": 4,
         "bookmarks": 5, "quotes": 0, "url": None, "media_type": None, "followers_count": 400},
        {"post_id": "5", "created_at": "2025-03-10T19:00:00+00:00",
         "text": "【お知らせ】学習ロードマップをnoteで販売開始しました。購入はこちらから。https://example.com/note",
         "impressions": 2500, "likes": 30, "replies": 4, "reposts": 6,
         "bookmarks": 15, "quotes": 1, "url": None, "media_type": None, "followers_count": 500},
        {"post_id": "6", "created_at": "2025-03-15T21:00:00+00:00",
         "text": "ご報告です。noteがついに1件売れました！人生初収益です。0→1をやっと達成できました。ありがとうございます。",
         "impressions": 5000, "likes": 150, "replies": 30, "reposts": 25,
         "bookmarks": 8, "quotes": 3, "url": None, "media_type": None, "followers_count": 600},
    ]
    df = pd.DataFrame(rows)
    return df
