// =====================================================================
// X AIリプ アシスタント バックエンドサーバー
//
// Chrome 拡張機能から投稿内容を受け取り、リプ3案を JSON で返します。
//   ・.env に OPENAI_API_KEY がある → OpenAI（AI）で生成
//   ・キーが無い                    → ルールベース生成（モック）で代用
//
// 起動方法:
//   cd server
//   npm install   （初回のみ。ライブラリをダウンロードする）
//   npm start     （サーバーが起動する。止めるときは Ctrl+C）
// =====================================================================

// .env ファイル（APIキーなどの秘密の設定）を環境変数として読み込む。
// 必ずファイルの一番上で実行する（他の処理より先にキーを用意するため）。
require("dotenv").config();

const express = require("express");
const cors = require("cors");

// リプ生成ロジック2種類（どちらも同じ server フォルダ内にある）
const { generateReplies } = require("./reply-generator.js");        // ルールベース
const { generateRepliesWithAI } = require("./ai-generator.js");     // OpenAI

// APIキーが設定されているかどうかで、使う生成方法を決める
const useAI = Boolean(process.env.OPENAI_API_KEY);

const app = express();

// サーバーが待ち受けるポート番号（住所の「部屋番号」のようなもの）
// http://localhost:3000 でアクセスできるようになる
const PORT = 3000;

// ---- ミドルウェア（すべてのリクエストに共通の前処理） ----------------

// CORS を許可する。
// Chrome 拡張は x.com という「別の場所」からこのサーバーを呼ぶため、
// ブラウザのセキュリティ制限を越える許可証が必要になる。
app.use(cors());

// リクエストの本文（JSON）を自動で読み取れるようにする
app.use(express.json());

// ---- 動作確認用: ブラウザで http://localhost:3000 を開くと表示される ----

app.get("/", (req, res) => {
  res.send(
    useAI
      ? "X AIリプ アシスタントのサーバーは動いています（OpenAI 接続モード）"
      : "X AIリプ アシスタントのサーバーは動いています（ルールベースのモックモード）"
  );
});

// ---- 本命の API: 投稿内容を受け取り、リプ3案を返す --------------------
//
// 受け取る JSON:  { "author": "投稿者名", "text": "投稿本文" }
// 返す JSON:      { "viewpoint": "採用した視点",
//                   "replies": [ { "type": "本命", "text": "..." } ×3 ] }

app.post("/api/replies", async (req, res) => {
  const { author, text } = req.body || {};

  // 入力チェック: 本文がない・文字列でないリクエストはエラーを返す
  if (typeof text !== "string" || text.trim() === "") {
    return res.status(400).json({
      error: "投稿本文（text）が空です。",
    });
  }

  try {
    let result;
    if (useAI) {
      // OpenAI で生成
      result = await generateRepliesWithAI({ author: author || "", text });
    } else {
      // APIキー未設定 → ルールベース生成で代用し、同じ形式に変換して返す
      const ruleBased = generateReplies({ author: author || "", text });
      result = {
        viewpoint: ruleBased.angleName,
        replies: ruleBased.replies.map((r) => ({ type: r.label, text: r.text })),
      };
    }

    // 動作確認用ログ（サーバーを起動したターミナルに表示される）
    console.log(
      `[サーバー] リプ生成(${useAI ? "AI" : "ルールベース"}): ` +
      `"${text.slice(0, 30)}..." → ${result.viewpoint}`
    );

    res.json(result);
  } catch (err) {
    // OpenAI との通信失敗など（キーの間違い・残高不足・通信断 等）
    console.error("[サーバー] 生成に失敗:", err.message);
    res.status(502).json({
      error: `リプの生成に失敗しました: ${err.message}`,
    });
  }
});

// ---- サーバー起動 ----------------------------------------------------

app.listen(PORT, () => {
  console.log(`サーバーが起動しました: http://localhost:${PORT}`);
  console.log(
    useAI
      ? `生成モード: OpenAI（モデル: ${process.env.OPENAI_MODEL || "gpt-5.5"}）`
      : "生成モード: ルールベース（.env に OPENAI_API_KEY を設定すると AI 生成に切り替わります）"
  );
  console.log("止めるときは Ctrl+C を押してください");
});
