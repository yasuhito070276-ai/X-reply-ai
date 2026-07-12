// =====================================================================
// バックグラウンド（タブを開く係）
//
// content.js（Xのページ側）から「ChatGPTを開いて」というメッセージを
// 受け取り、新しいタブで ChatGPT を開きます。
// API・サーバーへの通信はありません。
// =====================================================================

chrome.runtime.onMessage.addListener((message) => {
  // 知らない種類のメッセージは無視する
  if (message.type !== "OPEN_CHATGPT") return;

  // 念のため、開く先が ChatGPT であることを確認してからタブを開く
  if (typeof message.url === "string" && message.url.startsWith("https://chatgpt.com/")) {
    chrome.tabs.create({ url: message.url });
  }
});
