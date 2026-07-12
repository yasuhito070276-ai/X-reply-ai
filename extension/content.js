// =====================================================================
// X AIリプ アシスタント（ChatGPT専用チャット連携版）
// X のページに読み込まれて、以下を行うスクリプトです。
//   1. 各投稿に「AIリプ」ボタンを追加する
//   2. ボタンが押されたら、投稿本文と投稿者名を取得し、
//      設定されたプロンプト文面に差し込んでクリップボードへコピーする
//   3. 案内文を表示してから、ChatGPT のタブへ移動する
//      （専用チャットのタブがあればそれを前面表示。background.js が担当）
//   4. ChatGPT でコピーしたリプ案を、対象投稿の返信欄へ入力する
//
// 送信は必ず人間が行います。X にも ChatGPT にも自動送信のコードはありません。
// ChatGPT の画面（入力欄・送信ボタン）は一切操作しません。
// 設定（専用チャットURL・プロンプト・案内文）は settings.js + 設定画面で管理。
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

// 案内文を読む時間を確保するため、タブ切り替えを少し遅らせる（ミリ秒）
const TAB_SWITCH_DELAY = 1000;

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
// 2. 投稿を取得 → プロンプトをコピー → ChatGPT のタブへ
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

async function onAiReplyClick(tweet) {
  const info = getTweetInfo(tweet);

  // どの投稿へのリプか覚えておく（返信欄への入力時に使う）
  currentTweet = tweet;

  // 動作確認用：取得した内容を開発者ツールのコンソールにも出す
  console.log("[AIリプ] 取得した投稿:", info);

  // 設定（プロンプト文面・専用チャットURL・案内文）を読み込む
  const settings = await loadSettings();

  // プロンプトを組み立てる（settings.js の buildPrompt）
  const prompt = buildPrompt(settings.promptTemplate, info);
  lastPrompt = prompt;

  // クリップボードへコピー
  try {
    await navigator.clipboard.writeText(prompt);
  } catch {
    showToast("クリップボードへのコピーに失敗しました。もう一度お試しください", "warn", 5000);
    return;
  }

  // 案内文を表示（設定画面で変更できる）。
  // 専用チャットURLが未設定なら、設定を促すひとことを足す
  let message = settings.guideMessage;
  if (!settings.chatUrl) {
    message += "（拡張機能の設定画面で専用チャットURLを登録すると、毎回同じチャットが開きます）";
  }
  showToast(message, "normal", 6000);

  // ChatGPT から戻ってきたとき用の「返信欄へ入力」ボタンを出しておく
  showPasteBar();

  // 案内文を読む時間を少し置いてから、ChatGPT のタブへ移動する。
  // タブの検索・切り替え・作成は background.js の仕事（メッセージで依頼）
  setTimeout(() => {
    chrome.runtime.sendMessage({ type: "SHOW_CHATGPT", chatUrl: settings.chatUrl });
  }, TAB_SWITCH_DELAY);
}

// =====================================================================
// 3. ChatGPT でコピーしたリプ案を、対象投稿の返信欄へ入力する
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

console.log("[AIリプ] 拡張機能が読み込まれました（ChatGPT専用チャット連携版）");
