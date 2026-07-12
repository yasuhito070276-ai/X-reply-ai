// =====================================================================
// 設定の共通処理
//
// 設定は chrome.storage.local（Chrome内の保存領域）に保存され、
// 設定画面（options.html）で編集できます。
// このファイルは content.js と options.js の両方から使われます。
// =====================================================================

// ---- プロンプトの初期文面 --------------------------------------------
// リプ生成の固定ルールは AI サービス側（Claude のプロジェクト、または
// ChatGPT のカスタムGPT）に設定してあるため、拡張機能からは
// 投稿の情報と出力形式だけを送ります。
// {{author}} と {{postText}} の部分に、投稿者名と投稿本文が差し込まれます。
const DEFAULT_PROMPT_TEMPLATE = `【最優先指示】
このプロジェクト／GPTに設定されたルールを最優先で適用してください。
過去の会話ではなく、今回の投稿内容に合わせて3案を作成してください。

【投稿者】
{{author}}

【投稿本文】
{{postText}}

【出力】
本命：
親しみ：
知見：

余計な説明は不要です。`;

// v0.9 の初期文面（ChatGPT専用の表現だった版。自動移行用）
const LEGACY_PROMPT_TEMPLATE_V09 = `【最優先指示】
このGPTに設定されたルールを最優先で適用してください。
過去の会話ではなく、今回の投稿内容に合わせて3案を作成してください。

【投稿者】
{{author}}

【投稿本文】
{{postText}}

【出力】
本命：
親しみ：
知見：

余計な説明は不要です。`;

// ---- 旧バージョンの初期文面（自動移行用） ----------------------------
// 保存済みの設定がこれらと完全に同じ場合だけ、新しい初期文面へ
// 自動で置き換えます（自分で編集した文面は触りません）。

// v0.8 の初期文面（プロジェクトのルール参照版）
const LEGACY_PROMPT_TEMPLATE_V08 = `このプロジェクトのルールを適用してください。

投稿者：
{{author}}

投稿本文：
{{postText}}`;

// v0.7 の初期文面（固定ルール入りの長文版）
const LEGACY_PROMPT_TEMPLATE_V07 = `あなたはX（旧Twitter）の交流リプライを作るアシスタントです。
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

// v0.8 までの案内文の初期値（自動移行用）
const LEGACY_GUIDE_MESSAGE = "プロンプトをコピーしました。ChatGPTに貼り付けて送信してください";

// ---- 設定の既定値 ----------------------------------------------------
const DEFAULT_SETTINGS = {
  // 使うAIサービス（"claude" または "chatgpt"）
  aiService: "claude",

  // Xリプ専用GPTチャットのURL（ChatGPT用。例: https://chatgpt.com/g/g-xxxx）
  chatUrl: "",

  // ClaudeプロジェクトのURL（Claude用。例: https://claude.ai/project/xxxx）
  claudeUrl: "",

  // リプ生成プロンプトの文面
  promptTemplate: DEFAULT_PROMPT_TEMPLATE,

  // コピー後に画面へ大きく表示する案内文
  guideMessage: "コピーしました。⌘＋Vで貼り付け、Enterで送信してください",
};

// 保存されている設定を読み込む（未設定の項目は既定値になる）
function loadSettings() {
  return new Promise((resolve) => {
    chrome.storage.local.get(DEFAULT_SETTINGS, (items) => {
      // 移行処理: 旧バージョンの「初期値のまま」の設定が保存されていたら、
      // 新しい初期値に自動で置き換える（編集済みの文面は触らない）
      const updates = {};

      if (
        items.promptTemplate === LEGACY_PROMPT_TEMPLATE_V09 ||
        items.promptTemplate === LEGACY_PROMPT_TEMPLATE_V08 ||
        items.promptTemplate === LEGACY_PROMPT_TEMPLATE_V07
      ) {
        items.promptTemplate = DEFAULT_PROMPT_TEMPLATE;
        updates.promptTemplate = DEFAULT_PROMPT_TEMPLATE;
      }

      if (items.guideMessage === LEGACY_GUIDE_MESSAGE) {
        items.guideMessage = DEFAULT_SETTINGS.guideMessage;
        updates.guideMessage = DEFAULT_SETTINGS.guideMessage;
      }

      if (Object.keys(updates).length > 0) {
        chrome.storage.local.set(updates);
      }

      resolve(items);
    });
  });
}

// プロンプト文面に投稿者名と本文を差し込む
function buildPrompt(template, info) {
  const author = info.author || "（不明）";
  const text = info.text || "";
  return (
    template
      // 新形式の目印（{{...}} を先に置き換えること。順番が大事）
      .replaceAll("{{author}}", author)
      .replaceAll("{{postText}}", text)
      // 旧形式の目印にも念のため対応
      .replaceAll("{author}", author)
      .replaceAll("{text}", text)
  );
}
