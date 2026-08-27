const state = {
  bootstrap: null,
  step: 1,
  environment: null,
  coreReady: false,
  languageTest: null,
  visionTest: null,
  languageSkipped: false,
  visionSkipped: false,
  visionMode: "same",
  busy: false,
  environmentInstallBusy: false,
  environmentPollTimer: null,
  assistantName: "昔夕",
};

const environmentFeatureCatalog = [
  { key: "local_voice", icon: "audio-waveform", title: "昔夕本地语音系统" },
  { key: "qq_channel", icon: "message-circle", title: "QQ 通道" },
  { key: "local_vision", icon: "scan-eye", title: "本地视觉" },
  { key: "speech_recognition", icon: "mic", title: "系统声音理解" },
  { key: "screen_observation", icon: "scan-line", title: "屏幕观察与截图" },
];

const stepMeta = [
  { icon: "cpu", title: "检查这台电脑", subtitle: "先确认核心环境，再了解哪些扩展能力已经就绪", note: "核心环境检查完成后即可继续" },
  { icon: "brain-circuit", title: "连接语言模型", subtitle: "现在连接供应商，或者进入应用后再配置", note: "检测连接与稍后配置均可继续" },
  { icon: "scan-eye", title: "配置视觉模型", subtitle: "可以单独连接视觉供应商，也可以稍后配置", note: "视觉模型不是进入应用的必要条件" },
  { icon: "heart-handshake", title: "建立关系资料", subtitle: "告诉昔夕如何认识、称呼和理解你", note: "资料之后仍可在设置中修改" },
  { icon: "sliders-horizontal", title: "选择初始能力", subtitle: "按需启用语音、学习、联网、天气和 QQ", note: "缺少的本地组件可以稍后安装" },
  { icon: "badge-check", title: "完成首次配置", subtitle: "复核连接与功能，保存后进入昔夕", note: "配置完成前不会进入主应用" },
];

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const defaultAssistantName = "昔夕";
let assistantCopyCaptured = false;
const assistantTextTemplates = [];
const assistantAttributeTemplates = [];

function assistantName(settings = state.bootstrap?.settings || {}) {
  const value = String(settings.assistant_name || state.assistantName || defaultAssistantName).replace(/\s+/g, " ").trim();
  return value || defaultAssistantName;
}

function assistantText(value, name = assistantName()) {
  const text = String(value ?? "");
  if (name === defaultAssistantName) return text;
  return text.replaceAll("昔夕", name).replaceAll("小夕", name).replaceAll("Xixi", name).replaceAll("XIXI", name);
}

function applyAssistantIdentity(nameValue) {
  if (!assistantCopyCaptured) {
    assistantCopyCaptured = true;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      if (/[昔夕小夕]/.test(node.nodeValue || "") || /Xixi|XIXI/.test(node.nodeValue || "")) {
        assistantTextTemplates.push([node, node.nodeValue]);
      }
      node = walker.nextNode();
    }
    $$('[title], [aria-label], [placeholder], [alt]').forEach((element) => {
      ["title", "aria-label", "placeholder", "alt"].forEach((attribute) => {
        const value = element.getAttribute(attribute);
        if (value && (/[昔夕小夕]/.test(value) || /Xixi|XIXI/.test(value))) {
          assistantAttributeTemplates.push([element, attribute, value]);
        }
      });
    });
  }
  const name = String(nameValue || defaultAssistantName).replace(/\s+/g, " ").trim() || defaultAssistantName;
  state.assistantName = name;
  assistantTextTemplates.forEach(([node, template]) => {
    if (node.isConnected) node.nodeValue = assistantText(template, name);
  });
  assistantAttributeTemplates.forEach(([element, attribute, template]) => {
    if (element.isConnected) element.setAttribute(attribute, assistantText(template, name));
  });
  document.title = `${name}配置中心`;
}

