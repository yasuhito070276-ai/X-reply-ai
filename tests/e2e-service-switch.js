// =====================================================================
// AIサービス切り替え（Claude / ChatGPT）の自動テスト
//
// 確認すること:
//   1. 設定画面でサービスとURLを保存できる（不正URLは拒否）
//   2. Claude選択時: claude.ai のプロジェクトURLが開く／既存タブは前面表示
//   3. ChatGPT選択時: 従来どおり chatgpt.com のURLが開く
//   4. プロンプトはどちらのサービスでもクリップボードにコピーされる
//
// 実行方法:
//   cd tests
//   npm install playwright   （初回のみ。Chromium本体も必要）
//   node e2e-service-switch.js
// =====================================================================

const { chromium } = require("playwright");
const http = require("http");
const fs = require("fs");
const os = require("os");
const path = require("path");

const CLAUDE_URL = "https://claude.ai/project/test-proj";
const GPT_URL = "https://chatgpt.com/g/g-test-xreply";

(async () => {
  // 拡張機能を一時フォルダにコピーし、テスト用に2点だけ変更する:
  //   ・テストページ（localhost:8080）で動くように matches を変更
  //   ・background が実行した動作（開いた/前面表示したURL）を記録するフックを追加
  const extDir = fs.mkdtempSync(path.join(os.tmpdir(), "x-reply-ext-"));
  fs.cpSync(path.join(__dirname, "../extension"), extDir, { recursive: true });
  const manifestPath = path.join(extDir, "manifest.json");
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  manifest.content_scripts[0].matches = ["http://localhost:8080/*"];
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
  let bg = fs.readFileSync(path.join(extDir, "background.js"), "utf8");
  bg = bg.replace('return "focused";', 'self.lastAction = { how: "focused", url: target.url }; return "focused";');
  bg = bg.replace('return "opened";', 'self.lastAction = { how: "opened", url: chatUrl || config.fallbackUrl }; return "opened";');
  fs.writeFileSync(path.join(extDir, "background.js"), bg);

  const staticServer = http
    .createServer((req, res) => {
      res.setHeader("Content-Type", "text/html; charset=utf-8");
      res.end(fs.readFileSync(path.join(__dirname, "fixtures/draft.html")));
    })
    .listen(8080);

  const profileDir = fs.mkdtempSync(path.join(os.tmpdir(), "x-reply-profile-"));
  const context = await chromium.launchPersistentContext(profileDir, {
    headless: true,
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: [`--disable-extensions-except=${extDir}`, `--load-extension=${extDir}`],
    permissions: ["clipboard-read", "clipboard-write"],
  });
  // 外部サービスへの通信はテスト内で完結させる
  await context.route("https://claude.ai/**", (r) => r.fulfill({ contentType: "text/html", body: "fake claude" }));
  await context.route("https://chatgpt.com/**", (r) => r.fulfill({ contentType: "text/html", body: "fake chatgpt" }));

  const sw = context.serviceWorkers()[0] || (await context.waitForEvent("serviceworker"));
  const extId = new URL(sw.url()).host;
  const readAction = async () => {
    for (let i = 0; i < 40; i++) {
      const a = await sw.evaluate(() => self.lastAction);
      if (a) {
        await sw.evaluate(() => { self.lastAction = undefined; });
        return a;
      }
      await new Promise((r) => setTimeout(r, 100));
    }
    throw new Error("backgroundの動作が記録されなかった");
  };

  // ---- テスト1: 設定画面（サービス選択・URL検証・保存） ----
  const opt = await context.newPage();
  await opt.goto(`chrome-extension://${extId}/options.html`);
  await opt.waitForFunction(() => document.getElementById("promptTemplate").value.length > 0);

  const defaultService = await opt.evaluate(
    () => document.querySelector('input[name="aiService"]:checked')?.value
  );
  if (defaultService !== "claude") throw new Error("初期サービスがClaudeでない: " + defaultService);
  console.log("✅ 1-1: 初期状態でClaudeが選択されている");

  await opt.fill("#claudeUrl", "https://example.com/evil");
  await opt.click("#save");
  const err = await opt.$eval("#status", (el) => el.textContent);
  if (!err.includes("claude.ai")) throw new Error("Claude URLの検証が働いていない: " + err);
  console.log("✅ 1-2: claude.ai 以外のURLは保存できない");

  await opt.fill("#claudeUrl", CLAUDE_URL);
  await opt.fill("#chatUrl", GPT_URL);
  await opt.click("#save");
  await opt.waitForFunction(() => document.getElementById("status").textContent.includes("保存しました"));
  console.log("✅ 1-3: Claude/ChatGPT両方のURLを保存できた");
  await opt.close();

  // ---- テスト2: Claude選択時の動作 ----
  const page = await context.newPage();
  await page.goto("http://localhost:8080/");
  await page.waitForSelector(".ai-reply-button");
  await page.click(".ai-reply-button");
  await page.waitForSelector(".ai-reply-big-message");

  const clip = await page.evaluate(() => navigator.clipboard.readText());
  if (!clip.includes("【最優先指示】") || !clip.includes("毎朝のルーティン")) throw new Error("プロンプトが不正");
  console.log("✅ 2-1: プロンプトがコピーされた");

  const action1 = await readAction();
  if (action1.how !== "opened" || action1.url !== CLAUDE_URL) throw new Error("Claude URLが開かれない: " + JSON.stringify(action1));
  console.log("✅ 2-2: ClaudeプロジェクトURLが新しいタブで開いた");

  // 既存のClaudeタブがある場合は前面表示（新規タブなし）
  for (const p of context.pages()) {
    if (p !== page && p.url() !== "about:blank" && !p.url().startsWith("http://localhost")) await p.close();
  }
  const claudePage = await context.newPage();
  await claudePage.goto(CLAUDE_URL);
  const pagesBefore = context.pages().length;
  await page.bringToFront();
  await page.evaluate(() => document.querySelectorAll(".ai-reply-big-message").forEach((el) => el.remove()));
  await page.click(".ai-reply-button");
  const action2 = await readAction();
  if (action2.how !== "focused" || !action2.url.startsWith(CLAUDE_URL)) throw new Error("Claudeタブが前面表示されない: " + JSON.stringify(action2));
  if (context.pages().length !== pagesBefore) throw new Error("新規タブを作ってしまった");
  console.log("✅ 2-3: 既存のClaudeタブを前面表示（新規タブは作らない）");

  // ---- テスト3: ChatGPTへ切り替えた場合の動作 ----
  const opt2 = await context.newPage();
  await opt2.goto(`chrome-extension://${extId}/options.html`);
  await opt2.waitForFunction(() => document.getElementById("promptTemplate").value.length > 0);
  await opt2.check('input[name="aiService"][value="chatgpt"]');
  await opt2.click("#save");
  await opt2.waitForFunction(() => document.getElementById("status").textContent.includes("保存しました"));
  await opt2.close();

  await page.bringToFront();
  await page.evaluate(() => document.querySelectorAll(".ai-reply-big-message").forEach((el) => el.remove()));
  await page.click(".ai-reply-button");
  const action3 = await readAction();
  // Claudeのタブは開いているが、ChatGPT選択時はChatGPTのURLを開くはず
  if (action3.how !== "opened" || action3.url !== GPT_URL) throw new Error("ChatGPT URLが開かれない: " + JSON.stringify(action3));
  console.log("✅ 3: ChatGPTに切り替えると、ChatGPTのURLが開く（Claudeタブは無視）");

  await context.close();
  staticServer.close();
  console.log("--- 全テスト合格（サービス切り替え） ---");
})().catch((e) => {
  console.error("❌ テスト失敗:", e.message);
  process.exit(1);
});
