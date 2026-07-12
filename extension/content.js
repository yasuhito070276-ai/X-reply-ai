// =====================================================================
// X AIリプ アシスタント（ChatGPT連携版）
// X のページに読み込まれて、以下を行うスクリプトです。
//   1. 各投稿に「AIリプ」ボタンを追加する
//   2. ボタンが押されたら、投稿本文と投稿者名を取得し、
//      専用プロンプト（prompt-template.js）を組み立ててパネルに表示する
//   3. 「ChatGPTで開く」で、プロンプトを持って新しいタブへ移動する
//   4. ChatGPT でコピーしたリプ案を、対象投稿の返信欄へ入力する
//
// 送信は必ず人間が行います。自動送信のコードはありません。
// API・サーバーは使いません。
// =====================================================================

// ---- 投稿を見つけるための「目印」（セレクタ） -----------------------
// X の画面は data-testid という属性を目印にできます。
// X 側の仕様変更で変わることがあるため、1か所にまとめておきます。
const SELECTORS = {
  tweet: 'article[data-testid="tweet"]',        // 投稿1件の外枠
  tweetText: 'div[data-testid="tweetText"]',    // 投稿の本文
  userName: 'div[data-testid="User-Name"]',     // 投稿者名の表示部分
  actionBar: 'div[role="group"]',               // 返信・リポスト等のボタン列
  replyButton: 'button[data-testid="reply"]',   // 各投稿の返信ボタン
  composer: '[data-testid="tweetTextarea_0"]',  // 返信の入力欄
};

// ChatGPT の場所。「?q=プロンプト」を付けると入力済みの状態で開く
const CHATGPT_URL = "https://chatgpt.com/";

// URL に載せるプロンプトの長さの上限（超えたらコピー方式に自動で切り替え）
const MAX_URL_LENGTH = 6000;

// 状態を覚えておく変数たち
let currentTweet = null; // 「AIリプ」ボタンを押した投稿
let pendingTweet = null; // 返信欄への入力を待っている投稿
let lastPrompt = "";     // 直前に作ったプロンプト（誤って貼り付けた時の検出用）

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
// 2. 投稿の情報を取得して、プロンプトを組み立てる
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

  // どの投稿へのリプか覚えておく（返信欄への入力時に使う）
  currentTweet = tweet;

  // 動作確認用：取得した内容を開発者ツールのコンソールにも出す
  console.log("[AIリプ] 取得した投稿:", info);

  // prompt-template.js のテンプレートでプロンプトを作る
  const prompt = buildPrompt(info);
  lastPrompt = prompt;

  showPanel(info, prompt);
}

// =====================================================================
// 3. プロンプトをパネルに表示して、ChatGPT へ渡す
// =====================================================================

function showPanel(info, prompt) {
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
  title.textContent = "AIリプ用プロンプト";
  panel.appendChild(title);

  // --- 取得した投稿の確認表示 ---
  const source = document.createElement("div");
  source.className = "ai-reply-panel-source";
  source.textContent =
    `${info.author || "（投稿者名を取得できませんでした）"}: ` +
    `${info.text || "（本文を取得できませんでした）"}`;
  panel.appendChild(source);

  // --- 作成されたプロンプトのプレビュー ---
  const preview = document.createElement("div");
  preview.className = "ai-reply-prompt-preview";
  preview.textContent = prompt;
  panel.appendChild(preview);

  // --- ボタン ---
  const actions = document.createElement("div");
  actions.className = "ai-reply-panel-actions";

  // 本命: プロンプトを持って ChatGPT を新しいタブで開く
  const openButton = document.createElement("button");
  openButton.className = "ai-reply-action-button ai-reply-action-primary";
  openButton.textContent = "🚀 ChatGPTで開く（プロンプト入り）";
  openButton.addEventListener("click", () => openInChatGPT(prompt));
  actions.appendChild(openButton);

  // 予備: プロンプトをコピーして、空の ChatGPT を開く
  // （?q= の仕組みが将来使えなくなった場合はこちらを使う）
  const copyButton = document.createElement("button");
  copyButton.className = "ai-reply-action-button ai-reply-action-secondary";
  copyButton.textContent = "📋 コピーしてChatGPTを開く（予備）";
  copyButton.addEventListener("click", () => copyAndOpenChatGPT(prompt, false));
  actions.appendChild(copyButton);

  panel.appendChild(actions);

  // --- 注意書き ---
  const note = document.createElement("div");
  note.className = "ai-reply-panel-note";
  note.textContent =
    "※ 送信は手動です。ChatGPTで気に入った案をコピーしたら、" +
    "Xに戻って「返信欄へ入力」ボタンを押してください";
  panel.appendChild(note);

  overlay.appendChild(panel);
  document.body.appendChild(overlay);
}

