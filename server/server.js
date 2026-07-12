// =====================================================================
// X AIリプ アシスタント バックエンドサーバー（モック版）
//
// Chrome 拡張機能から投稿内容を受け取り、リプ3案を JSON で返します。
// 現在はまだ OpenAI API には繋がず、拡張機能と同じルールベース生成
// （../extension/reply-generator.js）をサーバー側で動かして返します。
//
// 起動方法:
//   cd server
//   npm install   （初回のみ。ライブラリをダウンロードする）
//   npm start     （サーバーが起動する。止めるときは Ctrl+C）
// =====================================================================

const express = require("express");
const cors = require("cors");

// 拡張機能と同じリプ生成ロジックを読み込む（書き直さずに使い回す）
const { generateReplies } = require("../extension/reply-generator.js");

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
  res.send("X AIリプ アシスタントのサーバーは動いています（モック版）");
});

// ---- 本命の API: 投稿内容を受け取り、リプ3案を返す --------------------
//
// 受け取る JSON:  { "author": "投稿者名", "text": "投稿本文" }
// 返す JSON:      { "angleName": "採用した視点", "replies": [ {label, text} ×3 ] }

app.post("/api/replies", (req, res) => {
  const { author, text } = req.body || {};

  // 入力チェック: 本文がない・文字列でないリクエストはエラーを返す
  if (typeof text !== "string" || text.trim() === "") {
    return res.status(400).json({
      error: "投稿本文（text）が空です。",
    });
  }

  // ルールベース生成でリプ3案を作る
  const result = generateReplies({ author: author || "", text });

  // 動作確認用ログ（サーバーを起動したターミナルに表示される）
  console.log(`[サーバー] リプ生成: "${text.slice(0, 30)}..." → ${result.angleName}`);

  res.json(result);
});

// ---- サーバー起動 ----------------------------------------------------

app.listen(PORT, () => {
  console.log(`サーバーが起動しました: http://localhost:${PORT}`);
  console.log("止めるときは Ctrl+C を押してください");
});
