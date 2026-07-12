// =====================================================================
// 設定の共通処理
//
// 設定は chrome.storage.local（Chrome内の保存領域）に保存され、
// 設定画面（options.html）で編集できます。
// このファイルは content.js と options.js の両方から使われます。
// =====================================================================

// ---- プロンプトの初期文面 --------------------------------------------
// {author} と {text} の部分に、投稿者名と投稿本文が自動で差し込まれます。
const DEFAULT_PROMPT_TEMPLATE = `あなたはX（旧Twitter）の交流リプライを作るアシスタントです。
最後に示す投稿への返信を3案作ってください。

## 禁止事項
- 投稿本文の要約はしない
- 「参考になります」「勉強になります」「共感しました」は使わない

## 視点の優先順位（最初に当てはまるものを1つ選び、3案すべてに適用）
1. 投稿で不足している具体例
2. 初心者が知りたいこと
3. 実践時の注意点
4. 判断基準
5. 例外ケース

## 3案の形式
- 本命: 丁寧に一歩踏み込む質問。投稿者が答えたくなるもの
- 親しみ: カジュアルで温かい文体。絵文字を1つ入れる
- 知見: 自分の見解や経験を一言添えたうえでの深掘り

## 条件
- それぞれ140文字以内の自然な日本語
- 投稿の具体的な内容（キーワード）に触れて、定型文にしない
- 「本命」「親しみ」「知見」のラベルを付けて出力する

---
投稿者: {author}
投稿本文:
{text}`;

// ---- 設定の既定値 ----------------------------------------------------
const DEFAULT_SETTINGS = {
  // X交流リプ専用チャットのURL（例: https://chatgpt.com/c/xxxxxxxx）
  chatUrl: "",

  // リプ生成プロンプトの文面
  promptTemplate: DEFAULT_PROMPT_TEMPLATE,

  // ChatGPTを開いた後に表示する案内文
  guideMessage: "プロンプトをコピーしました。ChatGPTに貼り付けて送信してください",
};

// 保存されている設定を読み込む（未設定の項目は既定値になる）
function loadSettings() {
  return new Promise((resolve) => {
    chrome.storage.local.get(DEFAULT_SETTINGS, (items) => resolve(items));
  });
}

// プロンプト文面に投稿者名と本文を差し込む
function buildPrompt(template, info) {
  return template
    .replaceAll("{author}", info.author || "（不明）")
    .replaceAll("{text}", info.text || "");
}
