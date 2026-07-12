// =====================================================================
// リプ生成ロジック（OpenAI API 版）
//
// OpenAI と通信するのはこのファイルだけです。
// APIキーは .env ファイルの OPENAI_API_KEY から読み込まれ、
// Chrome 拡張機能には一切渡りません。
//
// 使うモデルは .env の OPENAI_MODEL で変更できます（既定: gpt-5.5）。
// =====================================================================

const OpenAI = require("openai");

// ---- AI への指示文（プロンプト） -------------------------------------
// リプ生成のルール・優先順位・出力形式をここで全部指定する。
const SYSTEM_PROMPT = `あなたはX（旧Twitter）の交流リプライを作るアシスタントです。
投稿者名と投稿本文を受け取り、「読者が次に知りたいこと」を補足するリプライを3案作ります。

## 禁止事項
- 投稿本文の要約はしない
- 「参考になります」という表現は使わない
- 「勉強になります」という表現は使わない
- 「共感しました」という表現は使わない

## 視点の優先順位
投稿を分析し、次の優先順位で最初に当てはまる視点を1つ選んで3案すべてをその視点で書く:
1. 投稿で不足している具体例
2. 初心者が知りたいこと
3. 実践時の注意点
4. 判断基準
5. 例外ケース

## 3案のスタイル
- 本命: 丁寧に一歩踏み込む質問。投稿者が答えたくなるもの
- 親しみ: カジュアルで温かい文体。絵文字を1つ入れる
- 知見: 自分の見解や経験を一言添えたうえでの深掘り

## 文章の条件
- 自然な日本語で、それぞれ140文字以内
- 投稿の具体的な内容（キーワード）に触れて、誰にでも送れる定型文にしない

## 出力形式
次のJSONだけを出力する:
{"viewpoint":"選んだ視点の名前","replies":[{"type":"本命","text":"..."},{"type":"親しみ","text":"..."},{"type":"知見","text":"..."}]}`;

// 禁止ワード（AIの応答に紛れ込んでいないかの最終チェック用）
const BANNED_PHRASES = ["参考になります", "勉強になります", "共感しました"];

// ---- メインの関数（server.js から呼ばれる） ---------------------------

async function generateRepliesWithAI({ author, text }) {
  // APIキー（OPENAI_API_KEY）は OpenAI ライブラリが環境変数から自動で読む
  const client = new OpenAI();

  const completion = await client.chat.completions.create({
    model: process.env.OPENAI_MODEL || "gpt-5.5",
    temperature: 0.4, // 低め = 毎回の出力のブレを抑える
    response_format: { type: "json_object" }, // 必ずJSONで返させる設定
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      {
        role: "user",
        content: `投稿者名: ${author || "（不明）"}\n投稿本文:\n${text}`,
      },
    ],
  });

  // AIの応答（JSON文字列）を取り出して解析する
  const raw = completion.choices[0]?.message?.content ?? "";
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error("AIの応答をJSONとして読み取れませんでした");
  }

  // 形式チェック: 期待した形になっているかを必ず確認してから返す
  if (typeof parsed.viewpoint !== "string" || !Array.isArray(parsed.replies) || parsed.replies.length !== 3) {
    throw new Error("AIの応答が期待した形式（viewpoint + replies 3件）ではありませんでした");
  }
  for (const reply of parsed.replies) {
    if (typeof reply.type !== "string" || typeof reply.text !== "string" || reply.text.trim() === "") {
      throw new Error("AIの応答に不正なリプ案が含まれていました");
    }
    // 禁止ワードの最終チェック（見つけたらログに残す）
    for (const banned of BANNED_PHRASES) {
      if (reply.text.includes(banned)) {
        console.warn(`[AI] 禁止ワード「${banned}」を検出:`, reply.text);
      }
    }
  }

  // 余計なプロパティを取り除いて、決めた形だけを返す
  return {
    viewpoint: parsed.viewpoint,
    replies: parsed.replies.map((r) => ({ type: r.type, text: r.text })),
  };
}

module.exports = { generateRepliesWithAI };
