// =====================================================================
// 設定画面の処理
// 画面を開いたら保存済みの設定を表示し、「保存」で chrome.storage に書き込む。
// 設定の既定値と読み込み処理は settings.js にある。
// =====================================================================

const claudeUrlInput = document.getElementById("claudeUrl");
const chatUrlInput = document.getElementById("chatUrl");
const promptTemplateInput = document.getElementById("promptTemplate");
const guideMessageInput = document.getElementById("guideMessage");
const statusLabel = document.getElementById("status");

// 選択中のAIサービス（ラジオボタン）を読み書きする小道具
function getSelectedService() {
  const checked = document.querySelector('input[name="aiService"]:checked');
  return checked ? checked.value : DEFAULT_SETTINGS.aiService;
}
function setSelectedService(value) {
  const radio = document.querySelector(`input[name="aiService"][value="${value}"]`);
  if (radio) radio.checked = true;
}

// ---- 画面を開いたとき: 保存済みの設定を表示する ----
loadSettings().then((settings) => {
  setSelectedService(settings.aiService);
  claudeUrlInput.value = settings.claudeUrl;
  chatUrlInput.value = settings.chatUrl;
  promptTemplateInput.value = settings.promptTemplate;
  guideMessageInput.value = settings.guideMessage;
});

// ---- 保存ボタン ----
document.getElementById("save").addEventListener("click", () => {
  const aiService = getSelectedService();
  const claudeUrl = claudeUrlInput.value.trim();
  const chatUrl = chatUrlInput.value.trim();
  const promptTemplate = promptTemplateInput.value;
  const guideMessage = guideMessageInput.value.trim();

  // 入力チェック1: ClaudeのURLは空欄か、claude.ai のURLであること
  if (claudeUrl !== "" && !claudeUrl.startsWith("https://claude.ai/")) {
    showStatus("ClaudeのURLは https://claude.ai/ で始まるものを入力してください", true);
    return;
  }

  // 入力チェック2: ChatGPTのURLは空欄か、ChatGPTのURLであること
  if (
    chatUrl !== "" &&
    !chatUrl.startsWith("https://chatgpt.com/") &&
    !chatUrl.startsWith("https://chat.openai.com/")
  ) {
    showStatus("ChatGPTのURLは https://chatgpt.com/ で始まるものを入力してください", true);
    return;
  }

  // 入力チェック3: プロンプトに投稿本文の差し込み位置が必要
  // （新形式 {{postText}} または旧形式 {text} のどちらか）
  if (!promptTemplate.includes("{{postText}}") && !promptTemplate.includes("{text}")) {
    showStatus("プロンプトに {{postText}}（投稿本文の差し込み位置）が含まれていません", true);
    return;
  }

  chrome.storage.local.set(
    {
      aiService,
      claudeUrl,
      chatUrl,
      promptTemplate,
      guideMessage: guideMessage || DEFAULT_SETTINGS.guideMessage,
    },
    () => showStatus("保存しました ✓", false)
  );
});

// ---- 初期値に戻すボタン（画面に初期値を入れるだけ。保存で確定） ----
document.getElementById("reset").addEventListener("click", () => {
  setSelectedService(DEFAULT_SETTINGS.aiService);
  claudeUrlInput.value = "";
  chatUrlInput.value = "";
  promptTemplateInput.value = DEFAULT_SETTINGS.promptTemplate;
  guideMessageInput.value = DEFAULT_SETTINGS.guideMessage;
  showStatus("初期値を表示しました（「保存」を押すと確定します）", false);
});

// 保存結果などのメッセージを表示する（3秒で消える）
let statusTimer = null;
function showStatus(message, isError) {
  statusLabel.textContent = message;
  statusLabel.className = isError ? "error" : "";
  clearTimeout(statusTimer);
  statusTimer = setTimeout(() => (statusLabel.textContent = ""), 3000);
}
