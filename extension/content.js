// =====================================================================
// X AIリプ アシスタント
// X のページに読み込まれて、以下の3つを行うスクリプトです。
//   1. 各投稿に「AIリプ」ボタンを追加する
//   2. ボタンが押されたら、その投稿の本文と投稿者名を取得し、
//      background.js（通信係）経由でバックエンドサーバーに生成を依頼する
//   3. 返ってきたリプ3案（本命・親しみ・知見）をパネルに表示する
//
// このファイルは「画面まわり」専門で、サーバーとの通信は
// background.js が担当します。
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

// 「AIリプ」ボタンを押した投稿を覚えておく変数。
// 候補クリック時に「この投稿の返信ボタン」を押すために使う。
// 画面に複数の投稿があっても対象を取り違えないための仕組み。
let currentTweet = null;

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

  // どの投稿へのリプか覚えておく（候補クリック時に使う）
  currentTweet = tweet;

  // 動作確認用：取得した内容を開発者ツールのコンソールにも出す
  console.log("[AIリプ] 取得した投稿:", info);

  // 先に「生成中…」の状態でパネルを開く
  showPanel(info);

  // background.js（通信係）にリプ生成を依頼する。
  // 結果は2つ目の引数の関数（コールバック）に後から届く。
  chrome.runtime.sendMessage(
    { type: "GENERATE_REPLIES", author: info.author, text: info.text },
    (response) => {
      // 拡張機能を更新した直後などは通信路が切れていることがある
      if (chrome.runtime.lastError || !response) {
        renderError("拡張機能内の通信に失敗しました。X のページを再読み込みしてから、もう一度お試しください。");
        return;
      }
      if (!response.ok) {
        renderError(response.error);
        return;
      }
      renderResult(response.data);
    }
  );
}

// =====================================================================
// 3. リプ3案をパネルに表示する
// =====================================================================

// パネルを「生成中…」の状態で開く
function showPanel(info) {
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

  // --- 中身の入れ物 ---
  // 最初は「生成中…」を表示し、サーバーから結果が届いたら
  // renderResult() / renderError() がここを書き換える
  const body = document.createElement("div");
  body.className = "ai-reply-panel-body";

  const loading = document.createElement("div");
  loading.className = "ai-reply-panel-loading";
  loading.textContent = "リプを生成中…";
  body.appendChild(loading);

  panel.appendChild(body);

  // --- 注意書き ---
  const note = document.createElement("div");
  note.className = "ai-reply-panel-note";
  note.textContent = "※ 送信は手動です。候補を選ぶと返信欄に入力されますが、自動送信は行いません";
  panel.appendChild(note);

  overlay.appendChild(panel);
  document.body.appendChild(overlay);
}

// サーバーから届いたリプ3案をパネルに表示する
function renderResult(result) {
  const body = document.querySelector(".ai-reply-panel-body");
  if (!body) return; // 結果が届く前にパネルが閉じられていたら何もしない

  body.innerHTML = ""; // 「生成中…」を消す

  // --- 採用した視点の表示 ---
  // AIがどの視点（優先順位）を選んだかの確認用
  const angle = document.createElement("div");
  angle.className = "ai-reply-panel-angle";
  angle.textContent = `視点: ${result.viewpoint}`;
  body.appendChild(angle);

  // --- リプ候補の一覧（本命・親しみ・知見） ---
  for (const reply of result.replies) {
    const item = document.createElement("button");
    item.className = "ai-reply-panel-item";

    // 「本命」などのラベル（バッジ）
    const label = document.createElement("span");
    label.className = "ai-reply-panel-item-label";
    label.textContent = reply.type;
    item.appendChild(label);

    // リプの本文
    const text = document.createElement("span");
    text.textContent = reply.text;
    item.appendChild(text);

    item.addEventListener("click", () => {
      onReplySelected(reply.text);
    });
    body.appendChild(item);
  }
}

// エラーメッセージをパネルに表示する
function renderError(message) {
  const body = document.querySelector(".ai-reply-panel-body");
  if (!body) return;

  body.innerHTML = "";

  const error = document.createElement("div");
  error.className = "ai-reply-panel-error";
  error.textContent = message;
  body.appendChild(error);
}

// =====================================================================
// 4. 選んだ候補を返信欄へ自動入力する
//    ※ 入力するだけで、送信ボタンには一切触れません（送信は手動）
// =====================================================================

// 入力処理が動いている間は true になるフラグ（二重入力の防止）
let isInserting = false;

async function onReplySelected(text) {
  // 連打などで二重に動かないようにする
  if (isInserting) return;
  isInserting = true;

  // どの投稿へのリプかは currentTweet に覚えてある
  const tweet = currentTweet;
  closePanel();

  try {
    // 対象の投稿がもう画面に無い場合（スクロールで消えた等）は失敗扱い
    if (!tweet || !document.contains(tweet)) {
      throw new Error("対象の投稿が画面から見つかりませんでした");
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
      showToast("すでに入力済みです。送信は手動で行ってください");
      return;
    }

    // 4. 文章を挿入して、本当に入ったか検証する
    const ok = await insertTextIntoComposer(composer, text);
    if (!ok) {
      throw new Error("返信欄への入力を確認できませんでした");
    }

    // 5. 完了。カーソルは返信欄にあるので、そのまま編集できる。
    //    文字数チェック（日本語の投稿はおおよそ140文字が上限）
    if (text.length > 140) {
      showToast(
        `✏ 入力しました。⚠ ${text.length}文字あり、Xの文字数制限を超える可能性があります。編集のうえ、送信は手動で行ってください`,
        "warn",
        6000
      );
    } else {
      showToast("✏ 入力しました。送信は手動です。内容を確認・編集してから送信してください", "normal", 5000);
    }
  } catch (err) {
    console.warn("[AIリプ] 自動入力に失敗:", err.message);

    // 失敗したらクリップボードにコピーして、手動での貼り付けをお願いする
    try {
      await navigator.clipboard.writeText(text);
      showToast("自動入力できなかったため、クリップボードにコピーしました。返信欄に貼り付けてください（送信は手動です）", "warn", 5000);
    } catch {
      showToast("自動入力もコピーもできませんでした。お手数ですが手動で入力してください", "warn", 5000);
    }
  } finally {
    isInserting = false;
  }
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

function closePanel() {
  const overlay = document.querySelector(".ai-reply-overlay");
  if (overlay) overlay.remove();
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

console.log("[AIリプ] 拡張機能が読み込まれました");
