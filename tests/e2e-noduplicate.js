// =====================================================================
// 重複入力が起きないことを確認する自動テスト
//
// Xの返信欄（Draft.js）の2つの特性を fixtures/draft.html で再現している:
//   ① 改行が別ブロックになり textContent から改行文字が消える
//   ② プログラムから発行された paste イベントにも反応して文章が入る
// この2つが揃うと、修正前のコード（v0.9.0以前）は
// 「execCommand成功 → 検証が改行のせいで失敗 → pasteで二重入力」になる。
//
// 実行方法:
//   cd tests
//   npm install playwright   （初回のみ。Chromium本体も必要）
//   node e2e-noduplicate.js
// =====================================================================

const { chromium } = require("playwright");
const http = require("http");
const fs = require("fs");
const os = require("os");
const path = require("path");

// 改行入りのリプ案（改行があると textContent 比較の弱点を突ける）
const REPLY = "本命：これは一行目です\n二行目もあります😊";
const REPLY2 = "知見：別の案です\n改行もあります";
const norm = (s) => s.replace(/\s+/g, "");

(async () => {
  // 拡張機能を一時フォルダにコピーし、テストページで動くように matches を変更
  const extDir = fs.mkdtempSync(path.join(os.tmpdir(), "x-reply-ext-"));
  fs.cpSync(path.join(__dirname, "../extension"), extDir, { recursive: true });
  const manifestPath = path.join(extDir, "manifest.json");
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  manifest.content_scripts[0].matches = ["http://localhost:8080/*"];
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));

  // テストページ（Draft.js風の返信欄）を配信
  const staticServer = http
    .createServer((req, res) => {
      res.setHeader("Content-Type", "text/html; charset=utf-8");
      res.end(fs.readFileSync(path.join(__dirname, "fixtures/draft.html")));
    })
    .listen(8080);

  const profileDir = fs.mkdtempSync(path.join(os.tmpdir(), "x-reply-profile-"));
  const context = await chromium.launchPersistentContext(profileDir, {
    headless: true,
    // 通常は Playwright 同梱の Chromium を使う。
    // 別の Chromium を使いたい場合は環境変数 CHROMIUM_PATH で指定できる
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: [`--disable-extensions-except=${extDir}`, `--load-extension=${extDir}`],
    permissions: ["clipboard-read", "clipboard-write"],
  });
  // ChatGPTへの通信はテスト内で完結させる（外部に出さない）
  await context.route("https://chatgpt.com/**", (r) =>
    r.fulfill({ contentType: "text/html", body: "test" })
  );

  const page = await context.newPage();
  await page.goto("http://localhost:8080/");
  await page.waitForSelector(".ai-reply-button");

  // 挿入回数を数える（空白・改行を除いて比較）
  const countOf = (needle) =>
    page.$eval(
      '[data-testid="tweetTextarea_0"]',
      (el, n) => el.textContent.replace(/\s+/g, "").split(n).length - 1,
      norm(needle)
    );

  // AIリプ → 大きな案内を閉じる → 待機ボタンが出るまで
  const pressAiReply = async () => {
    await page.click(".ai-reply-button");
    await page.waitForSelector(".ai-reply-big-message");
    await page.evaluate(() =>
      document.querySelectorAll(".ai-reply-big-message").forEach((el) => el.remove())
    );
    await page.waitForSelector(".ai-reply-paste-bar");
  };

  // ---- テストA: 改行入りリプ案の入力が「ちょうど1回」か ----
  await pressAiReply();
  await page.evaluate((r) => navigator.clipboard.writeText(r), REPLY);
  await page.click(".ai-reply-paste-button");
  await page.waitForSelector('[data-testid="tweetTextarea_0"]', { timeout: 6000 });
  await page.waitForTimeout(1500); // 挿入処理（検証の待ち時間を含む）の完了を待つ
  const countA = await countOf(REPLY);
  if (countA !== 1) throw new Error(`重複入力が発生: ${countA}回`);
  console.log("✅ A: 改行入りでも「ちょうど1回」だけ入力された");

  // ---- テストB: 同じ文章での再実行・連打では増えない ----
  await pressAiReply();
  await page.evaluate((r) => navigator.clipboard.writeText(r), REPLY);
  await page.$eval(".ai-reply-paste-button", (b) => {
    b.click();
    b.click();
    b.click();
  });
  await page.waitForTimeout(1500);
  const countB = await countOf(REPLY);
  if (countB !== 1) throw new Error(`連打で重複: ${countB}回`);
  console.log("✅ B: 同じ文章の再実行・連打でも1回のまま");

  // ---- テストC: 新しい文章の連打は「1回だけ」入る ----
  await pressAiReply();
  await page.evaluate((r) => navigator.clipboard.writeText(r), REPLY2);
  await page.$eval(".ai-reply-paste-button", (b) => {
    b.click();
    b.click();
  });
  await page.waitForTimeout(1500);
  const countC = await countOf(REPLY2);
  if (countC !== 1) throw new Error(`新しい文章が${countC}回入った`);
  console.log("✅ C: 新しい文章も連打で1回だけ入力された");

  // ---- テストD: DOM変化が続いてもAIリプボタンは1投稿に1つ ----
  for (let i = 0; i < 5; i++) {
    await page.evaluate(() => document.body.appendChild(document.createElement("span")));
    await page.waitForTimeout(150);
  }
  await page.waitForTimeout(500);
  const buttons = await page.$$eval("#tweet1 .ai-reply-button", (els) => els.length);
  if (buttons !== 1) throw new Error(`ボタンが${buttons}個ある`);
  console.log("✅ D: DOM変化後もAIリプボタンは1投稿に1つだけ");

  await context.close();
  staticServer.close();
  console.log("--- 全テスト合格（重複入力なし） ---");
})().catch((e) => {
  console.error("❌ テスト失敗:", e.message);
  process.exit(1);
});
