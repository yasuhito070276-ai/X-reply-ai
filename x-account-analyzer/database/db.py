"""SQLite データベース層。

投稿データ・分析結果・設定・AIキャッシュをローカルの SQLite に保存する。
外部にデータを送信することはない。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "analyzer.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'csv',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    post_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    text TEXT NOT NULL,
    impressions REAL,
    likes REAL,
    replies REAL,
    reposts REAL,
    bookmarks REAL,
    quotes REAL,
    url TEXT,
    media_type TEXT,
    followers_count REAL,
    UNIQUE (dataset_id, post_id)
);

CREATE TABLE IF NOT EXISTS post_analysis (
    dataset_id INTEGER NOT NULL,
    post_id TEXT NOT NULL,
    engine TEXT NOT NULL DEFAULT 'rule',
    model TEXT,
    analyzed_at TEXT,
    payload TEXT NOT NULL,
    PRIMARY KEY (dataset_id, post_id)
);

CREATE TABLE IF NOT EXISTS dataset_settings (
    dataset_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    PRIMARY KEY (dataset_id, key)
);

CREATE TABLE IF NOT EXISTS ai_cache (
    cache_key TEXT PRIMARY KEY,
    provider TEXT,
    model TEXT,
    prompt TEXT,
    response TEXT,
    created_at TEXT
);
"""


def get_conn(db_path: str | Path | None = None) -> sqlite3.Connection:
    """DB接続を返す。初回はテーブルも作成する。"""
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    # Streamlit は複数スレッドから接続を使うため check_same_thread=False にする
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- データセット ----------

def create_dataset(conn: sqlite3.Connection, name: str, source: str = "csv") -> int:
    cur = conn.execute(
        "INSERT INTO datasets (name, source, created_at) VALUES (?, ?, ?)",
        (name, source, _now()),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_datasets(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT d.id, d.name, d.source, d.created_at,
               (SELECT COUNT(*) FROM posts p WHERE p.dataset_id = d.id) AS post_count
        FROM datasets d ORDER BY d.id DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def delete_dataset(conn: sqlite3.Connection, dataset_id: int) -> None:
    conn.execute("DELETE FROM posts WHERE dataset_id = ?", (dataset_id,))
    conn.execute("DELETE FROM post_analysis WHERE dataset_id = ?", (dataset_id,))
    conn.execute("DELETE FROM dataset_settings WHERE dataset_id = ?", (dataset_id,))
    conn.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
    conn.commit()


# ---------- 投稿 ----------

POST_COLUMNS = [
    "post_id", "created_at", "text", "impressions", "likes", "replies",
    "reposts", "bookmarks", "quotes", "url", "media_type", "followers_count",
]


def insert_posts(conn: sqlite3.Connection, dataset_id: int, df: pd.DataFrame) -> tuple[int, int]:
    """投稿を保存する。重複（同じ post_id）はスキップ。(追加数, スキップ数) を返す。"""
    inserted = 0
    skipped = 0
    for _, row in df.iterrows():
        values = [dataset_id] + [
            (None if pd.isna(row.get(c)) else row.get(c)) for c in POST_COLUMNS
        ]
        try:
            conn.execute(
                f"INSERT INTO posts (dataset_id, {', '.join(POST_COLUMNS)}) "
                f"VALUES ({', '.join(['?'] * (len(POST_COLUMNS) + 1))})",
                values,
            )
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1
    conn.commit()
    return inserted, skipped


def fetch_posts_df(conn: sqlite3.Connection, dataset_id: int) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT * FROM posts WHERE dataset_id = ? ORDER BY created_at",
        conn,
        params=(dataset_id,),
    )
    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
    return df


# ---------- 分析結果 ----------

def save_analysis(
    conn: sqlite3.Connection,
    dataset_id: int,
    results: list[dict],
    engine: str = "rule",
    model: str | None = None,
) -> None:
    """分析結果を保存する。results の各要素は post_id キーを含む辞書。"""
    now = _now()
    for r in results:
        payload = json.dumps({k: v for k, v in r.items() if k != "post_id"}, ensure_ascii=False)
        conn.execute(
            """
            INSERT INTO post_analysis (dataset_id, post_id, engine, model, analyzed_at, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (dataset_id, post_id)
            DO UPDATE SET engine=excluded.engine, model=excluded.model,
                          analyzed_at=excluded.analyzed_at, payload=excluded.payload
            """,
            (dataset_id, r["post_id"], engine, model, now, payload),
        )
    conn.commit()


def fetch_analysis_df(conn: sqlite3.Connection, dataset_id: int) -> pd.DataFrame:
    rows = conn.execute(
        "SELECT post_id, engine, model, analyzed_at, payload FROM post_analysis WHERE dataset_id = ?",
        (dataset_id,),
    ).fetchall()
    records = []
    for r in rows:
        rec = json.loads(r["payload"])
        rec["post_id"] = r["post_id"]
        rec["engine"] = r["engine"]
        rec["model"] = r["model"]
        records.append(rec)
    return pd.DataFrame(records)


# ---------- 設定（初収益日など） ----------

def set_setting(conn: sqlite3.Connection, dataset_id: int, key: str, value: str | None) -> None:
    conn.execute(
        """
        INSERT INTO dataset_settings (dataset_id, key, value) VALUES (?, ?, ?)
        ON CONFLICT (dataset_id, key) DO UPDATE SET value = excluded.value
        """,
        (dataset_id, key, value),
    )
    conn.commit()


def get_setting(conn: sqlite3.Connection, dataset_id: int, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM dataset_settings WHERE dataset_id = ? AND key = ?",
        (dataset_id, key),
    ).fetchone()
    return row["value"] if row else None


# ---------- AI キャッシュ ----------

def cache_key(provider: str, model: str, prompt: str) -> str:
    return hashlib.sha256(f"{provider}|{model}|{prompt}".encode("utf-8")).hexdigest()


def ai_cache_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT response FROM ai_cache WHERE cache_key = ?", (key,)).fetchone()
    return row["response"] if row else None


def ai_cache_set(
    conn: sqlite3.Connection, key: str, provider: str, model: str, prompt: str, response: str
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO ai_cache (cache_key, provider, model, prompt, response, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (key, provider, model, prompt, response, _now()),
    )
    conn.commit()
