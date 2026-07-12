// =====================================================================
// バックグラウンド（ChatGPTタブの管理係）
//
// content.js（Xのページ側）から「ChatGPTを表示して」というメッセージを
// 受け取り、次の順でタブを用意します。
//   1. 専用チャットのURLのタブが開いていれば → そのタブを前面表示
//   2. ChatGPTの他のタブが開いていれば     → それを前面表示
//   3. どちらも無ければ                     → 専用チャットURLを新しいタブで開く
//
// ChatGPTのページの中身（入力欄・送信ボタン）には一切触れません。
// タブの検索と切り替えのために "tabs" 権限を使います。
// =====================================================================

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // 知らない種類のメッセージは無視する
  if (message.type !== "SHOW_CHATGPT") return;

  showChatGPT(message.chatUrl)
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

async function showChatGPT(chatUrl) {
  // 開いているChatGPTのタブをすべて探す
  const tabs = await chrome.tabs.query({
    url: ["https://chatgpt.com/*", "https://chat.openai.com/*"],
  });

  // 1. 専用チャットのタブを最優先で探す
  let target = null;
  if (chatUrl) {
    target = tabs.find((tab) => normalizeUrl(tab.url) === normalizeUrl(chatUrl));
  }

  // 2. 無ければ、ChatGPTの任意のタブでよい
  if (!target && tabs.length > 0) {
    target = tabs[0];
  }

  if (target) {
    // 見つかったタブを前面に表示する（タブの中身は操作しない）
    await chrome.tabs.update(target.id, { active: true });
    await chrome.windows.update(target.windowId, { focused: true });
    return "focused";
  }

  // 3. ChatGPTのタブが1つも無い → 専用チャットURLを新しいタブで開く
  await chrome.tabs.create({ url: chatUrl || "https://chatgpt.com/" });
  return "opened";
}