function closePanel() {
  const overlay = document.querySelector(".ai-reply-overlay");
  if (overlay) overlay.remove();
}

// プロンプトをURLに載せて ChatGPT を新しいタブで開く
function openInChatGPT(prompt) {
  const url = CHATGPT_URL + "?q=" + encodeURIComponent(prompt);

  // URLが長すぎる場合はコピー方式に自動で切り替える
  if (url.length > MAX_URL_LENGTH) {
    copyAndOpenChatGPT(prompt, true);
    return;
  }

  // タブを開くのは background.js の仕事（メッセージで依頼する）
  chrome.runtime.sendMessage({ type: "OPEN_CHATGPT", url });

  closePanel();
  showPasteBar();
}

// プロンプトをクリップボードにコピーしてから、空の ChatGPT を開く（予備手段）
async function copyAndOpenChatGPT(prompt, becauseTooLong) {
  try {
    await navigator.clipboard.writeText(prompt);
  } catch {
    // コピーに失敗してもタブは開く（パネルのプレビューから手動コピーできる）
  }

  chrome.runtime.sendMessage({ type: "OPEN_CHATGPT", url: CHATGPT_URL });

  closePanel();
  showToast(
    becauseTooLong
      ? "プロンプトが長いためコピー方式にしました。ChatGPTの入力欄に貼り付けて送信してください"
      : "プロンプトをコピーしました。ChatGPTの入力欄に貼り付けて送信してください",
    "normal",
    5000
  );
  showPasteBar();
}

// =====================================================================
// 4. ChatGPT でコピーしたリプ案を、対象投稿の返信欄へ入力する
//    ※ 入力するだけで、送信ボタンには一切触れません（送信は手動）
// =====================================================================

// ChatGPT へ行っている間、X の画面の右下に「返信欄へ入力」ボタンを出しておく
function showPasteBar() {
  removePasteBar();

  // どの投稿への返信かを、この時点の対象で確定させておく
  pendingTweet = currentTweet;

  const bar = document.createElement("div");
  bar.className = "ai-reply-paste-bar";

  const button = document.createElement("button");
  button.className = "ai-reply-paste-button";
  button.textContent = "📋 コピーした文章を返信欄へ入力";
  button.addEventListener("click", onPasteButtonClick);
  bar.appendChild(button);

  const close = document.createElement("button");
  close.className = "ai-reply-paste-close";
  close.textContent = "×";
  close.title = "閉じる";
  close.addEventListener("click", removePasteBar);
  bar.appendChild(close);

  document.body.appendChild(bar);
}

function removePasteBar() {
  const bar = document.querySelector(".ai-reply-paste-bar");
  if (bar) bar.remove();
}

// 入力処理が動いている間は true になるフラグ（二重入力の防止）
let isInserting = false;

async function onPasteButtonClick() {
  // 連打などで二重に動かないようにする
  if (isInserting) return;
  isInserting = true;

  try {
    // 1. クリップボードの中身を読む
    //    （初回は Chrome が「クリップボードの読み取りを許可しますか」と
    //      聞いてくるので「許可」を選ぶ）
    let text = "";
    try {
      text = (await navigator.clipboard.readText()).trim();
    } catch {
      throw new Error("クリップボードを読み取れませんでした。Chromeに表示される許可の確認で「許可」を選んでください");
    }

    // 2. 中身のチェック
    if (!text) {
      throw new Error("クリップボードが空です。ChatGPTで気に入ったリプ案をコピーしてから押してください");
    }
    if (lastPrompt && text === lastPrompt.trim()) {
      throw new Error("コピーされているのはプロンプトです。ChatGPTが生成したリプ案の方をコピーしてください");
    }

    // 3. 対象投稿の返信欄に入力する
    const result = await insertReplyText(pendingTweet, text);

    // 4. 結果に応じた案内を表示（送信は手動！）
    if (result === "already") {
      showToast("すでに入力済みです。送信は手動で行ってください");
    } else if (text.length > 140) {
      showToast(
        `✏ 入力しました。⚠ ${text.length}文字あり、Xの文字数制限を超える可能性があります。編集のうえ、送信は手動で行ってください`,
        "warn",
        6000
      );
    } else {
      showToast("✏ 入力しました。送信は手動です。内容を確認・編集してから送信してください", "normal", 5000);
    }

    removePasteBar();
  } catch (err) {
    console.warn("[AIリプ] 返信欄への入力に失敗:", err.message);
    showToast(err.message, "warn", 6000);
  } finally {
    isInserting = false;
  }
}

