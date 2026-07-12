// =====================================================================
// バックグラウンド（通信係）
//
// content.js（Xのページ側）から「リプを生成して」というメッセージを
// 受け取り、バックエンドサーバーに問い合わせて結果を返します。
//
// ページ側から直接サーバーを呼ばずにここを経由するのは、
//   ・接続先の管理を1か所にまとめるため
//   ・Chrome拡張の通信許可（manifest.json の host_permissions）の
//     仕組みと相性が良いため
// です。
// =====================================================================

// バックエンドサーバーの場所。
// 将来サーバーをインターネット上に公開したら、ここを書き換えるだけでよい。
const API_URL = "http://localhost:3000/api/replies";

// content.js からのメッセージを待ち受ける
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // 知らない種類のメッセージは無視する
  if (message.type !== "GENERATE_REPLIES") return;

  // サーバーに投稿内容を送り、リプ3案をもらう
  fetch(API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ author: message.author, text: message.text }),
  })
    .then(async (res) => {
      if (!res.ok) {
        // サーバーがエラーを返した場合（例: 本文が空 → 400）
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || `サーバーエラーが発生しました（${res.status}）`);
      }
      return res.json();
    })
    .then((data) => {
      sendResponse({ ok: true, data });
    })
    .catch((err) => {
      // fetch自体の失敗は、ほとんどが「サーバーが起動していない」ケース
      const isNetworkError = err instanceof TypeError;
      sendResponse({
        ok: false,
        error: isNetworkError
          ? "サーバーに接続できませんでした。server フォルダで「npm start」を実行して、サーバーが起動しているか確認してください。"
          : err.message,
      });
    });

  // 「あとで非同期に sendResponse を呼ぶ」という Chrome への合図。
  // これを返さないと、応答を待たずに通信路が閉じられてしまう。
  return true;
});
