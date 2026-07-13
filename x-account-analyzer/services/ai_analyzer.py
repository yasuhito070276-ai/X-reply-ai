"""AI 分析モジュール（Anthropic / OpenAI / 未使用 の3択）。

重要ルール:
- 全投稿を一度に AI へ渡さない（小さなバッチに分割する）
- 分析結果は SQLite にキャッシュし、同じ投稿を二度分析しない
- プロンプトとモデル名を保存して再現できるようにする
- API キーがなくても、ルールベース分析だけでアプリは動く
- 「事実 / 仮説 / 不明」を分けて出力させる
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import httpx
import pandas as pd

from database import db as dbm

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

BATCH_SIZE = 20                 # 1回のAPI呼び出しで分類する投稿数
AVG_TOKENS_PER_POST = 220       # 概算（日本語投稿 + 出力JSON）
PROMPT_OVERHEAD_TOKENS = 900    # システムプロンプト等の概算


class AIError(Exception):
    """ユーザー向けの AI エラー。APIキーなどの秘密情報は含めない。"""


def available_providers() -> list[str]:
    """利用可能な AI プロバイダーの一覧。「AIなし」は常に選択可能。"""
    providers = ["AIを使用しない（ルールベース）"]
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        providers.append("Anthropic API")
    if os.environ.get("OPENAI_API_KEY", "").strip():
        providers.append("OpenAI API")
    return providers


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")


def estimate_cost(n_posts: int) -> dict:
    """AI 分析前に表示するコスト見積もり。"""
    n_batches = -(-n_posts // BATCH_SIZE)  # 切り上げ
    est_tokens = n_posts * AVG_TOKENS_PER_POST + n_batches * PROMPT_OVERHEAD_TOKENS
    return {
        "対象投稿数": n_posts,
        "推定バッチ数": n_batches,
        "推定トークン量": est_tokens,
        "推定API呼び出し回数": n_batches + 4,  # 分類 + 要約数回
    }


# ---------------------------------------------------------------
# プロバイダー呼び出し（httpx 直叩き。キーはログに出さない）
# ---------------------------------------------------------------

def _call_anthropic(prompt: str, model: str, max_tokens: int = 4000) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise AIError("ANTHROPIC_API_KEY が設定されていません。.env を確認してください。")
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120.0,
    )
    if resp.status_code == 401:
        raise AIError("Anthropic APIキーが無効です（401）。.env の ANTHROPIC_API_KEY を確認してください。")
    if resp.status_code == 429:
        raise AIError("Anthropic APIのレート制限に達しました（429）。少し待ってから「途中から再開」してください。")
    if resp.status_code != 200:
        raise AIError(f"Anthropic APIエラー（HTTP {resp.status_code}）。時間をおいて再実行してください。")
    data = resp.json()
    return "".join(block.get("text", "") for block in data.get("content", []))


def _call_openai(prompt: str, model: str, max_tokens: int = 4000) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise AIError("OPENAI_API_KEY が設定されていません。.env を確認してください。")
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
        json={
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120.0,
    )
    if resp.status_code == 401:
        raise AIError("OpenAI APIキーが無効です（401）。.env の OPENAI_API_KEY を確認してください。")
    if resp.status_code == 429:
        raise AIError("OpenAI APIのレート制限または残高不足です（429）。確認後に「途中から再開」してください。")
    if resp.status_code != 200:
        raise AIError(f"OpenAI APIエラー（HTTP {resp.status_code}）。時間をおいて再実行してください。")
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def resolve_model(provider: str) -> str:
    if provider == "Anthropic API":
        return os.environ.get("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
    return os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)


def call_ai(conn, provider: str, prompt: str, max_tokens: int = 4000) -> str:
    """キャッシュ付きの AI 呼び出し。同じプロンプトは再送しない。"""
    model = resolve_model(provider)
    key = dbm.cache_key(provider, model, prompt)
    cached = dbm.ai_cache_get(conn, key)
    if cached is not None:
        return cached
    if provider == "Anthropic API":
        response = _call_anthropic(prompt, model, max_tokens)
    elif provider == "OpenAI API":
        response = _call_openai(prompt, model, max_tokens)
    else:
        raise AIError("AIプロバイダーが選択されていません。")
    dbm.ai_cache_set(conn, key, provider, model, prompt, response)
    return response


def _extract_json(text: str):
    """AI の出力から JSON 部分を取り出す。"""
    match = re.search(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", text, re.DOTALL)
    raw = match.group(1) if match else text
    start = min([i for i in (raw.find("["), raw.find("{")) if i >= 0], default=-1)
    if start < 0:
        raise AIError("AIの出力からJSONを読み取れませんでした。再実行してください。")
    return json.loads(raw[start:])


# ---------------------------------------------------------------
# 多段階分析
# ---------------------------------------------------------------

def classify_posts_ai(
    conn,
    provider: str,
    posts_df: pd.DataFrame,
    dataset_id: int,
    limit: int | None = None,
    progress_callback=None,
) -> tuple[int, int, list[str]]:
    """段階1: 投稿をバッチに分けて AI 分類し、SQLite に保存する。

    limit を指定するとテスト分析モード（先頭 limit 件のみ）。
    戻り値: (分析済み件数, スキップ件数, エラーメッセージのリスト)
    途中で失敗しても、成功済みバッチは保存されるため再開できる。
    """
    template = load_prompt("classify_batch")
    existing = dbm.fetch_analysis_df(conn, dataset_id)
    done_ids: set[str] = set()
    if not existing.empty and "engine" in existing.columns:
        done_ids = set(existing[existing["engine"] == "ai"]["post_id"].astype(str))

    target = posts_df if limit is None else posts_df.head(limit)
    todo = target[~target["post_id"].astype(str).isin(done_ids)]
    skipped = len(target) - len(todo)

    analyzed = 0
    errors: list[str] = []
    model = resolve_model(provider)
    batches = [todo.iloc[i:i + BATCH_SIZE] for i in range(0, len(todo), BATCH_SIZE)]

    for bi, batch in enumerate(batches):
        items = [
            {"post_id": str(r["post_id"]), "text": str(r["text"])[:600]}
            for _, r in batch.iterrows()
        ]
        prompt = template.replace("{{POSTS_JSON}}", json.dumps(items, ensure_ascii=False))
        try:
            raw = call_ai(conn, provider, prompt)
            results = _extract_json(raw)
            valid = []
            batch_ids = {it["post_id"] for it in items}
            for r in results:
                if isinstance(r, dict) and str(r.get("post_id")) in batch_ids:
                    r["post_id"] = str(r["post_id"])
                    valid.append(r)
            dbm.save_analysis(conn, dataset_id, valid, engine="ai", model=model)
            analyzed += len(valid)
        except (AIError, json.JSONDecodeError) as e:
            errors.append(f"バッチ {bi + 1}/{len(batches)}: {e}")
            if isinstance(e, AIError) and ("429" in str(e) or "401" in str(e)):
                break  # レート制限・認証エラーは以降も失敗するため中断
        if progress_callback:
            progress_callback(bi + 1, len(batches))

    return analyzed, skipped, errors


def summarize_periods(conn, provider: str, merged: pd.DataFrame, freq: str = "W") -> str:
    """段階2-3: 週別/月別に要約する。"""
    template = load_prompt("summarize_period")
    d = merged.copy()
    d["created_at"] = pd.to_datetime(d["created_at"], utc=True)
    d["period"] = d["created_at"].dt.to_period(freq).astype(str)

    period_lines = []
    for period, sub in d.groupby("period"):
        cats = sub["category_primary"].value_counts().head(3).to_dict()
        sample = " / ".join(sub["text"].astype(str).str.slice(0, 40).head(3))
        period_lines.append(
            f"- {period}: 投稿{len(sub)}件, 主カテゴリ{cats}, 例: {sample}"
        )
    prompt = template.replace("{{PERIOD_DATA}}", "\n".join(period_lines[:80]))
    return call_ai(conn, provider, prompt)


def analyze_zero_to_one(conn, provider: str, merged: pd.DataFrame, revenue_date, comparison: dict) -> str:
    """段階5: 初収益前後の詳細分析。"""
    template = load_prompt("zero_to_one")
    d = merged.copy()
    d["created_at"] = pd.to_datetime(d["created_at"], utc=True)
    pivot = pd.Timestamp(revenue_date)
    if pivot.tzinfo is None:
        pivot = pivot.tz_localize("UTC")
    recent = d[(d["created_at"] >= pivot - pd.Timedelta(days=30)) & (d["created_at"] < pivot)]

    lines = [
        f"- {r['created_at'].strftime('%m/%d')} [{r.get('category_primary', '?')}] {str(r['text'])[:80]}"
        for _, r in recent.head(60).iterrows()
    ]
    stats = {
        "直前30日": comparison.get("recent"),
        "その前30日": comparison.get("prior"),
    }
    prompt = (
        template
        .replace("{{REVENUE_DATE}}", str(pivot.date()))
        .replace("{{STATS_JSON}}", json.dumps(stats, ensure_ascii=False))
        .replace("{{RECENT_POSTS}}", "\n".join(lines))
    )
    return call_ai(conn, provider, prompt)


def generate_report_sections(conn, provider: str, context: str) -> str:
    """段階6: 全体レポートの AI 生成（要約済みデータのみを渡す）。"""
    template = load_prompt("final_report")
    prompt = template.replace("{{CONTEXT}}", context[:24000])
    return call_ai(conn, provider, prompt, max_tokens=8000)
