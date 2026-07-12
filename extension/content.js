// =====================================================================
// X AIリプ アシスタント（ルールベース版）
// X のページに読み込まれて、以下の3つを行うスクリプトです。
//   1. 各投稿に「AIリプ」ボタンを追加する
//   2. ボタンが押されたら、その投稿の本文と投稿者名を取得する
//   3. リプ3案（本命・親しみ・知見）をパネルに表示する
//
// リプの文章を作る処理は reply-generator.js（先に読み込まれる）の
// generateReplies() が担当します。このファイルは「画面まわり」専門です。
// AI・バックエンドへの通信はまだ行いません。
// =====================================================================

// ---- 投稿を見つけるための「目印」（セレクタ） -----------------------
// X の画面は data-testid という属性を目印にできます。
// X 側の仕様変更で変わることがあるため、1か所にまとめておきます。
const SELECTORS = {
  tweet: 'article[data-testid="tweet"]',        // 投稿1件の外枠
  tweetText: 'div[data-testid="tweetText"]',    // 投稿の本文
  userName: 'div[data-testid="User-Name"]',     // 投稿者名の表示部分
  actionBar: 'div[role="group"]',               // 返信・リポスト等のボタン列
};

// =====================================================================
// 1. 各投稿に「AIリプ」ボタンを追加する
// =====================================================================

function addButtons() {
  // ページ内のすべての投稿を探してループする
  const tweets = document.querySelectorAll(SELECTORS.tweet);

  for (const tweet of tweets) {
    // すでにボタンを付けた投稿はスキップ（二重追加の防止）
    if (tweet.querySelector(".ai-reply-button")) continue;

    // 返信・リポストなどが並ぶボタン列を探し、その隣に追加する
    const actionBar = tweet.querySelector(SELECTORS.actionBar);
    if (!actionBar) continue;

    const button = document.createElement("button");
    button.className = "ai-reply-button";
    button.textContent = "AIリプ";

    button.addEventListener("click", (event) => {
      // クリックが投稿本体に伝わって詳細ページへ遷移するのを防ぐ
      event.stopPropagation();
      event.preventDefault();
      onAiReplyClick(tweet);
    });

    actionBar.appendChild(button);
  }
}

// =====================================================================
// 2. 投稿の本文と投稿者名を取得する
// =====================================================================

function getTweetInfo(tweet) {
  // 投稿本文（画像だけの投稿など、本文がない場合もある）
  const textElement = tweet.querySelector(SELECTORS.tweetText);
  const text = textElement ? textElement.innerText.trim() : "";

  // 投稿者名の部分は「表示名 / @ユーザー名 / 日付」が改行で並んでいるので、
  // 1行目（表示名）だけを取り出す
  const userElement = tweet.querySelector(SELECTORS.userName);
  const author = userElement ? userElement.innerText.split("\n")[0].trim() : "";

  return { author, text };
}

function onAiReplyClick(tweet) {
  const info = getTweetInfo(tweet);

  // 動作確認用：取得した内容を開発者ツールのコンソールにも出す
  console.log("[AIリプ] 取得した投稿:", info);

  // reply-generator.js のルールベース生成でリプ3案を作る
  const result = generateReplies(info);

  showPanel(info, result);
}

// =====================================================================
// 3. リプ3案をパネルに表示する
// =====================================================================

function showPanel(info, result) {
  // すでにパネルが開いていたら一度閉じる
  closePanel();

  // 画面全体を覆う半透明の背景（クリックで閉じる）
  const overlay = document.createElement("div");
  overlay.className = "ai-reply-overlay";
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) closePanel();
  });

  // パネル本体
  const panel = document.createElement("div");
  panel.className = "ai-reply-panel";

  // --- ヘッダー ---
  const title = document.createElement("div");
  title.className = "ai-reply-panel-title";
  title.textContent = "AIリプ候補";
  panel.appendChild(title);

  // --- 取得した投稿の確認表示 ---
  // 本文・投稿者名が正しく取れているかをここで確認できます
  const source = document.createElement("div");
  source.className = "ai-reply-panel-source";
  source.textContent =
    `${info.author || "（投稿者名を取得できませんでした）"}: ` +
    `${info.text || "（本文を取得できませんでした）"}`;
  panel.appendChild(source);

  // --- 採用した視点の表示 ---
  // どのルール（優先順位）が選ばれたかの確認用
  const angle = document.createElement("div");
  angle.className = "ai-reply-panel-angle";
  angle.textContent = `視点: ${result.angleName}`;
  panel.appendChild(angle);

  // --- リプ候補の一覧（本命・親しみ・知見） ---
  for (const reply of result.replies) {
    const item = document.createElement("button");
    item.className = "ai-reply-panel-item";

    // 「本命」などのラベル（バッジ）
    const label = document.createElement("span");
    label.className = "ai-reply-panel-item-label";
    label.textContent = reply.label;
    item.appendChild(label);

    // リプの本文
    const body = document.createElement("span");
    body.textContent = reply.text;
    item.appendChild(body);

    item.addEventListener("click", () => {
      // 【仮の動作】クリップボードにコピーする。
      // 返信欄への自動入力は後のステップで実装します。
      navigator.clipboard.writeText(reply.text).then(() => {
        showToast("コピーしました！ 返信欄に貼り付けてください");
        closePanel();
      });
    });
    panel.appendChild(item);
  }

  // --- 注意書き ---
  const note = document.createElement("div");
  note.className = "ai-reply-panel-note";
  note.textContent = "※ 送信は必ずご自身で行ってください（自動送信はしません）";
  panel.appendChild(note);

  overlay.appendChild(panel);
  document.body.appendChild(overlay);
}

function closePanel() {
  const overlay = document.querySelector(".ai-reply-overlay");
  if (overlay) overlay.remove();
}

// 画面下に短時間だけ出る通知（トースト）
function showToast(message) {
  const toast = document.createElement("div");
  toast.className = "ai-reply-toast";
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

// =====================================================================
// 起動処理
// X はスクロールするたびに投稿を後から追加していく作りなので、
// 「ページの変化を監視して、そのたびにボタンを付け直す」仕組みが必要です。
// MutationObserver がその監視役です。
// =====================================================================

// 変化が起きるたびに毎回処理すると重いので、
// 300ミリ秒待ってまとめて1回だけ実行する（デバウンス）
let addButtonsTimer = null;

const observer = new MutationObserver(() => {
  clearTimeout(addButtonsTimer);
  addButtonsTimer = setTimeout(addButtons, 300);
});

observer.observe(document.body, { childList: true, subtree: true });

// 読み込み直後に表示されている投稿にもボタンを付ける
addButtons();

console.log("[AIリプ] 拡張機能が読み込まれました（ルールベース版）");
