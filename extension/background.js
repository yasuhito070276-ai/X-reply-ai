// =====================================================================
// バックグラウンド（AIチャットのタブ管理係）
//
// content.js（Xのページ側）から「AIチャットを表示して」というメッセージを
// 受け取り、選択中のサービス（Claude または ChatGPT）について次の順で
// タブを用意します。
//   1. 設定したチャット/プロジェクトURLのタブが開いていれば → 前面表示
//   2. 同じサービスの他のタブが開いていれば               → 前面表示
//   3. どちらも無ければ                                   → 設定URLを新しいタブで開く
//
// AIチャットのページの中身（入力欄・送信ボタン）には一切触れません。
// タブの検索と切り替えのために "tabs" 権限を使います。
// =====================================================================

// サービスごとの「開いているタブ」の探し方と、URL未設定時に開く場所
const SERVICES = {
  claude: {
    tabPatterns: ["https://claude.ai/*"],
    fallbackUrl: "https://claude.ai/",
  },
  chatgpt: {
    tabPatterns: ["https://chatgpt.com/*", "https://chat.openai.com/*"],
    fallbackUrl: "https://chatgpt.com/",
  },
};

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // 知らない種類のメッセージは無視する
  if (message.type !== "SHOW_AI_CHAT") return;

  showAiChat(message.service, message.chatUrl)
    .then((how) => sendResponse({ ok: true, how }))
    .catch((err) => sendResponse({ ok: false, error: err.message }));

  // 「あとで非同期に sendResponse を呼ぶ」という Chrome への合図
  return true;
});

// URL同士を比べやすいように、末尾の / や ?以降を取り除いてそろえる
function normalizeUrl(url) {
  if (!url) return "";
  return url.split("#")[0].split("?")[0].replace(/\/+$/, "");
}

async function showAiChat(service, chatUrl) {
  // 未知のサービス名が来たら Claude 扱いにする（安全側の既定値）
  const config = SERVICES[service] || SERVICES.claude;

  // 開いている同じサービスのタブをすべて探す
  const tabs = await chrome.tabs.query({ url: config.tabPatterns });

  // 1. 設定したURLのタブを最優先で探す
  let target = null;
  if (chatUrl) {
    target = tabs.find((tab) => normalizeUrl(tab.url) === normalizeUrl(chatUrl));
  }

  // 2. 無ければ、同じサービスの任意のタブでよい
  if (!target && tabs.length > 0) {
    target = tabs[0];
  }

  if (target) {
    // 見つかったタブを前面に表示する（タブの中身は操作しない）
    await chrome.tabs.update(target.id, { active: true });
    await chrome.windows.update(target.windowId, { focused: true });
    return "focused";
  }

  // 3. タブが1つも無い → 設定URL（無ければサービスのトップ）を新しいタブで開く
  await chrome.tabs.create({ url: chatUrl || config.fallbackUrl });
  return "opened";
}
