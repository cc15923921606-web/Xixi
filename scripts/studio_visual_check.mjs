import fs from "node:fs";
import http from "node:http";
import { spawn, spawnSync } from "node:child_process";

const edge = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const outputDir = "D:\\AI friend\\昔夕\\logs";
const port = 9333;
const profile = `${outputDir}\\edge-studio-visual-profile-${process.pid}`;

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function getJson(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (response) => {
      let body = "";
      response.setEncoding("utf8");
      response.on("data", (chunk) => { body += chunk; });
      response.on("end", () => {
        try { resolve(JSON.parse(body)); } catch (error) { reject(error); }
      });
    }).on("error", reject);
  });
}

async function waitForTarget() {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    try {
      const targets = await getJson(`http://127.0.0.1:${port}/json`);
      const target = targets.find((item) => item.type === "page" && item.url.includes("127.0.0.1:8765"));
      if (target) return target;
    } catch {}
    await delay(250);
  }
  throw new Error("Edge DevTools target did not become ready");
}

const browser = spawn(edge, [
  "--headless",
  "--disable-gpu",
  "--hide-scrollbars",
  `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`,
  "--window-size=1440,900",
  "http://127.0.0.1:8765/",
], { stdio: "ignore" });
let socket;

try {
  const target = await waitForTarget();
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });

  let nextId = 1;
  const pending = new Map();
  const errors = [];
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) reject(new Error(message.error.message));
      else resolve(message.result);
    }
    if (message.method === "Runtime.exceptionThrown") {
      errors.push(message.params.exceptionDetails.text);
    }
    if (message.method === "Log.entryAdded" && message.params.entry.level === "error") {
      errors.push(message.params.entry.text);
    }
  });

  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });

  const evaluate = async (expression, awaitPromise = true) => {
    const result = await send("Runtime.evaluate", { expression, awaitPromise, returnByValue: true });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
    return result.result.value;
  };

  const screenshot = async (name) => {
    const result = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    fs.writeFileSync(`${outputDir}\\${name}`, Buffer.from(result.data, "base64"));
  };

  await send("Runtime.enable");
  await send("Page.enable");
  await send("Log.enable");
  await delay(1200);
  await evaluate(`new Promise((resolve) => {
    const deadline = Date.now() + 12000;
    const check = () => {
      if (document.querySelector('#home-activity-summary')?.textContent !== '正在同步') resolve(true);
      else if (Date.now() > deadline) resolve(false);
      else setTimeout(check, 100);
    };
    check();
  })`);

  const views = ["home", "chat", "memory", "growth", "game", "system", "tuning"];
  const report = {};
  for (const view of views) {
    await evaluate(`setView(${JSON.stringify(view)}); true`);
    await delay(["memory", "system", "game"].includes(view) ? 900 : 180);
    report[view] = await evaluate(`(() => {
      const active = document.querySelector('#view-${view}');
      return {
        active: active?.classList.contains('active') || false,
        bodyWidth: document.body.scrollWidth,
        viewportWidth: document.documentElement.clientWidth,
        noHorizontalOverflow: document.body.scrollWidth <= document.documentElement.clientWidth,
        viewWidth: active?.scrollWidth || 0,
        viewClientWidth: active?.clientWidth || 0,
        visibleButtons: [...active.querySelectorAll('button')].filter((button) => button.getBoundingClientRect().width > 0).length,
      };
    })()`);
  }

  await evaluate(`setInspector(false); setView('system'); showSystemTab('overview'); true`);
  await evaluate(`new Promise((resolve) => {
    const deadline = Date.now() + 12000;
    const check = () => {
      if (document.querySelectorAll('#diagnostic-list .diagnostic-item').length) resolve(true);
      else if (Date.now() > deadline) resolve(false);
      else setTimeout(check, 120);
    };
    check();
  })`);
  await screenshot("studio-redesign-system-overview.png");
  report.diagnosticsDetail = await evaluate(`(() => {
    const runButton = document.querySelector('#run-diagnostics');
    runButton.disabled = true;
    const disabledButtonColor = getComputedStyle(runButton).color;
    const disabledTextColor = getComputedStyle(runButton.querySelector('span')).color;
    const disabledOpacity = getComputedStyle(runButton).opacity;
    runButton.disabled = false;
    return {
      checks: document.querySelectorAll('#diagnostic-list .diagnostic-item').length,
      attention: document.querySelector('#diagnostic-attention').textContent,
      visibleRepairButtons: [...document.querySelectorAll('#diagnostic-list [data-repair-service]')].filter((item) => item.offsetWidth > 0).length,
      disabledButtonColor,
      disabledTextColor,
      disabledOpacity,
    };
  })()`);

  await evaluate(`setView('system'); showSystemTab('activity'); showActivityTab('timeline'); true`);
  await delay(350);
  await screenshot("studio-redesign-activity.png");
  report.activityDetail = await evaluate(`({
    timelineItems: document.querySelectorAll('#activity-list .activity-item').length,
    contextCards: (showActivityTab('contexts'), document.querySelectorAll('#context-board .context-thread').length),
  })`);
  await delay(350);
  report.activityDetail.contextCards = await evaluate(`document.querySelectorAll('#context-board .context-thread').length`);

  await evaluate(`showSystemTab('logs'); true`);
  await delay(250);
  await screenshot("studio-redesign-system-logs.png");
  report.system = await evaluate(`({
    tabs: document.querySelectorAll('[data-system-tab]').length,
    activeTab: document.querySelector('[data-system-tab].active')?.dataset.systemTab,
    logLoaded: document.querySelector('#log-viewer').textContent.length > 0,
  })`);

  await evaluate(`setView('game'); true`);
  await delay(350);
  await screenshot("studio-redesign-game.png");
  report.gameDetail = await evaluate(`({
    screenSource: document.querySelector('#game-screen-source')?.textContent.trim() || '',
    intervalControl: Boolean(document.querySelector('#game-interval')),
    sessionControl: Boolean(document.querySelector('#toggle-game-session')),
    manualAnalysis: Boolean(document.querySelector('#analyze-game')),
    previewAvailable: Boolean(document.querySelector('#game-preview')),
    inputControlsRemoved: !document.querySelector('#game-window-select, #game-key-whitelist, #game-emergency-stop, [data-game-mode]'),
  })`);

  await evaluate(`setView('home'); setNavigation(false); setInspector(false); true`);
  await delay(180);
  await screenshot("studio-redesign-home.png");
  report.inspectorCollapsed = await evaluate(`(() => {
    const inspector = document.querySelector('#inspector').getBoundingClientRect();
    const rail = document.querySelector('#inspector-rail').getBoundingClientRect();
    const content = document.querySelector('#inspector-content');
    return {
      width: Math.round(inspector.width),
      railWidth: Math.round(rail.width),
      contentHidden: getComputedStyle(content).visibility === 'hidden',
      statusDots: document.querySelectorAll('.inspector-rail .rail-status-dot').length,
      redundantRuntimeButtonRemoved: !document.querySelector('.inspector-rail .rail-runtime'),
      explicitExpandButton: Boolean(document.querySelector('#expand-inspector [data-lucide="panel-right-open"]')),
      moodHasOwnButton: Boolean(document.querySelector('#inspector-mood-button [data-lucide="heart"]')),
      serviceSwitches: [...document.querySelectorAll('#inspector-rail [data-rail-service]')].map((button) => ({
        service: button.dataset.railService,
        pressed: button.getAttribute('aria-pressed'),
        coloredState: button.classList.contains('online') ? 'online' : (button.classList.contains('attention') ? 'attention' : 'offline'),
        hasStatusDot: Boolean(button.querySelector('.rail-status-dot')),
      })),
      serviceSwitchesUseWholeButtonColor: [...document.querySelectorAll('#inspector-rail [data-rail-service]')].every((button) => !button.querySelector('.rail-status-dot') && (button.classList.contains('online') || button.classList.contains('attention') || button.getAttribute('aria-pressed') === 'false')),
    };
  })()`);
  report.railServiceInteraction = await evaluate(`(async () => {
    const originalApi = api;
    const originalLoadStatus = loadStatus;
    const beforeView = state.currentView;
    const wasExpanded = document.body.classList.contains('inspector-open');
    const calls = [];
    try {
      api = async (path, options = {}) => {
        calls.push({ path, body: options.body || '' });
        if (path === '/api/settings') return { vision_enabled: false };
        return originalApi(path, options);
      };
      loadStatus = async () => state.status;
      const button = document.querySelector('[data-rail-service="vision"]');
      await toggleQuickService(button);
      await toggleQuickService(document.querySelector('[data-rail-service="learning"]'));
      const weatherButton = document.querySelector('[data-rail-service="weather"]');
      weatherButton.dataset.action = 'online';
      await toggleQuickService(weatherButton);
      return {
        calledVisionSetting: calls.some((call) => call.path === '/api/settings' && call.body.includes('vision_enabled')),
        calledLearningSetting: calls.some((call) => call.path === '/api/settings' && call.body.includes('learning_enabled')),
        calledWeatherSetting: calls.some((call) => call.path === '/api/settings' && call.body.includes('weather_alert_enabled')),
        weatherEnablesService: calls.filter((call) => call.path === '/api/settings' && call.body.includes('weather_alert_enabled')).every((call) => !call.body.includes('"weather_alert_enabled":true') || call.body.includes('"weather_enabled":true')),
        viewUnchanged: state.currentView === beforeView,
        inspectorStayedCollapsed: document.body.classList.contains('inspector-open') === wasExpanded,
      };
    } catch (error) {
      return { calledVisionSetting: false, viewUnchanged: false, inspectorStayedCollapsed: false, error: String(error?.message || error) };
    } finally {
      api = originalApi;
      loadStatus = originalLoadStatus;
      state.quickControlBusy = '';
      if (state.status) renderStatus(state.status);
    }
  })()`);
  report.sidebarCollapsed = await evaluate(`(() => {
    const sidebar = document.querySelector('#sidebar').getBoundingClientRect();
    const settings = document.querySelector('#sidebar .nav-settings').getBoundingClientRect();
    return {
      waveformShortcutRemoved: !document.querySelector('#sidebar .voice-mini'),
      settingsVisible: settings.width > 0 && settings.height > 0,
      settingsNearBottom: sidebar.bottom - settings.bottom <= 12,
      settingsIcon: Boolean(document.querySelector('#sidebar .nav-settings [data-lucide="settings-2"]')),
    };
  })()`);

  await evaluate(`setView('home'); setNavigation(true); true`);
  await delay(180);
  await screenshot("studio-redesign-navigation.png");
  report.navigation = await evaluate(`(() => {
    const sidebar = document.querySelector('#sidebar').getBoundingClientRect();
    const drawer = document.querySelector('#nav-drawer');
    const profileCopy = document.querySelector('#sidebar .profile-copy');
    return {
      open: document.body.classList.contains('navigation-open'),
      width: Math.round(sidebar.width),
      railVisible: getComputedStyle(document.querySelector('#sidebar')).visibility === 'visible',
      labelsVisible: [...document.querySelectorAll('#sidebar .nav-item span')].every((item) => item.offsetWidth > 0),
      profileVisible: profileCopy.offsetWidth > 0,
      duplicateDrawerHidden: !drawer || drawer.offsetWidth === 0,
      systemInMainNavigation: Boolean(document.querySelector('#sidebar [data-view="system"]')),
    };
  })()`);

  await evaluate(`setNavigation(false); setInspector(true); true`);
  await delay(180);
  await screenshot("studio-redesign-inspector.png");
  report.inspector = await evaluate(`({
    open: document.body.classList.contains('inspector-open'),
    width: document.querySelector('#inspector').getBoundingClientRect().width,
    contentVisible: getComputedStyle(document.querySelector('#inspector-content')).visibility === 'visible',
    railHidden: getComputedStyle(document.querySelector('#inspector-rail')).display === 'none',
    quickToggles: document.querySelectorAll('#inspector-status-list [data-quick-service]').length,
    quickSettings: document.querySelectorAll('#inspector-status-list [data-quick-panel]').length,
    relationshipCard: Boolean(document.querySelector('.relation-card')),
    redundantInterestCard: Boolean(document.querySelector('#inspector-interest-list')),
    redundantMetrics: Boolean(document.querySelector('.inspector-metrics')),
    quickServices: [...document.querySelectorAll('#inspector-status-list [data-quick-service]')].map((item) => ({ service: item.dataset.quickService, action: item.dataset.action, pressed: item.getAttribute('aria-pressed') })),
    homeShowsAllRailStatuses: ['qq', 'model', 'vision', 'voice', 'learning', 'weather'].every((service) => Boolean(document.querySelector('#inspector-status-list [data-quick-service="' + service + '"]'))),
  })`);

  await evaluate(`setView('chat'); setInspector(true); true`);
  await delay(180);
  report.chatInspector = await evaluate(`(() => {
    const conversation = document.querySelector('#view-chat .conversation-pane');
    return {
      legacyContextRemoved: !document.querySelector('#view-chat .context-pane'),
      contextTitle: document.querySelector('#inspector-context-title').textContent,
      visibleContextCards: [...document.querySelectorAll('.inspector-context')].filter((item) => item.offsetWidth > 0).length,
      voiceContextAvailable: Boolean(document.querySelector('#inspector-voice-reply')),
      redundantChatActionHidden: getComputedStyle(document.querySelector('#topbar-actions')).display === 'none',
      conversationWidth: Math.round(conversation.getBoundingClientRect().width),
      inspectorWidth: Math.round(document.querySelector('#inspector').getBoundingClientRect().width),
      noHorizontalOverflow: document.body.scrollWidth <= document.documentElement.clientWidth,
    };
  })()`);
  await screenshot("studio-redesign-chat-inspector.png");
  report.chatTools = await evaluate(`({
    historyMessages: document.querySelectorAll('#message-stream .message').length,
    searchRemoved: !document.querySelector('#chat-search-input, #chat-search-count, #clear-chat-search'),
    quotePreview: Boolean(document.querySelector('#reply-preview')),
    visibleStopWhileIdle: document.querySelector('#stop-message').offsetWidth > 0,
    copyButtons: document.querySelectorAll('[data-message-action="copy"]').length,
    replyButtons: document.querySelectorAll('[data-message-action="reply"]').length,
    regenerateButtons: document.querySelectorAll('[data-message-action="regenerate"]').length,
    voiceLanguageButtons: document.querySelectorAll('.composer-voice-language [data-voice-language]').length,
    activeVoiceLanguage: document.querySelector('.composer-voice-language [data-voice-language].active')?.dataset.voiceLanguage || '',
    composerFits: document.querySelector('.composer-tools').scrollWidth <= document.querySelector('.composer-actions').clientWidth,
    startsAtLatest: (() => {
      const stream = document.querySelector('#message-stream');
      return stream.scrollHeight - stream.clientHeight - stream.scrollTop <= 3;
    })(),
  })`);
  report.voiceInputOverlay = await evaluate(`(() => {
    openVoiceInput();
    const overlay = document.querySelector('#voice-input-overlay');
    const control = document.querySelector('#voice-record-control');
    const rect = overlay.getBoundingClientRect();
    return {
      visible: !overlay.hidden && rect.width > 0 && rect.height > 0,
      readyState: overlay.dataset.state === 'ready',
      status: document.querySelector('#voice-input-status').textContent,
      controlSize: Math.round(control.getBoundingClientRect().width),
      hasEscapeExit: document.querySelector('#voice-input-hint').textContent.includes('Esc'),
      containedByComposer: (() => {
        const composerRect = document.querySelector('.composer').getBoundingClientRect();
        return Math.abs(rect.width - composerRect.width) <= 2 && Math.abs(rect.height - composerRect.height) <= 2;
      })(),
      leavesMessagesVisible: document.querySelector('#message-stream').getBoundingClientRect().height > rect.height,
      noHorizontalOverflow: document.body.scrollWidth <= document.documentElement.clientWidth,
    };
  })()`);
  await screenshot("studio-voice-input-overlay.png");
  await evaluate(`closeVoiceInput(); true`);

  await evaluate(`setInspector(false); openCommandPalette(); true`);
  await delay(120);
  report.commandPalette = await evaluate(`({
    open: document.querySelector('#command-dialog').open,
    commands: document.querySelectorAll('#command-list [data-command-id]').length,
    selected: document.querySelector('#command-list .selected')?.dataset.commandId || '',
  })`);
  await screenshot("studio-redesign-command-palette.png");
  await evaluate(`document.querySelector('#command-dialog').close(); setNotificationPanel(true); true`);
  await delay(350);
  report.notifications = await evaluate(`({
    open: document.querySelector('#notification-panel').classList.contains('open'),
    items: document.querySelectorAll('#notification-list .notification-item').length,
    summary: document.querySelector('#notification-summary').textContent,
  })`);
  await screenshot("studio-redesign-notifications.png");
  await evaluate(`setNotificationPanel(false); true`);

  await evaluate(`setInspector(false); setView('tuning'); showTuningPanel('interface'); true`);
  await delay(180);
  await screenshot("studio-redesign-settings.png");
  report.settings = await evaluate(`(() => {
    const categories = ['interface', 'persona', 'conversation', 'learning', 'model', 'game', 'qq', 'desktop', 'data', 'environment', 'advanced'];
    const settingNames = [...document.querySelectorAll('#view-tuning [data-setting]')].map((item) => item.dataset.setting);
    return {
      active: document.querySelector('#tuning-interface').classList.contains('active'),
      categories: categories.filter((name) => Boolean(document.querySelector('#tuning-' + name))).length,
      missingCategories: categories.filter((name) => !document.querySelector('#tuning-' + name)),
      duplicateSettings: settingNames.filter((name, index) => settingNames.indexOf(name) !== index),
      runtimeSwitches: document.querySelectorAll('[data-service-toggle]').length,
      search: Boolean(document.querySelector('#settings-search-input')),
      themeControl: Boolean(document.querySelector('[data-local-setting="theme"]')),
      desktopControls: document.querySelectorAll('[data-desktop-setting]').length,
      desktopPanel: Boolean(document.querySelector('#tuning-desktop')),
      redundantSettingsMode: Boolean(document.querySelector('#settings-mode, [data-settings-mode], .advanced-setting')),
    };
  })()`);
  await evaluate(`document.documentElement.dataset.theme = 'dark'; true`);
  await delay(120);
  report.settings.darkTheme = await evaluate(`({
    theme: document.documentElement.dataset.theme,
    canvas: getComputedStyle(document.documentElement).getPropertyValue('--canvas').trim(),
    surface: getComputedStyle(document.documentElement).getPropertyValue('--surface').trim(),
  })`);
  await evaluate(`searchSettings('中文最终声线语速'); true`);
  await delay(120);
  report.settings.searchTarget = await evaluate(`({ current: state.currentTuning || '', voicePanelRemoved: !document.querySelector('#tuning-voice') })`);
  await evaluate(`searchSettings(''); true`);
  await delay(120);
  const settingsScreenshots = [
    ['desktop', 'studio-redesign-settings-startup.png'],
    ['interface', 'studio-redesign-settings-appearance.png'],
    ['persona', 'studio-redesign-settings-persona.png'],
    ['conversation', 'studio-redesign-settings-conversation.png'],
    ['learning', 'studio-redesign-settings-growth.png'],
    ['game', 'studio-redesign-settings-game.png'],
    ['environment', 'studio-redesign-settings-environment.png'],
    ['advanced', 'studio-redesign-settings-advanced.png'],
  ];
  for (const [panel, file] of settingsScreenshots) {
    await evaluate(`showTuningPanel('${panel}'); true`);
    await delay(panel === 'environment' ? 1200 : 180);
    await screenshot(file);
  }
  await evaluate(`showTuningPanel('data'); true`);
  await delay(350);
  report.settings.backupControl = await evaluate(`Boolean(document.querySelector('#create-backup'))`);
  await screenshot("studio-redesign-settings-data.png");
  await evaluate(`showTuningPanel('model'); true`);
  await delay(180);
  report.settings.modelConnection = await evaluate(`({
    providerListVisible: document.querySelector('#model-provider-list').offsetWidth > 0,
    providerCount: document.querySelectorAll('#model-provider-list .model-provider-card').length,
    addProviderVisible: document.querySelector('#add-model-provider').offsetWidth > 0,
    fallbackModelListVisible: document.querySelector('#fallback-model-list').offsetWidth > 0,
    legacyConnectionControlsRemoved: !document.querySelector('#test-model-connection, #save-model-connection, #model-provider, #model-base-url-row'),
    noHorizontalOverflow: document.body.scrollWidth <= document.documentElement.clientWidth,
  })`);
  await screenshot("studio-redesign-model-connection.png");
  await evaluate(`showTuningPanel('qq'); true`);
  await delay(180);
  report.settings.qqIdentity = await evaluate(`({
    botInputVisible: document.querySelector('#bot-qq-id').offsetWidth > 0,
    ownerInputVisible: document.querySelector('#owner-qq-id').offsetWidth > 0,
    saveButtonVisible: document.querySelector('#save-qq-identity').offsetWidth > 0,
    switchButtonVisible: document.querySelector('#switch-qq-account').offsetWidth > 0,
    actualAccount: document.querySelector('#qq-actual-account').textContent.trim(),
    matchStatus: document.querySelector('#qq-account-match').textContent.trim(),
    noHorizontalOverflow: document.body.scrollWidth <= document.documentElement.clientWidth,
  })`);
  await screenshot("studio-redesign-qq-identity.png");

  report.textOverflow = await evaluate(`(() => [...document.querySelectorAll('button, strong, span, p, small, h1, h2, h3')]
    .filter((item) => { const style = getComputedStyle(item); return item.offsetWidth > 0 && style.display !== 'none' && style.visibility === 'visible' && item.scrollWidth > item.clientWidth + 2 && style.overflowX !== 'auto'; })
    .slice(0, 20)
    .map((item) => ({ tag: item.tagName, id: item.id, className: item.className, text: item.textContent.trim().slice(0, 80), scrollWidth: item.scrollWidth, clientWidth: item.clientWidth })))()`);
  report.undersizedText = await evaluate(`(() => [...document.querySelectorAll('button, label, strong, span, p, small, time, input, textarea, select, th, td')]
    .filter((item) => {
      const style = getComputedStyle(item);
      return item.offsetWidth > 0 && style.display !== 'none' && style.visibility === 'visible'
        && item.textContent.trim() && Number.parseFloat(style.fontSize) < 11
        && !item.classList.contains('notification-badge');
    })
    .slice(0, 20)
    .map((item) => ({ tag: item.tagName, id: item.id, className: item.className, text: item.textContent.trim().slice(0, 80), fontSize: getComputedStyle(item).fontSize })))()`);

  report.runtime = await evaluate(`({ title: document.title, loaded: Boolean(state.bootstrap), currentView: state.currentView })`);
  report.qqControlInteraction = await evaluate(`(async () => {
    const originalApi = api;
    const calls = [];
    const offlineQq = {
      ...(state.status?.qq || {}),
      online: false,
      enabled: false,
      napcat_online: false,
      connection_state: 'offline',
      account_state: 'idle',
    };
    try {
      api = async (path, options = {}) => {
        calls.push({ path, body: options.body || '' });
        if (path === '/api/qq/control') {
          return { qq: { ...offlineQq, enabled: true, connection_state: 'connecting', account_state: 'starting' } };
        }
        if (path === '/api/status') {
          return { ...state.status, qq: { ...offlineQq, enabled: true, connection_state: 'connecting', account_state: 'starting' } };
        }
        return originalApi(path, options);
      };
      const button = document.querySelector('#toggle-qq');
      button.dataset.action = 'online';
      await toggleQq();
      state.qqAccountMonitorGeneration += 1;
      return {
        controlRequested: calls.some((call) => call.path === '/api/qq/control' && call.body.includes('online')),
        buttonUnlocked: !document.querySelector('#toggle-qq')?.disabled,
        runtimeError: '',
      };
    } catch (error) {
      return { controlRequested: false, buttonUnlocked: false, runtimeError: String(error?.message || error) };
    } finally {
      api = originalApi;
      state.qqControlBusy = false;
      state.qqAccountMonitorGeneration += 1;
    }
  })()`);
  report.errors = errors;
  fs.writeFileSync(`${outputDir}\\studio-visual-report.json`, JSON.stringify(report, null, 2));
  process.stdout.write(JSON.stringify(report, null, 2));
  socket.close();
} finally {
  socket?.close();
  if (browser.pid) {
    spawnSync("taskkill.exe", ["/PID", String(browser.pid), "/T", "/F"], { stdio: "ignore" });
  }
}