// 対象投稿の返信欄を開いて、文章を入力する（成功: "ok" / 入力済み: "already"）
async function insertReplyText(tweet, text) {
  // 対象の投稿がもう画面に無い場合（スクロールで消えた等）は失敗扱い
  if (!tweet || !document.contains(tweet)) {
    throw new Error("対象の投稿が画面から見つかりませんでした。投稿を表示して、もう一度「AIリプ」からやり直してください");
  }

  // 1. 対象投稿の返信ボタンを押して、返信画面を開く
  const replyButton = tweet.querySelector(SELECTORS.replyButton);
  if (!replyButton) {
    throw new Error("返信ボタンが見つかりませんでした");
  }
  replyButton.click();

  // 2. 返信の入力欄が開くのを待つ（最大4秒）
  const composer = await waitForElement(SELECTORS.composer, 4000);

  // 3. すでに同じ文章が入っていたら何もしない（二重入力の防止）
  if (composer.textContent.includes(text)) {
    return "already";
  }

  // 4. 文章を挿入して、本当に入ったか検証する
  const ok = await insertTextIntoComposer(composer, text);
  if (!ok) {
    throw new Error("返信欄への入力を確認できませんでした。お手数ですが手動で貼り付けてください（文章はコピーされたままです）");
  }

  return "ok";
}

// 指定したセレクタの要素が画面に現れるまで待つ（0.1秒ごとに確認）
function waitForElement(selector, timeoutMs) {
  return new Promise((resolve, reject) => {
    const startedAt = Date.now();
    const timer = setInterval(() => {
      const el = document.querySelector(selector);
      if (el) {
        clearInterval(timer);
        resolve(el);
      } else if (Date.now() - startedAt > timeoutMs) {
        clearInterval(timer);
        reject(new Error("返信欄が開きませんでした"));
      }
    }, 100);
  });
}

// 返信欄（contenteditable）に文章を挿入する。
//
// X の返信欄は React が管理していて、要素に文字を直接書き込むと
// 「見た目には入っているのに X の内部データは空」というズレが起きる。
// そこで、本物のユーザー操作と同じ経路で文字が入る方法を使う:
//   方法1: execCommand("insertText") … キー入力の再現
//   方法2: paste イベントの発行     … 貼り付けの再現（方法1がダメな場合）
// 挿入後に textContent を見て、本当に入ったかを必ず検証する。
async function insertTextIntoComposer(composer, text) {
  composer.focus();

  // 方法1: キー入力の再現
  try {
    document.execCommand("insertText", false, text);
  } catch {
    // 失敗しても方法2があるので何もしない
  }

  // React の画面更新を少し待ってから検証
  await sleep(300);
  if (composer.textContent.includes(text)) return true;

  // 方法2: 貼り付け操作の再現
  try {
    const data = new DataTransfer();
    data.setData("text/plain", text);
    composer.dispatchEvent(
      new ClipboardEvent("paste", {
        clipboardData: data,
        bubbles: true,
        cancelable: true,
      })
    );
  } catch {
    // 検証で失敗を検知するので何もしない
  }

  await sleep(300);
  return composer.textContent.includes(text);
}

// 指定ミリ秒だけ待つ小道具
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// 画面下に短時間だけ出る通知（トースト）
// type に "warn" を渡すとオレンジ色の警告表示になる
function showToast(message, type = "normal", durationMs = 3000) {
  // 前のトーストが残っていたら消す（重なり防止）
  document.querySelectorAll(".ai-reply-toast").forEach((el) => el.remove());

  const toast = document.createElement("div");
  toast.className = "ai-reply-toast" + (type === "warn" ? " ai-reply-toast-warn" : "");
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), durationMs);
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

console.log("[AIリプ] 拡張機能が読み込まれました（ChatGPT連携版）");