async function api(path, options = {}) {
  const { timeoutMs = 0, ...requestOptions } = options;
  const controller = timeoutMs > 0 ? new AbortController() : null;
  let timedOut = false;
  let timer = null;
  if (controller) {
    requestOptions.signal = controller.signal;
    timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
  }
  try {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(requestOptions.headers || {}) },
      ...requestOptions,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `请求失败 (${response.status})`);
    return payload;
  } catch (error) {
    if (timedOut) throw new Error("操作等待超时，请检查接口后重试");
    throw error;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

function applySetupTheme() {
  let theme = "system";
  try {
    const saved = JSON.parse(localStorage.getItem("xixi-studio-interface-settings") || "{}");
    if (["light", "dark", "system"].includes(saved.theme)) theme = saved.theme;
  } catch {
    theme = "system";
  }
  document.documentElement.dataset.theme = theme;
}

function iconRefresh() {
  if (window.lucide) window.lucide.createIcons({ attrs: { "stroke-width": 1.8 } });
}

function toast(message, type = "success") {
  const item = document.createElement("div");
  item.className = `toast ${type === "error" ? "error" : ""}`;
  item.textContent = assistantText(message);
  $("#toast-region").append(item);
  setTimeout(() => item.remove(), 3400);
}

function showBootstrapFailure(error) {
  $("#boot-error-message").textContent = error?.message || "本地服务还没有准备好，请稍等片刻后重试。";
  $("#boot-error-screen").hidden = false;
  document.body.classList.add("boot-failed");
  iconRefresh();
}

function hideBootstrapFailure() {
  $("#boot-error-screen").hidden = true;
  document.body.classList.remove("boot-failed");
}

function connection(kind) {
  if (kind === "language") {
    return {
      provider_name: $("#first-run-language-provider").value.trim(),
      base_url: $("#first-run-language-base-url").value.trim(),
      api_key: $("#first-run-language-api-key").value.trim(),
      model: $("#first-run-language-model").value.trim(),
    };
  }
  const shared = state.visionMode === "same";
  return {
    provider_name: shared ? $("#first-run-language-provider").value.trim() : $("#first-run-vision-provider").value.trim(),
    base_url: shared ? $("#first-run-language-base-url").value.trim() : $("#first-run-vision-base-url").value.trim(),
    api_key: shared ? $("#first-run-language-api-key").value.trim() : $("#first-run-vision-api-key").value.trim(),
    model: $("#first-run-vision-model").value.trim(),
  };
}

function connectionSignature(value) {
  return JSON.stringify([value.base_url, value.api_key, value.model]);
}

function modelTestMatches(kind) {
  const current = connection(kind);
  return Boolean(
    state[`${kind}Test`]
    && state[`${kind}Test`].signature === connectionSignature(current)
  );
}

function setTestStatus(kind, status, title, detail) {
  const host = $(`#first-run-${kind}-status`);
  const icons = { idle: "circle-dashed", busy: "loader-circle", ok: "circle-check-big", skipped: "clock-3", error: "circle-alert" };
  host.dataset.state = status;
  const icon = document.createElement("i");
  icon.dataset.lucide = icons[status] || icons.idle;
  const copy = document.createElement("span");
  const strong = document.createElement("strong");
  const small = document.createElement("small");
  strong.textContent = title;
  small.textContent = detail;
  copy.append(strong, small);
  host.replaceChildren(icon, copy);
  iconRefresh();
}

function invalidateModelTest(kind) {
  state[`${kind}Test`] = null;
  state[`${kind}Skipped`] = false;
  setTestStatus(
    kind,
    "idle",
    "等待检测",
    kind === "language" ? "可以检测连接，也可以选择稍后配置" : "可以检测图片输入，也可以选择稍后配置",
  );
  if (kind === "language" && state.visionMode === "same") {
    state.visionTest = null;
    setTestStatus("vision", "idle", "等待检测", "语言接口已经变化，请重新检测视觉模型");
  }
}

function statusRow({ title, detail, status, icon, progress = null, trailing = null }) {
  const row = document.createElement("article");
  row.className = `first-run-${status.core ? "check" : "capability"}-item ${status.state}`;
  const mark = document.createElement("i");
  const markIcon = document.createElement("i");
  markIcon.dataset.lucide = icon;
  mark.append(markIcon);
  const copy = document.createElement("div");
  const strong = document.createElement("strong");
  const small = document.createElement("small");
  strong.textContent = title;
  small.textContent = detail;
  copy.append(strong, small);
  if (progress) copy.append(progress);
  const label = document.createElement("em");
  label.textContent = status.label;
  row.append(mark, copy, trailing || label);
  return row;
}

function environmentJobActive(job = {}) {
  return ["installing", "paused", "cancelling"].includes(String(job.state || ""));
}

function formatEnvironmentBytes(value) {
  const bytes = Number(value || 0);
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  const size = bytes / (1024 ** index);
  return `${size >= 100 || index === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[index]}`;
}

function formatEnvironmentElapsed(value) {
  const seconds = Math.max(0, Math.floor(Number(value) || 0));
  if (!seconds) return "";
  if (seconds < 60) return `${seconds} 秒`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return remainder ? `${minutes} 分 ${remainder} 秒` : `${minutes} 分钟`;
}

function createEnvironmentProgress(job = {}) {
  if (!environmentJobActive(job)) return null;
  const host = document.createElement("div");
  host.className = `first-run-environment-progress ${job.state || "installing"}`;
  const summary = document.createElement("span");
  const downloaded = Number(job.downloaded_bytes || 0);
  const total = Number(job.total_bytes || 0);
  const speed = Number(job.speed_bps || 0);
  const elapsed = formatEnvironmentElapsed(job.elapsed_seconds);
  const progress = job.progress === null || job.progress === undefined || job.progress === "" || !Number.isFinite(Number(job.progress))
    ? null
    : Math.max(0, Math.min(100, Number(job.progress)));
  if (job.phase === "downloading" && total > 0) {
    summary.textContent = `${formatEnvironmentBytes(downloaded)} / ${formatEnvironmentBytes(total)}${speed ? ` · ${formatEnvironmentBytes(speed)}/s` : ""}${progress !== null ? ` · ${Math.round(progress)}%` : ""}`;
  } else if (job.phase === "downloading" && (downloaded > 0 || speed > 0)) {
    summary.textContent = `${formatEnvironmentBytes(downloaded)}${speed ? ` · ${formatEnvironmentBytes(speed)}/s` : ""} · 正在计算总大小`;
  } else {
    summary.textContent = `${job.detail || ({ preparing: "准备中", downloading: "正在下载", installing: "正在安装" }[job.phase] || "正在处理")}${elapsed ? ` · 已进行 ${elapsed}` : ""}`;
  }
  const track = document.createElement("span");
  track.className = `first-run-environment-progress-track${progress === null ? " indeterminate" : ""}`;
  track.setAttribute("role", "progressbar");
  track.setAttribute("aria-label", "组件安装进度");
  if (progress !== null) {
    track.setAttribute("aria-valuemin", "0");
    track.setAttribute("aria-valuemax", "100");
    track.setAttribute("aria-valuenow", String(Math.round(progress)));
  } else {
    track.setAttribute("aria-valuetext", "正在计算下载总大小");
  }
  const fill = document.createElement("i");
  if (progress !== null) fill.style.width = `${progress}%`;
  track.append(fill);
  host.append(summary, track);
  return host;
}

function createEnvironmentActions(item, job) {
  const host = document.createElement("div");
  host.className = "first-run-environment-actions";
  const label = document.createElement("em");
  label.textContent = item.status_label || (item.state === "ok" ? "已就绪" : "可稍后配置");
  host.append(label);

  const active = environmentJobActive(job);
  if (!active && item.repairable && item.action === "install") {
    const install = document.createElement("button");
    install.type = "button";
    install.className = "secondary-button compact-button";
    install.dataset.firstRunEnvironmentInstall = item.key;
    install.disabled = state.environmentInstallBusy;
    install.innerHTML = '<i data-lucide="download"></i><span>安装</span>';
    host.append(install);
    return host;
  }
  if (!active) return host;

  const controls = [
    ...(job.can_pause ? [["pause", "pause", "暂停"]] : []),
    ...(job.can_resume ? [["resume", "play", "继续"]] : []),
    ...(job.can_cancel ? [["cancel", "x", "取消"]] : []),
  ];
  controls.forEach(([action, icon, title]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `icon-button first-run-environment-control${action === "cancel" ? " danger" : ""}`;
    button.dataset.firstRunEnvironmentAction = action;
    button.dataset.firstRunEnvironmentKey = item.key;
    button.title = title;
    button.setAttribute("aria-label", title);
    button.innerHTML = `<i data-lucide="${icon}"></i>`;
    host.append(button);
  });
  return host;
}

function renderEnvironment() {
  const core = [
    { title: "本地后端", detail: "昔夕的配置与数据服务可以正常访问", ready: Boolean(state.bootstrap?.status?.app?.online), icon: "server" },
    { title: "桌面运行外壳", detail: "配置中心与原生窗口通信已经建立", ready: Boolean(window.pywebview?.api), icon: "panel-top" },
    { title: "配置页面", detail: "独立配置页面已经完整加载", ready: document.readyState !== "loading", icon: "app-window" },
    { title: "独立数据空间", detail: "聊天、记忆与设置保存在独立目录", ready: Boolean(state.bootstrap?.settings), icon: "database" },
  ];
  state.coreReady = core.every((item) => item.ready);
  $("#first-run-core-checks").replaceChildren(...core.map((item) => statusRow({
    title: item.title,
    detail: item.detail,
    icon: item.ready ? "check" : item.icon,
    status: { core: true, state: item.ready ? "ok" : "missing", label: item.ready ? "可以使用" : "正在连接" },
  })));

  const featureMeta = new Map(environmentFeatureCatalog.map((item) => [item.key, item]));
  const items = (state.environment?.items || []).filter((item) => item.key !== "chat_model");
  const jobs = state.environment?.jobs || {};
  const installable = items.filter((item) => {
    const job = jobs[item.key] || item.job || {};
    return item.repairable && item.action === "install" && item.state !== "ok" && !environmentJobActive(job);
  });
  const backendBusy = items.some((item) => environmentJobActive(jobs[item.key] || item.job || {}));
  const installAll = $("#first-run-install-missing");
  installAll.disabled = state.environmentInstallBusy || backendBusy || installable.length === 0;
  installAll.dataset.environmentKeys = installable.map((item) => item.key).join(",");
  installAll.innerHTML = state.environmentInstallBusy || backendBusy
    ? '<i data-lucide="loader-circle"></i><span>正在安装</span>'
    : `<i data-lucide="${installable.length ? "package-plus" : "circle-check-big"}"></i><span>${installable.length ? `安装缺失项 (${installable.length})` : "环境已就绪"}</span>`;
  $("#first-run-environment-list").replaceChildren(...items.map((item) => {
    const meta = featureMeta.get(item.key) || { title: item.key, icon: "box" };
    const ready = item.state === "ok";
    const optional = item.state === "optional";
    const job = jobs[item.key] || item.job || {};
    const active = environmentJobActive(job);
    return statusRow({
      title: assistantText(meta.title),
      detail: active ? (job.detail || item.detail || "正在处理") : (item.detail || "等待检查"),
      icon: ready ? "check" : meta.icon,
      progress: createEnvironmentProgress(job),
      trailing: createEnvironmentActions(item, job),
      status: {
        core: false,
        state: active ? (job.state || "installing") : (optional ? "optional" : (ready ? "ok" : "missing")),
        label: item.status_label || (ready ? "已就绪" : "可稍后配置"),
      },
    });
  }));
  if (state.step === 1) {
    $("#first-run-footer-note").textContent = state.coreReady ? "核心环境检查通过，可以继续" : "正在等待桌面环境连接";
  }
  if (state.environmentPollTimer) clearTimeout(state.environmentPollTimer);
  state.environmentPollTimer = null;
  if (backendBusy && !state.environmentInstallBusy) {
    state.environmentPollTimer = setTimeout(() => {
      state.environmentPollTimer = null;
      void refreshEnvironment({ silent: true });
    }, 900);
  }
  iconRefresh();
}

async function refreshEnvironment({ silent = false } = {}) {
  const button = $("#first-run-refresh-environment");
  button.disabled = true;
  try {
    state.environment = await api("/api/environment", { timeoutMs: 20000 });
  } catch (error) {
    if (!state.environment) state.environment = { items: [], jobs: {} };
    if (!silent) toast(`环境检查未完全完成：${error.message}`, "error");
  } finally {
    renderEnvironment();
    button.disabled = false;
  }
}

async function waitForEnvironmentInstall(key) {
  for (let attempt = 0; attempt < 14400; attempt += 1) {
    const snapshot = await api("/api/environment/jobs", { timeoutMs: 20000 });
    const jobs = snapshot.jobs || {};
    state.environment = { ...(state.environment || {}), jobs };
    const current = jobs[key] || {};
    renderEnvironment();
    if (!environmentJobActive(current)) return current;
    await new Promise((resolve) => setTimeout(resolve, 800));
  }
  throw new Error("安装等待超时，请检查网络后重试");
}

async function installEnvironmentDependencies(keys) {
  const requested = [...new Set(keys.filter(Boolean))];
  if (!requested.length || state.environmentInstallBusy) return;
  state.environmentInstallBusy = true;
  renderEnvironment();
  let cursor = 0;
  const errors = [];
  const maxConcurrent = Math.max(1, Number(state.environment?.max_concurrent_jobs) || 3);
  try {
    const worker = async () => {
      while (cursor < requested.length) {
        const key = requested[cursor];
        cursor += 1;
        try {
      const environment = await api("/api/environment", { timeoutMs: 20000 });
      state.environment = environment;
      const item = (environment.items || []).find((candidate) => candidate.key === key);
      if (!item || item.state === "ok" || !item.repairable || item.action !== "install") continue;
      const title = environmentFeatureCatalog.find((candidate) => candidate.key === key)?.title || key;
      toast(`正在安装：${title}`);
      const started = await api("/api/environment/install", {
        method: "POST",
        body: JSON.stringify({ key }),
        timeoutMs: 20000,
      });
      state.environment = {
        ...(state.environment || environment),
        jobs: { ...(state.environment?.jobs || environment.jobs || {}), [key]: started },
      };
      renderEnvironment();
      const completed = await waitForEnvironmentInstall(key);
      if (completed?.state === "cancelled") {
            toast(`${assistantText(title)}安装已取消`);
            continue;
      }
      if (completed?.state !== "completed") {
        throw new Error(completed?.detail || `${title}安装失败`);
      }
          toast(`${assistantText(title)}安装完成`);
        } catch (error) {
          errors.push(error);
        }
      }
    };
    await Promise.all(
      Array.from({ length: Math.min(maxConcurrent, requested.length) }, () => worker()),
    );
    if (errors.length) {
      throw errors[0];
    }
    await refreshEnvironment({ silent: true });
    toast("所需环境组件已经安装完成");
  } catch (error) {
    toast(`安装失败：${error.message}`, "error");
  } finally {
    state.environmentInstallBusy = false;
    await refreshEnvironment({ silent: true });
  }
}

async function controlEnvironmentInstall(key, action, button) {
  button.disabled = true;
  try {
    const job = await api(`/api/environment/${action}`, {
      method: "POST",
      body: JSON.stringify({ key }),
      timeoutMs: 20000,
    });
    state.environment = {
      ...(state.environment || {}),
      jobs: { ...(state.environment?.jobs || {}), [key]: job },
    };
    renderEnvironment();
  } catch (error) {
    toast(error.message, "error");
    button.disabled = false;
  }
}

function handleEnvironmentAction(event) {
  const control = event.target.closest("[data-first-run-environment-action]");
  if (control) {
    void controlEnvironmentInstall(
      control.dataset.firstRunEnvironmentKey,
      control.dataset.firstRunEnvironmentAction,
      control,
    );
    return;
  }
  const install = event.target.closest("[data-first-run-environment-install]");
  if (install) void installEnvironmentDependencies([install.dataset.firstRunEnvironmentInstall]);
}

function setVisionMode(mode, { invalidate = true } = {}) {
  state.visionMode = mode === "separate" ? "separate" : "same";
  state.visionSkipped = false;
  $$('[data-first-run-vision-mode]').forEach((button) => {
    button.classList.toggle("active", button.dataset.firstRunVisionMode === state.visionMode);
  });
  $("#first-run-vision-separate-fields").hidden = state.visionMode !== "separate";
  $("#first-run-vision-shared-note").hidden = state.visionMode !== "same";
  if (invalidate) invalidateModelTest("vision");
}

function syncVisionEnabled() {
  const enabled = $("#first-run-vision-enabled").checked;
  if (enabled) state.visionSkipped = false;
  $("#first-run-vision-fields").hidden = !enabled;
  $("#first-run-vision-disabled-note").hidden = enabled;
  if (!enabled) state.visionTest = null;
}

function syncQqEnabled() {
  $("#first-run-qq-fields").hidden = !$("#first-run-feature-qq").checked;
}

async function discoverModels(kind) {
  const previousLanguageSignature = connectionSignature(connection("language"));
  const previousVisionSignature = connectionSignature(connection("vision"));
  const value = connection(kind);
  if (!value.base_url) throw new Error("请先填写 API 地址");
  const button = $(`#first-run-${kind}-discover`);
  button.disabled = true;
  try {
    const result = await api("/api/model/providers/discover", {
      method: "POST",
      body: JSON.stringify({ base_url: value.base_url, api_key: value.api_key }),
      timeoutMs: 30000,
    });
    const options = (result.models || []).map((model) => {
      const option = document.createElement("option");
      option.value = model.id;
      option.label = model.name || model.id;
      return option;
    });
    $(`#first-run-${kind}-model-options`).replaceChildren(...options);
    if (result.base_url) {
      const input = kind === "language" || state.visionMode === "same"
        ? $("#first-run-language-base-url")
        : $("#first-run-vision-base-url");
      input.value = result.base_url;
    }
    if (options.length === 1) $(`#first-run-${kind}-model`).value = options[0].value;
    const languageChanged = previousLanguageSignature !== connectionSignature(connection("language"));
    const visionChanged = previousVisionSignature !== connectionSignature(connection("vision"));
    if (languageChanged) invalidateModelTest("language");
    else if (visionChanged) invalidateModelTest("vision");
    toast(options.length ? `已获取 ${options.length} 个模型` : "接口没有返回模型目录，可以手动填写模型 ID");
  } finally {
    button.disabled = false;
  }
}

async function testModel(kind) {
  const value = connection(kind);
  if (!value.provider_name) throw new Error("请填写供应商名称");
  if (!value.base_url || !value.model) throw new Error("请填写 API 地址和模型 ID");
  const button = $(`#first-run-${kind}-test`);
  button.disabled = true;
  setTestStatus(kind, "busy", "正在检测", "正在识别接口类型并发送最小测试请求");
  try {
    const result = await api("/api/model/connection/test", {
      method: "POST",
      body: JSON.stringify({ target: kind, connection: value }),
      timeoutMs: 35000,
    });
    state[`${kind}Skipped`] = false;
    state[`${kind}Test`] = { signature: connectionSignature(value), result };
    setTestStatus(kind, "ok", "连接成功", `${result.api_label || result.provider || "接口已识别"} · ${result.model || value.model}`);
  } catch (error) {
    state[`${kind}Test`] = null;
    setTestStatus(kind, "error", "连接失败", error.message);
    throw error;
  } finally {
    button.disabled = false;
  }
}

async function ensureModelTest(kind) {
  if (modelTestMatches(kind)) return;
  await testModel(kind);
  if (!modelTestMatches(kind)) {
    throw new Error(kind === "language" ? "语言模型最终检测未通过" : "视觉模型最终检测未通过");
  }
}

function validateStep(step) {
  if (step === 1 && !state.coreReady) throw new Error("桌面环境还没有连接完成，请重新检查");
  if (step === 2 && !state.languageSkipped) {
    const current = connection("language");
    if (!modelTestMatches("language")) {
      throw new Error("请先检测并确认语言模型可用");
    }
  }
  if (step === 3 && $("#first-run-vision-enabled").checked && !state.visionSkipped) {
    const current = connection("vision");
    if (!modelTestMatches("vision")) {
      throw new Error("请先检测视觉模型，或者关闭图片理解");
    }
  }
  if (step === 4) {
    if (!$("#first-run-assistant-name").value.trim() || !$("#first-run-owner-name").value.trim() || !$("#first-run-owner-addresses").value.trim() || !$("#first-run-owner-relationship").value.trim()) {
      throw new Error("请填写角色名称、显示名称、称呼和关系");
    }
  }
  if (step === 5) {
    if ($("#first-run-feature-weather").checked && !$("#first-run-city").value.trim()) {
      throw new Error("启用天气提醒前请先填写城市");
    }
    if ($("#first-run-feature-qq").checked) {
      const ownerQq = $("#first-run-owner-qq").value.trim();
      const botQq = $("#first-run-bot-qq").value.trim();
      if (!/^[1-9]\d{4,11}$/.test(ownerQq) || !/^[1-9]\d{4,11}$/.test(botQq)) {
        throw new Error("启用 QQ 时，请填写两个 5 到 12 位 QQ 号");
      }
      if (ownerQq === botQq) throw new Error(`使用者 QQ 和${assistantName()}登录 QQ 不能相同`);
    }
  }
  return true;
}

function renderSummary() {
  const language = connection("language");
  const languageEnabled = !state.languageSkipped;
  const visionEnabled = $("#first-run-vision-enabled").checked && !state.visionSkipped;
  const vision = connection("vision");
  const features = [
    [$("#first-run-feature-voice").checked, "语音"],
    [$("#first-run-feature-learning").checked, "持续学习"],
    [$("#first-run-feature-search").checked, "联网搜索"],
    [$("#first-run-feature-weather").checked, "天气提醒"],
    [$("#first-run-feature-qq").checked, "QQ"],
  ].filter(([enabled]) => enabled).map(([, label]) => label);
  const rows = [
    ["badge", "角色名称", $("#first-run-assistant-name").value.trim(), "已命名"],
    ["brain-circuit", "语言模型", languageEnabled ? `${language.provider_name} · ${language.model}` : "进入应用后在“模型与 API”中配置", languageEnabled ? "已检测" : "已跳过"],
    ["scan-eye", "视觉模型", visionEnabled ? `${vision.provider_name} · ${vision.model}` : "暂不启用图片理解", visionEnabled ? "已检测" : "已跳过"],
    ["heart-handshake", "关系资料", `${$("#first-run-owner-name").value.trim()} · ${$("#first-run-owner-relationship").value.trim()}`, "已填写"],
    ["sliders-horizontal", "初始能力", features.join("、") || "全部保持关闭", `${features.length} 项启用`],
    ["hard-drive", "本地数据", "使用独立数据目录保存聊天、记忆与设置", "已隔离"],
  ];
  $("#first-run-summary").replaceChildren(...rows.map(([iconName, title, detail, label]) => {
    const row = document.createElement("div");
    row.className = "first-run-summary-row";
    const icon = document.createElement("i");
    icon.dataset.lucide = iconName;
    const copy = document.createElement("div");
    const strong = document.createElement("strong");
    const small = document.createElement("small");
    strong.textContent = title;
    small.textContent = detail;
    copy.append(strong, small);
    const status = document.createElement("span");
    status.textContent = label;
    row.append(icon, copy, status);
    return row;
  }));
  iconRefresh();
}

function setStep(step) {
  const nextStep = Math.max(1, Math.min(6, Number(step) || 1));
  state.step = nextStep;
  const meta = stepMeta[nextStep - 1];
  $$('[data-first-run-page]').forEach((page) => page.classList.toggle("active", Number(page.dataset.firstRunPage) === nextStep));
  $$('[data-first-run-nav]').forEach((item) => {
    const index = Number(item.dataset.firstRunNav);
    item.classList.toggle("active", index === nextStep);
    item.classList.toggle("complete", index < nextStep);
  });
  $$("#first-run-dialog .first-run-progress i").forEach((segment, index) => {
    segment.classList.toggle("active", index === nextStep - 1);
    segment.classList.toggle("complete", index < nextStep - 1);
  });
  $("#first-run-step-icon").setAttribute("data-lucide", meta.icon);
  $("#first-run-title").textContent = assistantText(meta.title);
  $("#first-run-subtitle").textContent = assistantText(meta.subtitle);
  $("#first-run-count").textContent = `${nextStep} / 6`;
  $("#first-run-footer-note").textContent = meta.note;
  $("#first-run-back").hidden = nextStep === 1;
  $("#first-run-next").hidden = nextStep === 6;
  $("#first-run-finish").hidden = nextStep !== 6;
  if (nextStep === 6) renderSummary();
  $("#first-run-dialog .first-run-content").scrollTop = 0;
  iconRefresh();
}

function fillSetup(settings = {}) {
  const configuredName = String(settings.assistant_name || defaultAssistantName).trim() || defaultAssistantName;
  $("#first-run-assistant-name").value = configuredName;
  applyAssistantIdentity(configuredName);
  $("#first-run-language-provider").value = "";
  $("#first-run-language-base-url").value = "";
  $("#first-run-language-api-key").value = "";
  $("#first-run-language-api-key").placeholder = "本地无鉴权接口可以留空";
  $("#first-run-language-model").value = "";
  $("#first-run-vision-provider").value = "";
  $("#first-run-vision-base-url").value = "";
  $("#first-run-vision-api-key").value = "";
  $("#first-run-vision-api-key").placeholder = "本地无鉴权接口可以留空";
  $("#first-run-vision-model").value = "";
  $("#first-run-owner-name").value = settings.owner_display_name === "主人" ? "" : (settings.owner_display_name || "");
  $("#first-run-owner-addresses").value = settings.owner_addresses === "主人" ? "" : (settings.owner_addresses || "");
  $("#first-run-owner-relationship").value = settings.owner_relationship || "创造者与重要的人";
  $("#first-run-city").value = settings.weather_location === "未设置" ? "" : (settings.weather_location || "");
  $("#first-run-owner-qq").value = state.bootstrap?.qq_identity?.owner_qq_id || "";
  $("#first-run-bot-qq").value = state.bootstrap?.qq_identity?.bot_qq_id || "";
  $("#first-run-feature-voice").checked = true;
  $("#first-run-feature-learning").checked = true;
  $("#first-run-feature-search").checked = true;
  $("#first-run-feature-weather").checked = Boolean(settings.weather_alert_enabled);
  $("#first-run-feature-qq").checked = Boolean(settings.qq_enabled);
  $("#first-run-vision-enabled").checked = true;
  state.languageSkipped = false;
  state.visionSkipped = false;
  setVisionMode("same", { invalidate: false });
  syncVisionEnabled();
  syncQqEnabled();
  setStep(1);
  renderEnvironment();
  void refreshEnvironment();
}

async function completeSetup(event) {
  event.preventDefault();
  if (state.step !== 6) {
    validateStep(state.step);
    setStep(state.step + 1);
    return;
  }
  validateStep(4);
  validateStep(5);
  if (state.busy) return;
  state.busy = true;
  const finish = $("#first-run-finish");
  finish.disabled = true;
  $("#first-run-back").disabled = true;
  $("#first-run-finish-status").hidden = false;
  try {
    if (!state.languageSkipped) await ensureModelTest("language");
    if ($("#first-run-vision-enabled").checked && !state.visionSkipped) {
      await ensureModelTest("vision");
    }
    const language = connection("language");
    const languageEnabled = !state.languageSkipped;
    if (languageEnabled) {
      await api("/api/model/connection/apply", {
        method: "POST",
        body: JSON.stringify({ target: "language", provider_id: "first-run-primary", provider_name: language.provider_name, connection: language }),
        timeoutMs: 60000,
      });
    }
    const visionEnabled = $("#first-run-vision-enabled").checked && !state.visionSkipped;
    if (visionEnabled) {
      const vision = connection("vision");
      await api("/api/model/connection/apply", {
        method: "POST",
        body: JSON.stringify({ target: "vision", provider_id: state.visionMode === "same" ? "first-run-primary" : "first-run-vision", provider_name: vision.provider_name, connection: vision }),
        timeoutMs: 60000,
      });
    }
    const city = $("#first-run-city").value.trim();
    const qqEnabled = $("#first-run-feature-qq").checked;
    const values = {
      assistant_name: $("#first-run-assistant-name").value.trim(),
      owner_display_name: $("#first-run-owner-name").value.trim(),
      owner_addresses: $("#first-run-owner-addresses").value.trim(),
      owner_relationship: $("#first-run-owner-relationship").value.trim(),
      brain_enabled: languageEnabled,
      vision_enabled: visionEnabled,
      voice_enabled: $("#first-run-feature-voice").checked,
      learning_enabled: $("#first-run-feature-learning").checked,
      anime_learning_enabled: $("#first-run-feature-learning").checked,
      web_search_enabled: $("#first-run-feature-search").checked,
      weather_enabled: Boolean(city),
      weather_alert_enabled: $("#first-run-feature-weather").checked,
      qq_enabled: qqEnabled,
    };
    if (city) values.weather_location = city;
    await api("/api/settings", { method: "PUT", body: JSON.stringify(values) });
    if (qqEnabled) {
      await api("/api/qq/identity", {
        method: "PUT",
        body: JSON.stringify({ owner_qq_id: $("#first-run-owner-qq").value.trim(), bot_qq_id: $("#first-run-bot-qq").value.trim() }),
      });
    }
    await api("/api/settings", { method: "PUT", body: JSON.stringify({ setup_complete: true }) });
    const verified = await api("/api/bootstrap", { timeoutMs: 20000 });
    if (!verified.settings?.setup_complete) throw new Error("配置保存状态未确认，请重试");
    window.location.replace("/");
  } catch (error) {
    $("#first-run-finish-status").hidden = true;
    toast(`配置未完成：${error.message}`, "error");
    state.busy = false;
    finish.disabled = false;
    $("#first-run-back").disabled = false;
  }
}

function skipModel(kind) {
  state[`${kind}Test`] = null;
  state[`${kind}Skipped`] = true;
  setTestStatus(
    kind,
    "skipped",
    "已选择稍后配置",
    kind === "language" ? "进入应用后可在“模型与 API”中连接语言模型" : "进入应用后可随时添加视觉模型",
  );
  setStep(kind === "language" ? 3 : 4);
}

function bindEvents() {
  $("#retry-bootstrap").addEventListener("click", () => void loadSetup(true));
  $("#first-run-form").addEventListener("submit", (event) => {
    completeSetup(event).catch((error) => toast(error.message, "error"));
  });
  $("#first-run-next").addEventListener("click", () => {
    try {
      validateStep(state.step);
      setStep(state.step + 1);
    } catch (error) {
      toast(error.message, "error");
    }
  });
  $("#first-run-back").addEventListener("click", () => setStep(state.step - 1));
  $("#first-run-refresh-environment").addEventListener("click", () => void refreshEnvironment());
  $("#first-run-install-missing").addEventListener("click", (event) => {
    const keys = String(event.currentTarget.dataset.environmentKeys || "").split(",").filter(Boolean);
    void installEnvironmentDependencies(keys);
  });
  $("#first-run-environment-list").addEventListener("click", handleEnvironmentAction);
  $("#first-run-language-discover").addEventListener("click", () => discoverModels("language").catch((error) => toast(error.message, "error")));
  $("#first-run-vision-discover").addEventListener("click", () => discoverModels("vision").catch((error) => toast(error.message, "error")));
  $("#first-run-language-test").addEventListener("click", () => testModel("language").catch((error) => toast(error.message, "error")));
  $("#first-run-vision-test").addEventListener("click", () => testModel("vision").catch((error) => toast(error.message, "error")));
  $("#first-run-language-skip").addEventListener("click", () => skipModel("language"));
  $("#first-run-vision-skip").addEventListener("click", () => skipModel("vision"));
  $$('[data-first-run-vision-mode]').forEach((button) => button.addEventListener("click", () => setVisionMode(button.dataset.firstRunVisionMode)));
  $("#first-run-vision-enabled").addEventListener("change", syncVisionEnabled);
  $("#first-run-feature-qq").addEventListener("change", syncQqEnabled);
  $("#first-run-assistant-name").addEventListener("input", (event) => {
    applyAssistantIdentity(event.currentTarget.value);
    if (state.step === 6) renderSummary();
  });
  ["first-run-language-base-url", "first-run-language-api-key", "first-run-language-model"].forEach((id) => {
    $("#" + id).addEventListener("input", () => invalidateModelTest("language"));
  });
  ["first-run-vision-base-url", "first-run-vision-api-key", "first-run-vision-model"].forEach((id) => {
    $("#" + id).addEventListener("input", () => invalidateModelTest("vision"));
  });
  $$(".secret-toggle").forEach((button) => button.addEventListener("click", () => {
    const input = document.getElementById(button.dataset.secretTarget);
    const showing = input.type === "text";
    input.type = showing ? "password" : "text";
    button.title = showing ? "显示密钥" : "隐藏密钥";
    button.setAttribute("aria-label", showing ? "显示密钥" : "隐藏密钥");
    button.innerHTML = `<i data-lucide="${showing ? "eye" : "eye-off"}"></i>`;
    iconRefresh();
  }));
}

async function loadSetup(showFailure = false) {
  const retry = $("#retry-bootstrap");
  retry.disabled = true;
  try {
    const data = await api("/api/bootstrap", { timeoutMs: 20000 });
    if (data.settings?.setup_complete) {
      window.location.replace("/");
      return;
    }
    state.bootstrap = data;
    hideBootstrapFailure();
    fillSetup(data.settings || {});
  } catch (error) {
    if (showFailure) showBootstrapFailure(error);
    else showBootstrapFailure(error);
  } finally {
    retry.disabled = false;
  }
}

function init() {
  applySetupTheme();
  bindEvents();
  iconRefresh();
  void loadSetup(true);
}

window.addEventListener("pywebviewready", () => {
  renderEnvironment();
  void refreshEnvironment();
}, { once: true });

init();
