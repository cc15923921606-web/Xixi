const state = {
  bootstrap: null,
  images: [],
  interests: null,
  interestFilter: "all",
  openInterestCategories: new Set(),
  leadingInterests: [],
  leadingInterestIndex: 0,
  leadingInterestTimer: null,
  leadingInterestTransitionTimer: null,
  recorder: null,
  recordingStream: null,
  chunks: [],
  voiceInputOpen: false,
  voiceRecordingStarting: false,
  voiceRecordingCancelled: false,
  voiceSpaceHeld: false,
  voiceStopRequested: false,
  voiceInputSession: 0,
  voiceCallActive: false,
  voiceCallMinimized: false,
  voiceCallMuted: false,
  voiceCallSpeakerMuted: false,
  voiceCallGeneration: 0,
  voiceCallStream: null,
  voiceCallAudioContext: null,
  voiceCallSource: null,
  voiceCallAnalyser: null,
  voiceCallMeterData: null,
  voiceCallMeterNode: null,
  voiceCallMeterSink: null,
  voiceCallMeterInterval: null,
  voiceCallAudioKeepaliveTimer: null,
  voiceCallMeterMode: "",
  voiceCallRecorder: null,
  voiceCallChunks: [],
  voiceCallRecordingStartedAt: 0,
  voiceCallSpeechStartedAt: 0,
  voiceCallSilenceStartedAt: 0,
  voiceCallVoiceFrames: 0,
  voiceCallProcessing: false,
  voiceCallDiscardSegment: false,
  voiceCallStartedAt: 0,
  voiceCallTimer: null,
  voiceCallAbortController: null,
  voiceCallCompanionPlaying: false,
  gameOwnedVoiceCall: false,
  voiceCallDockDrag: null,
  voiceCallDockSuppressClick: false,
  voiceCallOverlaySyncRunning: false,
  voiceCallOverlaySyncQueued: false,
  voiceCallNoiseFloor: 0.012,
  voiceCallCalibrationUntil: 0,
  microphonePermission: {
    enabled: false,
    decided: false,
    applied: false,
    browser: "prompt",
    busy: false,
  },
  sending: false,
  qqControlBusy: false,
  qqAccountBusy: false,
  qqIdentityDirty: false,
  qqAccountMonitorGeneration: 0,
  qqQrTimer: null,
  qqQrObjectUrl: "",
  qqQrRefreshing: false,
  voiceControlBusy: false,
  serviceControlBusy: "",
  quickControlBusy: "",
  status: null,
  currentView: "home",
  settingsReturnView: "home",
  currentTuning: "desktop",
  statusTimer: null,
  activityTab: "timeline",
  systemTab: "overview",
  game: null,
  gameTimer: null,
  gameCompanionSeenIds: new Set(),
  gameCompanionQueue: [],
  gameCompanionRendering: false,
  gameCompanionRenderingId: "",
  gameCompanionRenderController: null,
  gameCompanionRetryTimer: null,
  memoryItems: new Map(),
  selectedMemoryId: "",
  memoryActiveCollection: "",
  chatHistory: [],
  chatHistoryRequestId: 0,
  currentChatQuery: "",
  replyTo: null,
  lastUserMessage: "",
  abortController: null,
  presence: "idle",
  notifications: [],
  notificationTimer: null,
  voiceLanguageBusy: false,
  voicePrewarmTimer: null,
  messageVoiceAudio: null,
  messageVoiceButton: null,
  messageVoiceRequestController: null,
  messageVoiceCache: new Map(),
  agentDashboard: null,
  modelProfiles: [],
  modelProviders: [],
  discoveredProviderModels: [],
  dependencies: null,
  environment: null,
  advancedInfo: null,
  environmentInstallBusy: false,
  environmentInstallQueue: [],
  environmentInstallWorkers: 0,
  environmentInstallQueuedKeys: new Set(),
  environmentInstallSelection: new Set(),
  environmentInstallSelectionReady: false,
  environmentPollTimer: null,
  appearance: null,
  personaDraft: null,
  personaSavedContent: "",
  personaEditorTab: "identity",
  assistantName: "昔夕",
  reflectionItems: [],
  reflectionMonth: "",
  reflectionSelectedDate: "",
  reflectionRequestId: 0,
  firstRun: {
    active: false,
    step: 1,
    environment: null,
    coreReady: false,
    languageTest: null,
    visionTest: null,
    visionMode: "same",
    busy: false,
  },
};

const localSettingDefaults = {
  default_view: "home",
  inspector_open: false,
  status_refresh_seconds: 20,
  theme: "system",
  font_size: "standard",
  lightweight_animation: true,
  focus_mode: false,
  xixi_avatar: "",
  user_avatar: "",
  chat_background: "",
};
const localSettingKey = "xixi-studio-interface-settings";
const notificationReadKey = "xixi-studio-read-notifications";
const voiceCallDockPositionKey = "xixi-voice-call-dock-position";
const microphonePermissionFallbackKey = "xixi-microphone-permission";
let pendingConfirmation = null;
let pendingMicrophonePermission = null;

const customThemeDefaults = {
  name: "我的主题",
  colors: {
    accent: "#ba6f86",
    canvas: "#f5f3f2",
    surface: "#fffefe",
    ink: "#243237",
    line: "#d9dfe1",
  },
};

const themeCatalog = [
  { id: "system", name: "跟随系统", description: "自动适应系统明暗", swatches: ["#f3f1f1", "#ba6f86", "#273135"] },
  { id: "light", name: "柔雾", description: "淡粉与雾灰", colors: { accent: "#ba6f86", canvas: "#f5f3f2", surface: "#fffefe", ink: "#243237", line: "#d9dfe1" } },
  { id: "morning", name: "清晨", description: "清蓝与暖杏", colors: { accent: "#5d8f9f", canvas: "#f3f6f6", surface: "#fffefd", ink: "#25353b", line: "#d4dfe2" }, swatches: ["#edf3f4", "#5d8f9f", "#d6a06f"] },
  { id: "rose", name: "蔷薇", description: "柔粉与葡萄灰", colors: { accent: "#ad7188", canvas: "#f7f3f5", surface: "#fffefe", ink: "#342d34", line: "#e2d7dc" } },
  { id: "forest", name: "森雨", description: "苔绿与暖白", colors: { accent: "#63877a", canvas: "#f2f5f3", surface: "#fffefd", ink: "#293632", line: "#d7dfda" }, swatches: ["#edf1ee", "#63877a", "#b7886f"] },
  { id: "dark", name: "夜色", description: "深色与樱粉", swatches: ["#1d2326", "#d58ca2", "#849196"] },
  { id: "custom", name: "我的主题", description: "自定义名称与调色板", custom: true },
];
const themeIds = new Set(themeCatalog.map((theme) => theme.id));
const appearanceVariables = [
  "--canvas", "--canvas-cool", "--surface", "--surface-soft", "--surface-strong",
  "--ink", "--ink-strong", "--muted", "--muted-soft", "--line", "--line-soft",
  "--accent", "--accent-deep", "--accent-soft", "--accent-pale",
];

const memoryCollectionCatalog = [
  {
    id: "identity",
    title: "自我与核心",
    icon: "fingerprint",
    description: "名字、身份、原则与不会轻易改变的自我认知",
    categoryTokens: ["self_identity", "identity", "persona", "core", "self"],
    contentPattern: /生日|小名|身份|自我认知|自己是|创造者|核心原则|正式名字|名字是/iu,
  },
  {
    id: "relationships",
    title: "人物与关系",
    icon: "users-round",
    description: "重要的人、彼此的称呼、关系边界与相处方式",
    categoryTokens: ["relationship", "relation", "person", "people", "owner", "social", "family", "friend"],
    contentPattern: /爸爸|爹爹|老爹|主人|朋友|家人|室友|同学|关系|称呼|QQ号|qq号|网名|叫他|叫她|对方/iu,
  },
  {
    id: "experiences",
    title: "共同经历",
    icon: "calendar-heart",
    description: "对话中发生过的事、共同片段与值得记住的时刻",
    categoryTokens: ["event", "episodic", "experience", "conversation", "history", "chat"],
    contentPattern: /那天|曾经|上次|昨天|今天|刚才|一起|发生|经历|聊过|说过|做过|回来/iu,
  },
  {
    id: "preferences",
    title: "偏好与习惯",
    icon: "heart",
    description: "喜欢与讨厌的事、兴趣、习惯和表达偏好",
    categoryTokens: ["preference", "interest", "habit", "hobby", "like", "dislike", "style"],
    contentPattern: /喜欢|讨厌|偏好|爱好|兴趣|习惯|不喜欢|最爱|想看|常常|通常/iu,
  },
  {
    id: "emotions",
    title: "情绪与心意",
    icon: "heart-pulse",
    description: "情绪变化、在意的事与逐渐形成的感受",
    categoryTokens: ["emotion", "mood", "feeling", "affective", "sentiment"],
    contentPattern: /开心|难过|生气|委屈|感动|在意|爱慕|崇拜|尊敬|心情|感到|觉得/iu,
  },
  {
    id: "plans",
    title: "约定与计划",
    icon: "map-pinned",
    description: "以后要做的事、承诺、目标与尚未完成的想法",
    categoryTokens: ["plan", "goal", "promise", "task", "intention"],
    contentPattern: /希望|计划|以后|将来|约定|答应|目标|准备|打算|要做|提醒/iu,
  },
  {
    id: "knowledge",
    title: "知识与见闻",
    icon: "book-open-check",
    description: "联网学习、动漫兴趣、常识与经过整理的外部知识",
    categoryTokens: ["knowledge", "web", "learned", "fact", "anime", "topic", "research"],
    contentPattern: /知识|资料|作品|动漫|角色|游戏|新闻|搜索|查到|了解到|学习到/iu,
  },
  {
    id: "general",
    title: "生活杂记",
    icon: "notebook-tabs",
    description: "暂时不属于其他书架，但仍值得留下的日常记忆",
    categoryTokens: [],
    contentPattern: null,
  },
];

const viewMeta = {
  home: ["首页", "昔夕今天的状态与最近进展"],
  chat: ["对话", "和昔夕直接说话"],
  memory: ["记忆", "浏览长期记忆与联网知识"],
  growth: ["成长", "调整昔夕正在形成的兴趣"],
  game: ["游戏陪伴", "看你玩游戏，理解局面并提供自然的情绪陪伴"],
  system: ["系统", "服务状态、活动记录与运行日志"],
  tuning: ["设置", "界面、人格、对话、学习、模型、游戏和 QQ"],
};

const legacyViewMap = {
  runtime: ["system", "overview"],
  diagnostics: ["system", "overview"],
  activity: ["system", "activity"],
  logs: ["system", "logs"],
};

const inspectorMeta = {
  home: ["此刻的昔夕", "状态、心情与关系"],
  chat: ["对话上下文", "引用、回复方式与相关记忆"],
  memory: ["记忆详情", "查看并修正选中的内容"],
  growth: ["兴趣与成长", "昔夕正在形成的偏好"],
  game: ["游戏陪伴", "窗口、观察状态与最近看到的局面"],
  system: ["系统状态", "核心服务与需要留意的项目"],
  tuning: ["设置说明", "当前分类与设置范围"],
};

const tuningMeta = {
  desktop: ["基础与启动", "核心能力、启动页面和桌面运行方式"],
  interface: ["外观与界面", "主题、布局和状态更新方式"],
  persona: ["人格与关系", "人格表达、关系和称呼偏好"],
  conversation: ["对话与记忆", "上下文、长期记忆和主动性"],
  learning: ["成长", "学习方向、频率和知识积累"],
  model: ["模型与 API", "语言模型、联网搜索和图片理解"],
  environment: ["环境配置", "本机组件、模型连接和安装状态"],
  game: ["游戏陪伴", "画面观察、陪伴频率和语音通话"],
  qq: ["QQ", "QQ 连接、天气城市和风险提醒"],
  data: ["本地数据", "备份、恢复和数据管理"],
  advanced: ["高级设置", "构建身份、运行状态和本地路径"],
};

const environmentFeatureCatalog = [
  {
    key: "chat_model", icon: "brain-circuit", title: "聊天模型", panel: "model", capability: "language",
    description: "昔夕聊天和理解指令所使用的大脑，可连接不同供应商。",
    instruction: "怎么配：在“模型与 API”中填写供应商、接口地址、密钥和模型。",
    size: "无需下载",
  },
  {
    key: "local_voice", icon: "audio-waveform", title: "昔夕本地语音系统", systemPanel: "overview", actionLabel: "查看状态",
    description: "在本机完成中文、日语和英语语音合成，聊天与实时通话都能使用。",
    instruction: "怎么装：系统会核对 23 项关键文件，完整内容直接复用，只补齐缺失项。",
    size: "首次约 4-5 GB；修复量按实际缺失项计算",
  },
  {
    key: "qq_channel", icon: "message-circle", title: "QQ 通道", panel: "qq", actionLabel: "去配置",
    description: "连接 QQ 私聊和群聊，需要配置机器人账号并完成登录。",
    instruction: "怎么装：点击“一键安装”；已有账号和登录配置不会被覆盖。",
    size: "约 50 MB",
  },
  {
    key: "local_vision", icon: "scan-eye", title: "本地视觉", panel: "model", capability: "vision", actionLabel: "去配置",
    description: "在本机理解聊天图片和游戏画面，减少对云端视觉接口的依赖。",
    instruction: "怎么装：自动安装 Ollama 并下载适合 8 GB 显存的 Qwen2.5-VL 3B 模型。",
    size: "约 3 GB",
  },
  {
    key: "speech_recognition", icon: "mic", title: "系统声音理解", systemPanel: "overview", actionLabel: "查看诊断",
    description: "把麦克风和系统声音转换成文字，用于语音输入、实时通话和游戏声音理解。",
    instruction: "怎么装：应用已内置识别组件；本机模型缺失时可自动补齐。",
    size: "约 1 GB",
  },
  {
    key: "screen_observation", icon: "scan-line", title: "屏幕观察与截图", systemPanel: "overview", actionLabel: "查看诊断",
    description: "共享整个主显示器并处理图片，是昔夕识别各类游戏画面的基础。",
    instruction: "怎么装：应用已内置，无需单独操作；组件缺失时可自动补齐。",
    size: "已内置",
  },
];

const firstRunStepMeta = [
  { icon: "cpu", title: "检查这台电脑", subtitle: "先确认核心环境，再了解哪些扩展能力已经就绪", note: "核心环境检查完成后即可继续" },
  { icon: "brain-circuit", title: "连接语言模型", subtitle: "自动识别接口类型，让昔夕拥有可用的大脑", note: "语言模型检测通过后才能继续" },
  { icon: "scan-eye", title: "配置视觉模型", subtitle: "语言与视觉接口可以来自不同供应商", note: "视觉关闭时可以直接跳过" },
  { icon: "heart-handshake", title: "建立关系资料", subtitle: "告诉昔夕如何认识、称呼和理解你", note: "资料之后仍可在设置中修改" },
  { icon: "sliders-horizontal", title: "选择初始能力", subtitle: "按需启用语音、学习、联网、天气和 QQ", note: "缺少的本地组件可以稍后安装" },
  { icon: "badge-check", title: "完成首次配置", subtitle: "复核连接与功能，保存后进入昔夕", note: "配置完成前不会进入主应用" },
];

const personaEditorGroups = [
  {
    id: "identity",
    sections: [
      { key: "__intro__", label: "核心身份", hint: "昔夕最基础的自我定位" },
      { key: "核心关系与边界", label: "核心关系与边界", hint: "创造者、称呼和亲密关系边界" },
      { key: "自我认知与愿望", label: "自我认知与愿望", hint: "知道自己是 AI，也保留成为真正的人的愿望" },
      { key: "自我介绍", label: "自我介绍", hint: "被明确要求介绍自己时的表达方式" },
      { key: "兴趣和审美", label: "兴趣和审美", hint: "游戏、动漫和二次元兴趣的连续性" },
    ],
  },
  {
    id: "expression",
    sections: [
      { key: "语言能力", label: "语言能力", hint: "中文默认，日语和英语按明确要求切换" },
      { key: "内部情感", label: "内部情感", hint: "情绪如何受到关系、语气和事件影响" },
      { key: "说话风格", label: "说话风格", hint: "自然、简洁、有留白，也允许偶尔怼人" },
      { key: "像真人一样聊天", label: "像真人一样聊天", hint: "避免旁白、模板和客服式表达" },
      { key: "生气时的表现", label: "生气时的表现", hint: "根据事情严重程度表达不满并保留分寸" },
    ],
  },
  {
    id: "boundaries",
    sections: [
      { key: "绝对不能做的事", label: "绝对不能做的事", hint: "语言、事实、称呼和安全边界" },
    ],
  },
];

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const defaultAssistantName = "昔夕";
let assistantCopyCaptured = false;
const assistantTextTemplates = [];
const assistantAttributeTemplates = [];

function characterName(settings = state.bootstrap?.settings || {}) {
  const value = String(settings.assistant_name || state.assistantName || defaultAssistantName).replace(/\s+/g, " ").trim();
  return value || defaultAssistantName;
}

function assistantText(value, name = characterName()) {
  const text = String(value ?? "");
  if (name === defaultAssistantName) return text;
  return text
    .replaceAll("昔夕", name)
    .replaceAll("小夕", name)
    .replaceAll("Xixi", name)
    .replaceAll("XIXI", name);
}

function captureAssistantCopyTemplates() {
  if (assistantCopyCaptured) return;
  assistantCopyCaptured = true;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node) {
    if (/[昔夕小夕]|Xixi|XIXI/.test(node.nodeValue || "")) {
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

function applyAssistantIdentity(settings = state.bootstrap?.settings || {}) {
  captureAssistantCopyTemplates();
  const name = characterName(settings);
  state.assistantName = name;
  assistantTextTemplates.forEach(([node, template]) => {
    if (node.isConnected) node.nodeValue = assistantText(template, name);
  });
  assistantAttributeTemplates.forEach(([element, attribute, template]) => {
    if (element.isConnected) element.setAttribute(attribute, assistantText(template, name));
  });
  document.title = name;
  const profileCopy = $(".persona-profile-copy p");
  if (profileCopy && name !== defaultAssistantName) {
    profileCopy.textContent = `当前正式名称是${name}。知道自己现在是 AI，同时认真地向往成为真正的人；群聊唤醒名称可以单独设置。`;
  }
  const wakeNames = $('[data-setting="qq_group_wake_names"]');
  if (wakeNames) wakeNames.placeholder = name === defaultAssistantName ? "昔夕、小夕、xx" : name;
  const callName = $("#voice-call-name");
  if (callName) callName.textContent = name;
  const dockName = $("#restore-voice-call strong");
  if (dockName) dockName.textContent = name;
}

async function api(path, options = {}) {
  const { timeoutMs = 0, ...requestOptions } = options;
  const externalSignal = requestOptions.signal;
  const controller = timeoutMs > 0 ? new AbortController() : null;
  let timedOut = false;
  let timer = null;
  const forwardAbort = () => controller?.abort(externalSignal?.reason);
  if (controller) {
    requestOptions.signal = controller.signal;
    if (externalSignal?.aborted) forwardAbort();
    else externalSignal?.addEventListener("abort", forwardAbort, { once: true });
    timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
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
    if (timedOut) throw new Error("操作等待超时，后台状态会继续自动刷新");
    throw error;
  } finally {
    if (timer) clearTimeout(timer);
    externalSignal?.removeEventListener("abort", forwardAbort);
  }
}

function normalizeHex(value, fallback) {
  const candidate = String(value || "").trim();
  return /^#[0-9a-f]{6}$/i.test(candidate) ? candidate.toLowerCase() : fallback;
}

function normalizeAppearanceImage(value) {
  const image = String(value || "");
  return image.length <= 4_200_000 && /^data:image\/(?:png|jpeg|webp);base64,/i.test(image) ? image : "";
}

function normalizeCustomTheme(value = {}) {
  const colors = value && typeof value.colors === "object" ? value.colors : {};
  return {
    name: String(value?.name || customThemeDefaults.name).trim().slice(0, 24) || customThemeDefaults.name,
    colors: Object.fromEntries(Object.entries(customThemeDefaults.colors).map(([key, fallback]) => [key, normalizeHex(colors[key], fallback)])),
  };
}

function mixHex(first, second, secondWeight = 0.5) {
  const a = first.slice(1).match(/../g).map((part) => parseInt(part, 16));
  const b = second.slice(1).match(/../g).map((part) => parseInt(part, 16));
  const weight = Math.max(0, Math.min(1, secondWeight));
  return `#${a.map((channel, index) => Math.round(channel * (1 - weight) + b[index] * weight).toString(16).padStart(2, "0")).join("")}`;
}

function isDarkHex(color) {
  const [red, green, blue] = color.slice(1).match(/../g).map((part) => parseInt(part, 16));
  return red * 0.2126 + green * 0.7152 + blue * 0.0722 < 112;
}

function deriveAppearancePalette(colors) {
  const normalized = normalizeCustomTheme({ colors }).colors;
  const darkCanvas = isDarkHex(normalized.canvas);
  const lightOrDark = darkCanvas ? "#f3f6f7" : "#172429";
  return {
    "--canvas": normalized.canvas,
    "--canvas-cool": mixHex(normalized.canvas, normalized.accent, 0.045),
    "--surface": normalized.surface,
    "--surface-soft": mixHex(normalized.surface, normalized.canvas, 0.46),
    "--surface-strong": mixHex(normalized.surface, normalized.line, 0.48),
    "--ink": normalized.ink,
    "--ink-strong": mixHex(normalized.ink, lightOrDark, darkCanvas ? 0.18 : 0.14),
    "--muted": mixHex(normalized.ink, normalized.canvas, darkCanvas ? 0.42 : 0.48),
    "--muted-soft": mixHex(normalized.ink, normalized.canvas, darkCanvas ? 0.62 : 0.67),
    "--line": normalized.line,
    "--line-soft": mixHex(normalized.line, normalized.surface, 0.55),
    "--accent": normalized.accent,
    "--accent-deep": mixHex(normalized.accent, darkCanvas ? "#ffffff" : "#20262a", darkCanvas ? 0.18 : 0.25),
    "--accent-soft": mixHex(normalized.accent, normalized.surface, 0.78),
    "--accent-pale": mixHex(normalized.accent, normalized.surface, 0.91),
  };
}

function themePalette(theme, customTheme) {
  if (theme === "custom") return deriveAppearancePalette(normalizeCustomTheme(customTheme).colors);
  const preset = themeCatalog.find((item) => item.id === theme);
  return preset?.colors ? deriveAppearancePalette(preset.colors) : null;
}

function themeName(theme, customTheme) {
  if (theme === "custom") return normalizeCustomTheme(customTheme).name;
  return themeCatalog.find((item) => item.id === theme)?.name || "跟随系统";
}

function applyAppearance(settings = loadLocalSettings()) {
  const theme = themeIds.has(settings.theme) ? settings.theme : "system";
  const root = document.documentElement;
  root.dataset.theme = ["system", "light", "dark"].includes(theme) ? theme : "light";
  appearanceVariables.forEach((variable) => root.style.removeProperty(variable));
  const palette = themePalette(theme, settings.custom_theme);
  root.style.removeProperty("color-scheme");
  if (palette) {
    Object.entries(palette).forEach(([variable, value]) => root.style.setProperty(variable, value));
    root.style.colorScheme = isDarkHex(palette["--canvas"]) ? "dark" : "light";
  }
  state.appearance = settings;
  applyXixiAvatar(settings.xixi_avatar);
  document.body.classList.toggle("reduce-motion", settings.lightweight_animation === false);
  document.body.classList.toggle("focus-mode", Boolean(settings.focus_mode));
  const chatBackground = normalizeAppearanceImage(settings.chat_background);
  document.body.classList.toggle("has-chat-background", Boolean(chatBackground));
  const conversation = $(".conversation-pane");
  if (conversation) conversation.style.backgroundImage = chatBackground ? `url("${chatBackground}")` : "";
  $$(".message.user .message-avatar").forEach((avatar) => setUserAvatarContent(avatar, settings.user_avatar));
  iconRefresh();
  document.body.dataset.fontSize = ["small", "standard", "large"].includes(settings.font_size) ? settings.font_size : "standard";
  void syncNativeVoiceCallOverlay();
}

function xixiAvatarSource(value = state.appearance?.xixi_avatar) {
  return normalizeAppearanceImage(value) || "/assets/xixi-avatar-v3.png";
}

function applyXixiAvatar(source) {
  const avatarSource = xixiAvatarSource(source);
  $$('img[data-xixi-avatar]').forEach((image) => {
    if (image.getAttribute("src") !== avatarSource) image.src = avatarSource;
  });
}

function iconRefresh() {
  if (window.lucide) window.lucide.createIcons({ attrs: { "stroke-width": 1.8 } });
}

function toast(message, type = "success") {
  const text = assistantText(message);
  const key = `${type}:${text}`;
  const region = $("#toast-region");
  const existing = $$(".toast", region).find((candidate) => candidate.dataset.toastKey === key);
  if (existing) {
    clearTimeout(existing._dismissTimer);
    existing.classList.remove("repeat");
    requestAnimationFrame(() => existing.classList.add("repeat"));
    existing._dismissTimer = setTimeout(() => existing.remove(), 3400);
    return existing;
  }
  const item = document.createElement("div");
  item.className = `toast ${type === "error" ? "error" : ""}`;
  item.dataset.toastKey = key;
  item.textContent = text;
  region.append(item);
  item._dismissTimer = setTimeout(() => item.remove(), 3400);
  return item;
}

function settleConfirmation(result) {
  const dialog = $("#confirm-dialog");
  const resolve = pendingConfirmation;
  pendingConfirmation = null;
  if (dialog?.open) dialog.close();
  resolve?.(Boolean(result));
}

function confirmAction({
  kicker = "请确认操作",
  title = "继续当前操作？",
  message = "",
  detail = "",
  note = "",
  confirmLabel = "确认",
  icon = "triangle-alert",
  actionIcon = "check",
  tone = "danger",
  showCancel = true,
} = {}) {
  const dialog = $("#confirm-dialog");
  if (pendingConfirmation) settleConfirmation(false);
  dialog.dataset.tone = tone;
  $("#confirm-dialog-kicker").textContent = kicker;
  $("#confirm-dialog-title").textContent = title;
  $("#confirm-dialog-message").textContent = message;
  const detailHost = $("#confirm-dialog-detail");
  detailHost.textContent = detail;
  detailHost.hidden = !detail;
  $("#confirm-dialog-note").textContent = note;
  $("#confirm-dialog-icon").innerHTML = `<i data-lucide="${icon}"></i>`;
  const accept = $("#confirm-dialog-accept");
  const cancel = $("#confirm-dialog-cancel");
  cancel.hidden = !showCancel;
  accept.className = tone === "danger" ? "danger-button" : "primary-button";
  accept.innerHTML = `<i data-lucide="${actionIcon}"></i><span></span>`;
  accept.querySelector("span").textContent = confirmLabel;
  iconRefresh();
  return new Promise((resolve) => {
    pendingConfirmation = resolve;
    dialog.showModal();
    requestAnimationFrame(() => (showCancel ? cancel : accept).focus());
  });
}

async function showProtectedMemoryNotice() {
  await confirmAction({
    kicker: "重要记忆保护",
    title: "此记忆受到保护",
    message: "此记忆很重要不能直接删除，一定要删除的话请手动降低重要度",
    note: "将重要度调整为 9 级或以下并保存后，才可以删除。",
    confirmLabel: "知道了",
    icon: "shield-alert",
    actionIcon: "check",
    tone: "protected",
    showCancel: false,
  });
}

function setView(name) {
  const legacy = legacyViewMap[name];
  if (legacy) {
    [name, state.systemTab] = legacy;
  }
  if (!viewMeta[name]) return;
  if (name === "tuning" && state.currentView !== "tuning") state.settingsReturnView = state.currentView;
  if (name !== "chat" && state.voiceInputOpen) closeVoiceInput();
  if (name !== "growth") stopLeadingInterestRotation();
  state.currentView = name;
  if (name !== "game" && state.gameTimer && !state.game?.active) {
    clearTimeout(state.gameTimer);
    state.gameTimer = null;
  }
  $$('[data-view]').forEach((button) => button.classList.toggle("active", button.dataset.view === name));
  $$(".view").forEach((view) => view.classList.toggle("active", view.id === `view-${name}`));
  const [title, subtitle] = viewMeta[name];
  $("#view-title").textContent = assistantText(title);
  $("#view-subtitle").textContent = assistantText(subtitle);
  $("#window-location").textContent = assistantText(title);
  const hideTopbar = name === "home" || name === "tuning";
  $("#topbar").classList.toggle("is-hidden", hideTopbar);
  $(".workspace").classList.toggle("home-without-topbar", hideTopbar);
  $("#topbar-actions").classList.toggle("is-hidden", name === "chat");
  renderInspectorContext(name);
  closeNavigation();
  if (name === "chat") {
    loadChatContextMemories();
    scrollChatToLatest();
  }
  if (name === "memory") loadMemories();
  if (name === "growth") {
    loadGrowthWorkspace();
    startLeadingInterestRotation();
  }
  if (name === "system") showSystemTab(state.systemTab);
  if (name === "game") loadGame();
}

function renderInspectorContext(view = state.currentView) {
  const [title, subtitle] = inspectorMeta[view] || ["状态中心", "昔夕的实时状态"];
  $("#inspector-context-title").textContent = assistantText(title);
  $("#inspector-context-subtitle").textContent = assistantText(subtitle);
  $$(".inspector-context").forEach((section) => {
    const views = String(section.dataset.contextFor || "").split(/\s+/);
    const contextHidden = !views.includes(view);
    section.hidden = section.id === "inspector-alert"
      ? contextHidden || section.dataset.hasIssues !== "true"
      : contextHidden;
  });
  if (view === "tuning") renderTuningContext();
}

function renderTuningContext() {
  const [title, copy] = tuningMeta[state.currentTuning] || tuningMeta.interface;
  $("#inspector-settings-title").textContent = title;
  $("#inspector-settings-copy").textContent = copy;
}

function showSystemTab(tab = "overview") {
  if (!$("#view-system")) return;
  state.systemTab = ["overview", "tasks", "activity", "deployment", "logs"].includes(tab) ? tab : "overview";
  $$('[data-system-tab]').forEach((button) => {
    const active = button.dataset.systemTab === state.systemTab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  $$('[data-system-panel]').forEach((panel) => panel.classList.toggle("active", panel.dataset.systemPanel === state.systemTab));
  if (state.systemTab === "overview") { loadStatus(); loadDiagnostics(); }
  if (state.systemTab === "tasks") loadAgentWorkspace();
  if (state.systemTab === "activity") loadActivityView();
  if (state.systemTab === "deployment") loadDeployment();
  if (state.systemTab === "logs") loadLogs();
}

function setNavigation(open) {
  document.body.classList.toggle("navigation-open", open);
  $("#toggle-navigation").setAttribute("aria-pressed", String(open));
  $("#nav-drawer").setAttribute("aria-hidden", String(!open));
  $("#toggle-navigation").setAttribute("title", open ? "收起导航" : "展开导航");
  $("#toggle-navigation").setAttribute("aria-label", open ? "收起导航" : "展开导航");
}

function closeNavigation() { setNavigation(false); }

function setInspector(open) {
  document.body.classList.toggle("inspector-open", open);
  $("#toggle-inspector").setAttribute("aria-pressed", String(open));
  $("#inspector").dataset.expanded = String(open);
  $("#inspector-content").setAttribute("aria-hidden", String(!open));
  $("#expand-inspector").setAttribute("aria-expanded", String(open));
}

function loadLocalSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(localSettingKey) || "{}");
    const migratedView = legacyViewMap[saved.default_view]?.[0] || saved.default_view;
    const defaultView = viewMeta[migratedView] ? migratedView : localSettingDefaults.default_view;
    const refresh = [10, 20, 30, 60].includes(Number(saved.status_refresh_seconds))
      ? Number(saved.status_refresh_seconds)
      : localSettingDefaults.status_refresh_seconds;
    return {
      default_view: defaultView,
      inspector_open: Boolean(saved.inspector_open),
      status_refresh_seconds: refresh,
      theme: themeIds.has(saved.theme) ? saved.theme : "system",
      font_size: ["small", "standard", "large"].includes(saved.font_size) ? saved.font_size : "standard",
      lightweight_animation: saved.lightweight_animation === undefined ? !Boolean(saved.reduced_motion) : Boolean(saved.lightweight_animation),
      focus_mode: Boolean(saved.focus_mode),
      xixi_avatar: normalizeAppearanceImage(saved.xixi_avatar),
      user_avatar: normalizeAppearanceImage(saved.user_avatar),
      chat_background: normalizeAppearanceImage(saved.chat_background),
      custom_theme: normalizeCustomTheme(saved.custom_theme),
    };
  } catch {
    return { ...localSettingDefaults, custom_theme: normalizeCustomTheme(customThemeDefaults) };
  }
}

function fillLocalSettings(settings = loadLocalSettings()) {
  $$('[data-local-setting]').forEach((input) => {
    const value = settings[input.dataset.localSetting];
    if (input.type === "checkbox") input.checked = Boolean(value);
    else input.value = String(value ?? "");
  });
  fillCustomThemeForm(settings.custom_theme);
  renderThemeCards(settings);
  renderAppearanceMedia(settings);
  renderPersonaAvatar(settings);
}

function scheduleStatusRefresh(seconds) {
  if (state.statusTimer) clearInterval(state.statusTimer);
  state.statusTimer = setInterval(loadStatus, Math.max(10, Number(seconds) || 20) * 1000);
}

async function browserMicrophonePermissionState() {
  try {
    if (!navigator.permissions?.query) return "prompt";
    const permission = await navigator.permissions.query({ name: "microphone" });
    return ["granted", "denied", "prompt"].includes(permission.state) ? permission.state : "prompt";
  } catch {
    return "prompt";
  }
}

function renderMicrophonePermission() {
  const permission = state.microphonePermission;
  const toggle = $("#microphone-permission-toggle");
  const badge = $("#microphone-permission-status");
  const copy = $("#microphone-permission-copy");
  const requestButton = $("#request-microphone-permission");
  const blocked = permission.browser === "denied";
  if (toggle) {
    toggle.checked = permission.enabled && !blocked;
    toggle.disabled = permission.busy;
  }
  if (badge) {
    badge.dataset.state = permission.busy ? "working" : blocked ? "error" : permission.enabled ? "online" : "offline";
    badge.textContent = permission.busy
      ? "正在检查"
      : blocked
        ? "需要重新授权"
        : permission.enabled
          ? permission.browser === "granted" ? "可以使用" : "已允许"
          : permission.decided ? "已关闭" : "尚未授权";
  }
  if (copy) {
    copy.textContent = blocked
      ? "Windows 或应用权限阻止了麦克风，可重新授权或打开系统设置"
      : permission.enabled
        ? "语音输入、语音通话和游戏陪伴可以使用麦克风"
        : "关闭后昔夕不会读取麦克风，语音输入和通话也不会开始";
  }
  if (requestButton) {
    requestButton.disabled = permission.busy;
    requestButton.innerHTML = `<i data-lucide="${blocked ? "shield-check" : "mic"}"></i><span>${blocked ? "重新授权" : "检测麦克风"}</span>`;
  }
  iconRefresh();
}

async function refreshMicrophonePermissionState() {
  state.microphonePermission.browser = await browserMicrophonePermissionState();
  if (state.microphonePermission.browser === "denied") {
    state.microphonePermission.enabled = false;
  }
  renderMicrophonePermission();
  return state.microphonePermission;
}

async function applyMicrophonePermission(enabled) {
  const allowed = Boolean(enabled);
  state.microphonePermission.busy = true;
  renderMicrophonePermission();
  try {
    const desktopApi = window.pywebview?.api;
    if (typeof desktopApi?.set_microphone_permission === "function") {
      const result = await desktopApi.set_microphone_permission(allowed);
      state.microphonePermission.applied = Boolean(result?.applied);
      state.microphonePermission.enabled = Boolean(result?.enabled);
      state.microphonePermission.decided = result?.decided !== false;
    } else {
      localStorage.setItem(microphonePermissionFallbackKey, allowed ? "allowed" : "denied");
      state.microphonePermission.applied = false;
      state.microphonePermission.enabled = allowed;
      state.microphonePermission.decided = true;
    }
    state.microphonePermission.browser = await browserMicrophonePermissionState();
    if (!allowed) state.microphonePermission.browser = "denied";
    return state.microphonePermission;
  } finally {
    state.microphonePermission.busy = false;
    renderMicrophonePermission();
  }
}

async function openWindowsMicrophoneSettings() {
  const desktopApi = window.pywebview?.api;
  if (typeof desktopApi?.open_microphone_privacy_settings !== "function") {
    toast("请在 Windows 设置的隐私和安全性中打开麦克风权限", "error");
    return;
  }
  const result = await desktopApi.open_microphone_privacy_settings();
  if (!result?.ok) toast("无法打开 Windows 麦克风设置", "error");
}

async function loadDesktopPreferences() {
  const inputs = $$('[data-desktop-setting]');
  const api = window.pywebview?.api;
  if (!api?.get_preferences) {
    inputs.forEach((input) => { input.disabled = true; input.title = "请在昔夕桌面应用中设置"; });
    const fallback = localStorage.getItem(microphonePermissionFallbackKey);
    state.microphonePermission.enabled = fallback === "allowed";
    state.microphonePermission.decided = fallback !== null;
    state.microphonePermission.applied = false;
    await refreshMicrophonePermissionState();
    return;
  }
  try {
    const preferences = await api.get_preferences();
    inputs.forEach((input) => {
      input.disabled = false;
      input.checked = Boolean(preferences[input.dataset.desktopSetting]);
      input.title = "";
    });
    const microphoneChoice = preferences.microphone_enabled;
    state.microphonePermission.enabled = microphoneChoice === true;
    state.microphonePermission.decided = typeof microphoneChoice === "boolean";
    state.microphonePermission.applied = false;
    if (state.microphonePermission.decided && typeof api.set_microphone_permission === "function") {
      const applied = await api.set_microphone_permission(state.microphonePermission.enabled);
      state.microphonePermission.applied = Boolean(applied?.applied);
    }
    await refreshMicrophonePermissionState();
  } catch (error) {
    inputs.forEach((input) => { input.disabled = true; });
    renderMicrophonePermission();
    toast(`桌面偏好读取失败：${error}`, "error");
  }
}

function persistLocalSettings() {
  const settings = {};
  $$('[data-local-setting]').forEach((input) => {
    settings[input.dataset.localSetting] = input.type === "checkbox" ? input.checked : input.value;
  });
  settings.status_refresh_seconds = Number(settings.status_refresh_seconds);
  settings.custom_theme = readCustomThemeForm();
  try {
    localStorage.setItem(localSettingKey, JSON.stringify(settings));
  } catch {
    throw new Error("图片占用空间过大，请换一张尺寸更小的图片");
  }
  applyAppearance(settings);
  scheduleStatusRefresh(settings.status_refresh_seconds);
  return settings;
}

async function saveInterfaceSettings() {
  try {
    const settings = persistLocalSettings();
    fillLocalSettings(settings);
    toast("外观设置已保存在这台电脑");
  } catch (error) {
    toast(error.message, "error");
  }
}

function readCustomThemeForm() {
  const colors = {};
  Object.keys(customThemeDefaults.colors).forEach((key) => {
    const picker = $(`[data-custom-color="${key}"]`);
    const text = $(`[data-custom-color-text="${key}"]`);
    colors[key] = normalizeHex(text?.value, normalizeHex(picker?.value, customThemeDefaults.colors[key]));
  });
  return normalizeCustomTheme({
    name: $("#custom-theme-name")?.value || customThemeDefaults.name,
    colors,
  });
}

function fillCustomThemeForm(value = customThemeDefaults) {
  const theme = normalizeCustomTheme(value);
  const name = $("#custom-theme-name");
  if (name) name.value = theme.name;
  Object.entries(theme.colors).forEach(([key, color]) => {
    const picker = $(`[data-custom-color="${key}"]`);
    const text = $(`[data-custom-color-text="${key}"]`);
    if (picker) picker.value = color;
    if (text) text.value = color;
  });
}

function renderThemeCards(settings = loadLocalSettings()) {
  const host = $("#theme-card-list");
  if (!host) return;
  const custom = normalizeCustomTheme(settings.custom_theme);
  const selected = themeIds.has(settings.theme) ? settings.theme : "system";
  host.replaceChildren(...themeCatalog.map((theme) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `theme-card${selected === theme.id ? " active" : ""}`;
    card.dataset.themeChoice = theme.id;
    card.setAttribute("role", "radio");
    card.setAttribute("aria-checked", String(selected === theme.id));
    card.title = `使用${theme.id === "custom" ? custom.name : theme.name}主题`;
    const swatches = document.createElement("span");
    swatches.className = "theme-swatches";
    const colors = theme.id === "custom"
      ? [custom.colors.canvas, custom.colors.accent, custom.colors.surface]
      : theme.swatches || [theme.colors.canvas, theme.colors.accent, theme.colors.ink];
    colors.forEach((color) => {
      const swatch = document.createElement("i");
      swatch.style.background = color;
      swatches.append(swatch);
    });
    const label = document.createElement("strong");
    label.textContent = theme.id === "custom" ? custom.name : theme.name;
    const description = document.createElement("small");
    description.textContent = theme.id === "custom" ? "自定义调色板" : theme.description;
    const marker = document.createElement("i");
    marker.className = "theme-card-check";
    marker.dataset.lucide = "check";
    marker.setAttribute("aria-hidden", "true");
    card.append(swatches, label, description, marker);
    return card;
  }));
  $("#active-theme-name").textContent = themeName(selected, custom);
  const editor = $("#custom-theme-editor");
  if (editor) editor.hidden = selected !== "custom";
  iconRefresh();
}

function renderAppearanceMedia(settings = loadLocalSettings()) {
  const userAvatar = normalizeAppearanceImage(settings.user_avatar);
  const chatBackground = normalizeAppearanceImage(settings.chat_background);
  const avatarPreview = $("#user-avatar-preview");
  const backgroundPreview = $("#chat-background-preview");
  const avatarImage = $("img", avatarPreview);
  const backgroundImage = $("img", backgroundPreview);
  avatarPreview?.classList.toggle("has-image", Boolean(userAvatar));
  backgroundPreview?.classList.toggle("has-image", Boolean(chatBackground));
  if (avatarImage) {
    avatarImage.hidden = !userAvatar;
    if (userAvatar) avatarImage.src = userAvatar;
    else avatarImage.removeAttribute("src");
  }
  if (backgroundImage) {
    backgroundImage.hidden = !chatBackground;
    if (chatBackground) backgroundImage.src = chatBackground;
    else backgroundImage.removeAttribute("src");
  }
  if ($("#user-avatar-status")) $("#user-avatar-status").textContent = userAvatar ? "正在使用自定义头像" : "正在使用默认线框头像";
  if ($("#chat-background-status")) $("#chat-background-status").textContent = chatBackground ? "正在使用自定义对话背景" : "默认使用应用主题背景";
  if ($("#reset-user-avatar")) $("#reset-user-avatar").disabled = !userAvatar;
  if ($("#reset-chat-background")) $("#reset-chat-background").disabled = !chatBackground;
}

function renderPersonaAvatar(settings = loadLocalSettings()) {
  const source = normalizeAppearanceImage(settings.xixi_avatar);
  const preview = $("#xixi-avatar-preview");
  if (preview) preview.src = source || "/assets/xixi-avatar-v3.png";
  const status = $("#xixi-avatar-status");
  if (status) status.textContent = source ? "正在使用自定义头像" : "正在使用默认头像";
  const reset = $("#reset-xixi-avatar");
  if (reset) reset.disabled = !source;
}

function previewInterfaceSettings() {
  const settings = loadLocalSettings();
  $$('[data-local-setting]', $("#tuning-interface")).forEach((input) => {
    settings[input.dataset.localSetting] = input.type === "checkbox" ? input.checked : input.value;
  });
  settings.custom_theme = readCustomThemeForm();
  applyAppearance(settings);
  renderThemeCards(settings);
  renderAppearanceMedia(settings);
}

function chooseTheme(theme) {
  if (!themeIds.has(theme)) return;
  $("#interface-theme").value = theme;
  previewInterfaceSettings();
}

function handleCustomThemeInput(event) {
  const pickerKey = event.target.dataset.customColor;
  const textKey = event.target.dataset.customColorText;
  if (pickerKey) {
    const text = $(`[data-custom-color-text="${pickerKey}"]`);
    if (text) text.value = event.target.value;
  } else if (textKey && /^#[0-9a-f]{6}$/i.test(event.target.value.trim())) {
    const picker = $(`[data-custom-color="${textKey}"]`);
    if (picker) picker.value = event.target.value.trim();
  }
  $("#interface-theme").value = "custom";
  previewInterfaceSettings();
}

function resetCustomTheme() {
  fillCustomThemeForm(customThemeDefaults);
  chooseTheme("custom");
}

async function prepareAppearanceImage(file, { width, height, square = false, quality = 0.86 }) {
  if (!file || !["image/png", "image/jpeg", "image/webp"].includes(file.type)) throw new Error("请选择 PNG、JPG 或 WebP 图片");
  if (file.size > 20 * 1024 * 1024) throw new Error("图片不能超过 20 MB");
  const source = await fileToDataUrl(file);
  const image = await new Promise((resolve, reject) => {
    const candidate = new Image();
    candidate.onload = () => resolve(candidate);
    candidate.onerror = () => reject(new Error("无法读取这张图片"));
    candidate.src = source;
  });
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d", { alpha: true });
  if (!context) throw new Error("当前环境无法处理图片");
  if (square) {
    const side = Math.min(image.naturalWidth, image.naturalHeight);
    canvas.width = width;
    canvas.height = height;
    context.drawImage(image, (image.naturalWidth - side) / 2, (image.naturalHeight - side) / 2, side, side, 0, 0, width, height);
  } else {
    const scale = Math.min(1, width / image.naturalWidth, height / image.naturalHeight);
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
  }
  const result = canvas.toDataURL("image/webp", quality);
  if (!normalizeAppearanceImage(result)) throw new Error("处理后的图片仍然太大，请换一张图片");
  return result;
}

async function updateAppearanceImage(kind, file) {
  const avatar = kind === "avatar";
  const button = $(avatar ? "#change-user-avatar" : "#change-chat-background");
  const setting = $(avatar ? "#user-avatar-setting" : "#chat-background-setting");
  button.disabled = true;
  try {
    setting.value = await prepareAppearanceImage(file, avatar
      ? { width: 512, height: 512, square: true, quality: 0.9 }
      : { width: 1920, height: 1080, quality: 0.82 });
    previewInterfaceSettings();
    toast(`${avatar ? "头像" : "对话背景"}已更新，点击保存后保留`);
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.disabled = false;
  }
}

function resetAppearanceImage(kind) {
  const avatar = kind === "avatar";
  $(avatar ? "#user-avatar-setting" : "#chat-background-setting").value = "";
  previewInterfaceSettings();
  toast(`${avatar ? "头像" : "对话背景"}已恢复默认，点击保存后保留`);
}

async function updateXixiAvatar(file) {
  const button = $("#change-xixi-avatar");
  const setting = $("#xixi-avatar-setting");
  if (!button || !setting) return;
  button.disabled = true;
  try {
    setting.value = await prepareAppearanceImage(file, { width: 512, height: 512, square: true, quality: 0.9 });
    const settings = loadLocalSettings();
    settings.xixi_avatar = setting.value;
    applyAppearance(settings);
    renderPersonaAvatar(settings);
    toast("昔夕头像已更新，点击保存人格设置后保留");
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.disabled = false;
  }
}

function resetXixiAvatar() {
  const setting = $("#xixi-avatar-setting");
  if (!setting) return;
  setting.value = "";
  const settings = loadLocalSettings();
  settings.xixi_avatar = "";
  applyAppearance(settings);
  renderPersonaAvatar(settings);
  toast("昔夕头像已恢复默认，点击保存人格设置后保留");
}

function parseOwnerAddresses(value) {
  const seen = new Set();
  return String(value || "")
    .split(/[，,、\n|]+/)
    .map((item) => item.trim().slice(0, 24))
    .filter((item) => item && !seen.has(item) && seen.add(item))
    .slice(0, 8);
}

function renderOwnerAddressList(value = $("#owner-addresses")?.value) {
  const host = $("#owner-address-preview");
  if (!host) return;
  const addresses = parseOwnerAddresses(value);
  host.replaceChildren(...addresses.map((address) => {
    const tag = document.createElement("span");
    tag.textContent = address;
    return tag;
  }));
  if (!addresses.length) {
    const empty = document.createElement("span");
    empty.textContent = "未设置";
    empty.dataset.empty = "true";
    host.append(empty);
  }
}

async function saveDesktopSettings() {
  persistLocalSettings();
  const desktopApi = window.pywebview?.api;
  if (!desktopApi?.save_preferences) return toast("启动偏好已保存；桌面行为需在昔夕桌面应用中设置", "error");
  const desktopSettings = {};
  $$('[data-desktop-setting]').forEach((input) => { desktopSettings[input.dataset.desktopSetting] = input.checked; });
  try {
    await desktopApi.save_preferences(desktopSettings);
    toast("基础与启动设置已保存");
  } catch (error) {
    toast(`桌面偏好保存失败：${error}`, "error");
  }
}

function statusLabel(online) { return online ? "正常" : "离线"; }

function qqStatusLabel(qq) {
  if (qq.online) return "在线";
  if (qq.account_state === "switching") return "切换中";
  if (qq.account_state === "waiting_login") return "等待登录";
  if (qq.account_state === "starting") return "启动中";
  if (qq.account_state === "error") return "启动失败";
  if (qq.connection_state === "connecting") return "连接中";
  if (qq.connection_state === "reconnecting") return "重连中";
  if (qq.connection_state === "disconnecting") return "下线中";
  return "已下线";
}

function qqConnectionDetail(qq) {
  if (qq.online) return `${qq.nickname} · ${qq.user_id}`;
  if (qq.account_state === "switching") return `正在切换到 ${qq.account_target}`;
  if (qq.account_state === "waiting_login") return `请完成 ${qq.account_target} 的 QQ 登录`;
  if (qq.account_state === "starting") return `正在启动 ${qq.account_target}`;
  if (qq.account_state === "error") return qq.account_error || "QQ 启动失败";
  if (qq.enabled && qq.napcat_online) return "NapCat 已登录，昔夕正在连接";
  if (qq.napcat_online) return "监听已关闭 · QQ 账号仍在线";
  return "NapCat 未登录";
}

function updateQqControl(qq) {
  const button = $("#toggle-qq");
  if (!button) return;
  const operationActive = ["starting", "waiting_login", "switching"].includes(qq.account_state);
  const shouldGoOffline = Boolean(qq.enabled || operationActive || qq.napcat_online);
  button.dataset.action = shouldGoOffline ? "offline" : "online";
  button.disabled = state.qqControlBusy || qq.connection_state === "disconnecting";
  button.classList.toggle("go-offline", shouldGoOffline);
  button.innerHTML = shouldGoOffline
    ? `<i data-lucide="log-out"></i><span>${operationActive ? "取消并下线" : "QQ 下线"}</span>`
    : '<i data-lucide="log-in"></i><span>QQ 上线</span>';
}

function setQqComponentStatus(component, componentState, label, detail) {
  const card = $(`[data-qq-component="${component}"]`);
  if (!card) return;
  card.dataset.state = componentState;
  $(`#qq-${component}-status`).textContent = label;
  $(`#qq-${component}-detail`).textContent = detail;
}

function updateQqSettingsControls(qq = {}) {
  const operationActive = ["starting", "waiting_login", "switching"].includes(qq.account_state);
  const channelRequested = Boolean(qq.enabled || operationActive || qq.napcat_online || qq.process_online);
  const installed = qq.napcat_installed !== false;
  const busy = Boolean(state.qqControlBusy || state.qqAccountBusy);
  const login = $("#qq-login-qr");
  const start = $("#qq-start-channel");
  const stop = $("#qq-stop-channel");
  const restart = $("#qq-restart-channel");
  if (!login || !start || !stop || !restart) return;

  login.disabled = busy || !installed || qq.online;
  start.disabled = busy || !installed || Boolean(qq.enabled || operationActive);
  stop.disabled = busy || !channelRequested;
  restart.disabled = busy || !installed || !channelRequested;
  login.innerHTML = operationActive
    ? '<i data-lucide="loader-circle"></i><span>等待登录</span>'
    : `<i data-lucide="qr-code"></i><span>${qq.online ? "已登录" : "查看登录二维码"}</span>`;
  start.innerHTML = qq.connection_state === "connecting"
    ? '<i data-lucide="loader-circle"></i><span>连接中</span>'
    : '<i data-lucide="plug-zap"></i><span>连接消息通道</span>';
  restart.classList.toggle("loading", busy && restart.getAttribute("aria-busy") === "true");
}

function qqIdentityReady(identity = qqIdentityPayload()) {
  return /^[1-9]\d{4,11}$/.test(identity.bot_qq_id)
    && /^[1-9]\d{4,11}$/.test(identity.owner_qq_id);
}

function setQqGuideStep(step, stepState) {
  const item = $(`[data-qq-step="${step}"]`);
  if (item) item.dataset.state = stepState;
}

function updateQqSetupGuide(qq = {}) {
  const guide = $("#qq-install-guide");
  const action = $("#qq-guide-primary");
  if (!guide || !action) return;

  const identity = qqIdentityPayload();
  const installed = qq.napcat_installed !== false;
  const identityReady = qqIdentityReady(identity);
  const savedBot = String(qq.configured_user_id || state.bootstrap?.qq_identity?.bot_qq_id || "");
  const savedOwner = String(qq.owner_user_id || state.bootstrap?.qq_identity?.owner_qq_id || "");
  const identitySaved = identityReady
    && identity.bot_qq_id === savedBot
    && identity.owner_qq_id === savedOwner
    && !state.qqIdentityDirty;
  const loginOnline = Boolean(qq.qq_login_online ?? qq.napcat_online);
  const onebotOnline = Boolean(qq.online);
  const operationActive = ["starting", "waiting_login", "switching"].includes(qq.account_state);
  const connecting = ["connecting", "reconnecting"].includes(qq.connection_state);
  const busy = Boolean(state.environmentInstallBusy || state.qqControlBusy || state.qqAccountBusy);
  const hasError = qq.account_state === "error";

  let stage = "login";
  if (!installed) stage = "install";
  else if (!identitySaved) stage = "identity";
  else if (onebotOnline) stage = "online";
  else if (loginOnline) stage = "connect";
  else if (operationActive) stage = "waiting";
  else if (hasError) stage = "error";

  guide.dataset.stage = stage;
  guide.dataset.state = onebotOnline ? "installed" : (hasError ? "error" : "working");
  setQqGuideStep("install", installed ? "complete" : "current");
  setQqGuideStep("identity", !installed ? "pending" : (identitySaved ? "complete" : "current"));
  setQqGuideStep("login", !installed || !identitySaved ? "pending" : (loginOnline || onebotOnline ? "complete" : "current"));
  setQqGuideStep("connect", onebotOnline ? "complete" : (loginOnline ? "current" : "pending"));

  const guideStatus = $("#qq-guide-status");
  const title = $("#qq-guide-next-title");
  const copy = $("#qq-guide-next-copy");
  const heading = $("#qq-install-title");
  const intro = $("#qq-install-copy");
  heading.textContent = `让${characterName()}登录 QQ`;
  intro.textContent = onebotOnline
    ? `${characterName()}已经可以收发 QQ 私聊和群聊消息。`
    : "按当前高亮步骤操作，扫码完成后会自动上线。";

  const presentation = {
    install: ["需要准备组件", "先安装 QQ 登录组件", "只需安装一次，完成后会自动进入下一步。", "package-plus", "安装 QQ 组件", "working"],
    identity: ["需要填写账号", "填写两个 QQ 号", `填写${characterName()}使用的 QQ 和你的主人 QQ，然后继续。`, "user-round-pen", identityReady ? "保存并继续" : "填写 QQ 账号", "working"],
    login: ["等待扫码登录", "使用手机 QQ 扫码", "点击后会生成二维码，扫码成功后无需再点启动。", "qr-code", "生成登录二维码", "working"],
    waiting: ["等待手机扫码", "二维码正在等待扫码", "二维码过期时可以在弹窗中直接刷新。", "qr-code", "查看登录二维码", "working"],
    connect: [connecting ? "正在自动连接" : "等待连接通道", "扫码成功，正在上线", "QQ 已登录，正在建立消息通道。", connecting ? "loader-circle" : "plug-zap", connecting ? "正在连接" : "继续连接", "working"],
    online: ["QQ 已上线", `${characterName()}已经登录 QQ`, "现在可以直接在 QQ 中和她聊天。", "circle-check", "已完成", "online"],
    error: ["登录需要重试", "QQ 登录没有完成", qq.account_error || "重新生成二维码并按提示扫码。", "refresh-cw", "重新登录", "error"],
  }[stage];
  guideStatus.textContent = presentation[0];
  guideStatus.dataset.state = presentation[5];
  title.textContent = presentation[1];
  copy.textContent = presentation[2];
  action.innerHTML = `<i data-lucide="${presentation[3]}"></i><span>${presentation[4]}</span>`;
  action.disabled = busy || stage === "online" || (stage === "connect" && connecting);
  action.setAttribute("aria-busy", String(busy || (stage === "connect" && connecting)));
}

function renderQqSettings(qq = {}) {
  const overall = $("#qq-settings-overall-status");
  if (!overall) return;
  const operationActive = ["starting", "waiting_login", "switching"].includes(qq.account_state);
  const hasError = qq.account_state === "error";
  const processOnline = Boolean(qq.qq_process_online ?? qq.process_online ?? qq.napcat_online);
  const loginOnline = Boolean(qq.qq_login_online ?? qq.napcat_online);
  const napcatOnline = Boolean(qq.napcat_service_online ?? qq.napcat_online);
  const onebotOnline = Boolean(qq.online);
  overall.dataset.state = qq.online ? "online" : (hasError ? "error" : (operationActive || qq.enabled ? "working" : "offline"));
  overall.textContent = qqStatusLabel(qq);
  $("#qq-connection-copy").textContent = hasError
    ? (qq.account_error || "QQ 通道启动失败，请检查 NapCat")
    : qqConnectionDetail(qq);

  setQqComponentStatus(
    "process",
    processOnline ? "online" : (operationActive ? "working" : "offline"),
    processOnline ? "运行中" : (operationActive ? "启动中" : "未运行"),
    processOnline ? "昔夕专用 QQ 进程已启动" : "等待 QQ 进程启动",
  );
  setQqComponentStatus(
    "login",
    loginOnline ? "online" : (qq.account_state === "waiting_login" ? "working" : "offline"),
    loginOnline ? "已登录" : (qq.account_state === "waiting_login" ? "等待扫码" : "未登录"),
    loginOnline ? `${qq.nickname || "QQ"} · ${qq.user_id || qq.configured_user_id || ""}` : "等待账号登录",
  );
  setQqComponentStatus(
    "napcat",
    napcatOnline ? "online" : (operationActive ? "working" : "offline"),
    napcatOnline ? "在线" : (operationActive ? "启动中" : "离线"),
    napcatOnline ? "NapCat 服务正在响应" : "插件通道未启动",
  );
  setQqComponentStatus(
    "onebot",
    onebotOnline ? "online" : (qq.connection_state === "connecting" || qq.connection_state === "reconnecting" ? "working" : "offline"),
    onebotOnline ? "已连接" : (qq.connection_state === "connecting" || qq.connection_state === "reconnecting" ? "连接中" : "未连接"),
    onebotOnline ? "消息收发通道工作正常" : "等待昔夕连接 OneBot",
  );
  $("#qq-connection-note").textContent = hasError
    ? `启动失败：${qq.account_error || "请检查 QQ 登录窗口和 NapCat 日志"}`
    : (qq.account_state === "waiting_login"
      ? `正在等待 ${qq.account_target || qq.configured_user_id || "目标账号"} 完成 QQ 登录。`
      : "上方首次登录向导会完成常用流程；这里用于查看状态或手动重新连接。");
  updateQqSettingsControls(qq);
  updateQqSetupGuide(qq);
}

function createServiceControl(key, status) {
  const button = document.createElement("button");
  button.className = "secondary-button service-card-control";
  button.type = "button";
  button.dataset.control = key;

  if (key === "qq") {
    button.classList.add("qq-control-button");
    button.id = "toggle-qq";
    return button;
  }

  if (key === "weather") {
    const controls = document.createElement("div");
    controls.className = "service-card-controls";
    const cityButton = document.createElement("button");
    cityButton.className = "secondary-button service-card-control";
    cityButton.type = "button";
    cityButton.dataset.control = "weather";
    cityButton.dataset.action = "change-city";
    cityButton.innerHTML = '<i data-lucide="map-pin"></i><span>更换城市</span>';

    const alertsEnabled = Boolean(status.weather.alerts_enabled);
    button.dataset.setting = "weather_alert_enabled";
    button.dataset.enabled = String(alertsEnabled);
    button.classList.toggle("disable-action", alertsEnabled);
    button.disabled = state.serviceControlBusy === "weather_alert_enabled";
    button.innerHTML = alertsEnabled
      ? '<i data-lucide="bell-off"></i><span>关闭提醒</span>'
      : '<i data-lucide="bell-ring"></i><span>开启提醒</span>';
    controls.append(cityButton, button);
    return controls;
  }

  if (key === "voice") {
    const online = Boolean(status.voice.online);
    const warming = status.voice.prewarm?.state === "warming";
    button.dataset.action = online ? "offline" : "online";
    button.classList.toggle("disable-action", online);
    button.disabled = state.voiceControlBusy || warming;
    button.innerHTML = warming
      ? '<i data-lucide="loader-circle"></i><span>启动中</span>'
      : online
      ? '<i data-lucide="volume-x"></i><span>关闭语音</span>'
      : '<i data-lucide="volume-2"></i><span>开启语音</span>';
    return button;
  }

  if (key === "model" || key === "vision") {
    const controls = document.createElement("div");
    controls.className = "service-card-controls model-service-controls";
    const enabled = key === "model"
      ? Boolean(status.model.enabled)
      : Boolean(status.vision.enabled);

    const switchButton = document.createElement("button");
    switchButton.className = "secondary-button service-card-control";
    switchButton.type = "button";
    switchButton.dataset.control = key;
    switchButton.dataset.panel = "model";
    switchButton.dataset.modelCapability = key === "model" ? "language" : "vision";
    switchButton.innerHTML = '<i data-lucide="replace"></i><span>更换模型</span>';

    button.classList.toggle("disable-action", enabled);
    if (key === "model") {
      button.dataset.action = enabled ? "offline" : "online";
      button.disabled = state.serviceControlBusy === "brain_enabled" || state.quickControlBusy === "model";
      button.innerHTML = enabled
        ? '<i data-lucide="power-off"></i><span>关闭模型</span>'
        : '<i data-lucide="power"></i><span>开启模型</span>';
    } else {
      button.dataset.setting = "vision_enabled";
      button.dataset.enabled = String(enabled);
      button.disabled = state.serviceControlBusy === "vision_enabled" || state.quickControlBusy === "vision";
      button.innerHTML = enabled
        ? '<i data-lucide="power-off"></i><span>关闭识图</span>'
        : '<i data-lucide="power"></i><span>开启识图</span>';
    }

    controls.append(switchButton, button);
    return controls;
  }

  const settingControls = {
    learning: ["learning_enabled", status.learning.online, "学习"],
  };
  if (settingControls[key]) {
    const [setting, enabled, label] = settingControls[key];
    button.dataset.setting = setting;
    button.dataset.enabled = String(enabled);
    button.classList.toggle("disable-action", enabled);
    button.disabled = state.serviceControlBusy === setting;
    button.innerHTML = enabled
      ? `<i data-lucide="power-off"></i><span>关闭${label}</span>`
      : `<i data-lucide="power"></i><span>开启${label}</span>`;
    return button;
  }
  return button;
}

function compactStatusEntries(status) {
  const voiceWarming = status.voice.prewarm?.state === "warming";
  return [
    ["QQ", status.qq.online, status.qq.online ? status.qq.nickname : qqStatusLabel(status.qq)],
    ["大脑", status.model.online, status.model.name],
    ["视觉", status.vision.enabled && status.vision.online, status.vision.enabled ? status.vision.model : "已关闭"],
    ["语音", status.voice.online, status.voice.online ? "语音系统已打开" : (voiceWarming ? "语音系统启动中" : (status.voice.enabled ? "语音系统暂不可用" : "语音系统已关闭"))],
  ];
}

function renderCompactStatusInto(host, status) {
  if (!host) return;
  const entries = compactStatusEntries(status);
  host.replaceChildren(...entries.map(([label, online, detail]) => {
    const row = document.createElement("div");
    row.className = "compact-status-item";
    const name = document.createElement("span");
    const dot = document.createElement("i");
    dot.className = `status-dot ${online ? "online" : ""}`;
    name.append(dot, document.createTextNode(label));
    const small = document.createElement("small");
    small.textContent = detail;
    row.append(name, small);
    return row;
  }));
}

function quickServiceEntries(status) {
  const qqOperationActive = ["starting", "waiting_login", "switching"].includes(status.qq.account_state);
  const voiceWarming = status.voice.prewarm?.state === "warming";
  const voiceInstalled = status.voice.release_ready !== false;
  const weatherAlertsEnabled = Boolean(status.weather.alerts_enabled);
  const weatherDeliveryReady = status.weather.delivery_ready ?? Boolean(
    weatherAlertsEnabled && status.weather.online && status.qq.online
  );
  const weatherDetail = weatherAlertsEnabled
    ? `${status.weather.location} · ${weatherDeliveryReady ? "提醒运行中" : "提醒已开启，等待 QQ 上线"}`
    : `${status.weather.location} · 提醒已关闭`;
  return [
    { key: "qq", label: "QQ", icon: "message-circle", enabled: Boolean(status.qq.enabled || status.qq.napcat_online || qqOperationActive), online: Boolean(status.qq.online), detail: qqStatusLabel(status.qq), panel: "qq" },
    { key: "model", label: "大脑", icon: "brain-circuit", enabled: Boolean(status.model.enabled), online: Boolean(status.model.online), detail: status.model.enabled ? status.model.name : "已关闭", panel: "model", capability: "language" },
    { key: "vision", label: "视觉", icon: "scan-eye", enabled: Boolean(status.vision.enabled), online: Boolean(status.vision.enabled && status.vision.online), detail: status.vision.enabled ? status.vision.model : "已关闭", panel: "model", capability: "vision" },
    { key: "voice", label: "语音", icon: "audio-waveform", enabled: Boolean(status.voice.enabled), online: Boolean(status.voice.online), busy: voiceWarming, detail: voiceInstalled ? (status.voice.online ? "语音系统已打开" : (voiceWarming ? "语音系统启动中" : (status.voice.enabled ? "语音系统暂不可用" : "语音系统已关闭"))) : "需要先安装本地语音系统", panel: voiceInstalled ? "" : "environment", focus: voiceInstalled ? "" : "local_voice" },
    { key: "learning", label: "持续学习", icon: "book-open-check", enabled: Boolean(status.learning.online), online: Boolean(status.learning.online), detail: status.learning.online ? `${status.learning.web_memories} 条联网知识` : "已关闭", panel: "learning", focus: "learning_enabled", setting: "learning_enabled" },
    { key: "weather", label: "天气提醒", icon: "bell-ring", enabled: weatherAlertsEnabled, online: weatherDeliveryReady, detail: weatherDetail, panel: "qq", focus: "weather_alert_enabled", setting: "weather_alert_enabled" },
  ];
}

function createQuickServiceRow(service, variant = "") {
  const row = document.createElement("div");
  row.className = `quick-service ${variant} ${service.enabled ? "enabled" : "disabled"} ${service.online ? "online" : ""}`.trim();

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "quick-service-toggle";
  toggle.dataset.quickService = service.key;
  toggle.dataset.action = service.enabled ? "offline" : "online";
  toggle.disabled = Boolean(service.busy) || state.quickControlBusy === service.key || (service.key === "qq" && state.qqControlBusy) || (service.key === "voice" && state.voiceControlBusy);
  toggle.setAttribute("aria-pressed", String(service.enabled));
  toggle.title = service.enabled ? `关闭${service.label}` : `开启${service.label}`;
  toggle.innerHTML = `<span class="quick-service-icon"><i data-lucide="${service.icon}"></i><i class="status-dot ${service.online ? "online" : ""}"></i></span><span class="quick-service-copy"><strong>${service.label}</strong><small></small></span>`;
  toggle.querySelector("small").textContent = service.detail;

  row.append(toggle);
  if (service.panel) {
    const settings = document.createElement("button");
    settings.type = "button";
    settings.className = "quick-service-settings";
    settings.dataset.quickPanel = service.panel;
    if (service.focus) settings.dataset.focusSetting = service.focus;
    if (service.capability) settings.dataset.modelCapability = service.capability;
    settings.title = `打开${service.label}设置`;
    settings.setAttribute("aria-label", `打开${service.label}设置`);
    settings.innerHTML = '<i data-lucide="chevron-right"></i>';
    row.append(settings);
  } else {
    row.classList.add("no-settings");
  }
  return row;
}

function renderQuickServiceControls(status) {
  const host = $("#inspector-status-list");
  if (!host) return;
  host.className = "quick-service-list";
  host.replaceChildren(...quickServiceEntries(status).map((service) => createQuickServiceRow(service)));
  iconRefresh();
}

function renderStartupServiceControls(status) {
  const host = $("#startup-service-list");
  if (!host) return;
  host.replaceChildren(...quickServiceEntries(status).map((service) => createQuickServiceRow(service, "startup-service")));
  iconRefresh();
}

function renderCompactStatus(status) {
  renderQuickServiceControls(status);
  renderStartupServiceControls(status);
}

async function toggleQuickService(button) {
  const service = button.dataset.quickService;
  const action = button.dataset.action;
  if (!service || state.quickControlBusy) return;
  state.quickControlBusy = service;
  renderCompactStatus(state.status);
  updateRailStatus(state.status);
  try {
    if (service === "qq") {
      await toggleQq();
    } else if (service === "voice") {
      await toggleVoice({ dataset: { action }, disabled: false });
    } else if (service === "model") {
      await api("/api/model/control", { method: "POST", body: JSON.stringify({ action }) });
      await loadStatus();
      toast(action === "online" ? "大脑功能已开启" : "大脑功能已关闭");
    } else if (service === "vision") {
      const enabled = action === "online";
      const applied = await api("/api/settings", { method: "PUT", body: JSON.stringify({ vision_enabled: enabled }) });
      if (state.bootstrap?.settings) Object.assign(state.bootstrap.settings, applied);
      await loadStatus();
      toast(enabled ? "图片理解已开启" : "图片理解已关闭");
    } else if (["learning", "weather"].includes(service)) {
      const enabled = action === "online";
      const setting = service === "learning" ? "learning_enabled" : "weather_alert_enabled";
      const payload = {
        [setting]: enabled,
        ...(service === "weather" && enabled ? { weather_enabled: true } : {}),
      };
      const applied = await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
      if (state.bootstrap?.settings) Object.assign(state.bootstrap.settings, applied);
      await loadStatus();
      const label = service === "learning" ? "持续学习" : "天气提醒";
      toast(`${label}已${enabled ? "开启" : "关闭"}`);
    }
  } catch (error) {
    toast(error.message, "error");
    await loadStatus();
  } finally {
    state.quickControlBusy = "";
    if (state.status) {
      renderCompactStatus(state.status);
      updateRailStatus(state.status);
    }
  }
}

function openQuickServiceSettings(button) {
  setInspector(false);
  setView("tuning");
  showTuningPanel(button.dataset.quickPanel);
  const capability = button.dataset.modelCapability;
  if (capability) {
    setTimeout(() => focusModelCapability(capability), 40);
    return;
  }
  const focus = button.dataset.focusSetting;
  if (focus) {
    setTimeout(() => {
      const target = button.dataset.quickPanel === "environment"
        ? $(`[data-environment-feature="${focus}"]`)
        : $(`[data-setting="${focus}"]`);
      target?.scrollIntoView({ block: "center", behavior: "smooth" });
      target?.focus?.({ preventScroll: true });
    }, 40);
  }
}

function focusModelCapability(capability) {
  const candidates = $$(`#model-provider-list [data-model-capability="${capability}"]`);
  const target = candidates.find((item) => !item.classList.contains("active"))
    || candidates[0]
    || $("#add-model-provider");
  target?.scrollIntoView({ block: "center", behavior: "smooth" });
  target?.focus({ preventScroll: true });
}

function updateHomeService(key, value, { online = false, enabled = true, attention = false } = {}) {
  const item = $(`[data-home-service="${key}"]`);
  if (!item) return;
  item.dataset.state = !enabled ? "paused" : (attention ? "attention" : (online ? "online" : "offline"));
  const output = item.querySelector("[data-home-service-value]");
  if (output) output.textContent = value;
}

function renderHomeStatus(status) {
  renderInspectorAlert(status);
  const model = status.model || {};
  const qq = status.qq || {};
  const voice = status.voice || {};
  const vision = status.vision || {};
  const learning = status.learning || {};
  const weather = status.weather || {};
  const game = status.game || {};
  const voiceWarming = voice.prewarm?.state === "warming";
  const voiceLanguages = { zh: "中文", ja: "日语", en: "英语" };

  updateHomeService("model", model.enabled ? (model.online ? model.name || "已连接" : "连接异常") : "已关闭", {
    online: Boolean(model.online), enabled: model.enabled !== false, attention: Boolean(model.enabled !== false && !model.online),
  });
  updateHomeService("qq", qq.enabled ? qqStatusLabel(qq) : "已关闭", {
    online: Boolean(qq.online), enabled: Boolean(qq.enabled), attention: Boolean(qq.enabled && !qq.online),
  });
  updateHomeService("voice", voice.enabled ? `${voiceLanguages[voice.language] || "中文"} · ${voice.online ? "正常" : (voiceWarming ? "启动中" : "不可用")}` : "已关闭", {
    online: Boolean(voice.online), enabled: voice.enabled !== false, attention: Boolean(voice.enabled !== false && !voice.online && !voiceWarming),
  });
  updateHomeService("vision", vision.enabled ? (vision.online ? vision.model || "正常" : "不可用") : "已关闭", {
    online: Boolean(vision.online), enabled: vision.enabled !== false, attention: Boolean(vision.enabled !== false && !vision.online),
  });
  updateHomeService("learning", learning.online ? `${Number(learning.memories || 0).toLocaleString("zh-CN")} 条记忆` : "已关闭", {
    online: Boolean(learning.online), enabled: Boolean(learning.online),
  });
  const weatherMode = weather.alerts_enabled
    ? (weather.delivery_ready ? "提醒中" : "等待 QQ")
    : "仅天气";
  updateHomeService("weather", weather.online ? `${weather.location || "当前城市"} · ${weatherMode}` : "已关闭", {
    online: Boolean(weather.online), enabled: Boolean(weather.online), attention: Boolean(weather.online && weather.alerts_enabled && !weather.delivery_ready),
  });
  const gameMode = "只读观察";
  updateHomeService("game", game.active ? `${gameMode} · 运行中` : `${gameMode} · 待命`, {
    online: Boolean(game.active), enabled: true,
  });

  $("#home-memory-count").textContent = Number(learning.memories || 0).toLocaleString("zh-CN");
  $("#home-knowledge-count").textContent = Number(learning.web_memories || 0).toLocaleString("zh-CN");
  $("#home-game-state").textContent = game.active ? "运行中" : gameMode;
  $("#home-uptime").textContent = formatDuration(Number(status.app?.uptime_s || 0));
}

function renderHomeSnapshot(snapshot = {}) {
  const resume = $("#home-resume-panel");
  const conversation = snapshot.recent_conversation;
  resume.hidden = !conversation;
  $(".home-content-grid").classList.toggle("without-resume", !conversation);
  if (conversation) {
    const source = String(conversation.session_id || "").startsWith("group:") ? "群聊中的上次话题" : "你们的上次对话";
    $("#home-resume-title").textContent = source;
    $("#home-resume-copy").textContent = String(conversation.content || "").slice(0, 120);
  }

  const activities = Array.isArray(snapshot.activities) ? snapshot.activities.slice(0, 3) : [];
  $("#home-activity-summary").textContent = activities.length ? `${activities.length} 条值得留意的进展` : "今天还很安静";
  $("#home-activity-list").replaceChildren(...activities.map((item) => {
    const row = document.createElement("div");
    row.className = "home-activity-item";
    const dot = document.createElement("i");
    const copy = document.createElement("span"); copy.textContent = item.title;
    const time = document.createElement("time"); time.textContent = formatDate(item.created_at);
    row.append(dot, copy, time);
    return row;
  }));
}

function renderHomeAgent(payload = {}) {
  const reflections = Array.isArray(payload.reflections) ? payload.reflections : [];
  const dailyReflections = reflections
    .filter((item) => item.period_type === "daily")
    .sort((left, right) => String(right.period_key).localeCompare(String(left.period_key)));
  const latest = dailyReflections[0];
  $("#home-reflection-count").textContent = String(dailyReflections.length);
  $("#home-growth-title").textContent = latest?.title || "还没有形成今天的想法";
  const firstParagraph = String(latest?.content || `${characterName()}正在从真实对话和学习内容中形成自己的偏好与判断。`)
    .split(/\n\s*\n/)[0]
    .trim();
  $("#home-growth-copy").textContent = firstParagraph;
  const summary = payload.summary || {};
  const meta = [];
  if (Number(summary.active_goals || 0)) meta.push(`${summary.active_goals} 个目标进行中`);
  if (Number(summary.pending_threads || 0)) meta.push(`${summary.pending_threads} 个话题待跟进`);
  $("#home-growth-meta").textContent = meta.join(" · ") || "成长内容已同步";
}

function renderInspectorAlert(status) {
  const alert = $("#inspector-alert");
  if (!alert) return;
  const issues = [
    status.qq.enabled && !status.qq.online ? "QQ 未连接" : "",
    status.model.enabled && !status.model.online ? "大脑离线" : "",
    status.vision.enabled && !status.vision.online ? "视觉不可用" : "",
    status.voice.enabled && !status.voice.online && status.voice.prewarm?.state !== "warming" ? "语音不可用" : "",
  ].filter(Boolean);
  alert.dataset.hasIssues = String(issues.length > 0);
  alert.hidden = state.currentView !== "system" || issues.length === 0;
  $("#inspector-alert-title").textContent = issues.length > 1 ? `${issues.length} 项状态异常` : (issues[0] || "状态正常");
  $("#inspector-alert-copy").textContent = issues.length > 1 ? issues.join(" · ") : "打开系统页可以检查具体原因";
}

function renderStatus(status) {
  state.status = status;
  syncVoiceLanguageControl();
  updateQqIdentityNote(status.qq);
  if (state.bootstrap?.qq_identity && status.qq) {
    state.bootstrap.qq_identity = {
      ...state.bootstrap.qq_identity,
      actual_online: Boolean(status.qq.napcat_online),
      actual_user_id: status.qq.user_id ? String(status.qq.user_id) : "",
      actual_nickname: status.qq.nickname || "",
      account_matches: Boolean(
        status.qq.napcat_online
        && String(status.qq.user_id) === String(state.bootstrap.qq_identity.bot_qq_id)
      ),
    };
    fillQqIdentity(state.bootstrap.qq_identity);
  }
  renderQqSettings(status.qq || {});
  const services = [
    ["qq", "QQ", "message-circle", status.qq.online, qqConnectionDetail(status.qq), qqStatusLabel(status.qq)],
    ["model", "语言模型", "brain-circuit", status.model.enabled && status.model.online, `${status.model.name} · ${status.model.provider}`, status.model.enabled ? statusLabel(status.model.online) : "已关闭"],
    ["vision", "图片理解", "scan-eye", status.vision.enabled && status.vision.online, status.vision.model, status.vision.enabled ? statusLabel(status.vision.online) : "已关闭"],
    ["voice", "语音合成", "audio-waveform", status.voice.online, status.voice.online ? "语音系统已打开" : (status.voice.enabled ? "语音系统暂不可用" : "语音系统已关闭")],
    ["learning", "持续学习", "book-open-check", status.learning.online, `${status.learning.web_memories} 条联网知识`],
    ["weather", "天气", "cloud-sun", Boolean(status.weather.delivery_ready), `${status.weather.location} · ${status.weather.alerts_enabled ? (status.weather.delivery_ready ? "提醒运行中" : "提醒已开启，等待 QQ 上线") : "提醒已关闭"}`],
  ];
  const grid = $("#status-grid");
  grid.replaceChildren(...services.map(([key, name, icon, online, detail, label]) => {
    const card = document.createElement("article");
    card.className = "status-card has-control";
    card.dataset.service = key;
    card.innerHTML = `<div class="status-card-head"><span class="status-card-icon"><i data-lucide="${icon}"></i></span><span class="status-pill"><i class="status-dot ${online ? "online" : ""}"></i>${label || statusLabel(online)}</span></div>`;
    const strong = document.createElement("strong");
    strong.textContent = name;
    const span = document.createElement("span");
    span.textContent = detail;
    card.append(strong, span, createServiceControl(key, status));
    return card;
  }));
  $("#uptime-value").textContent = formatDuration(status.app.uptime_s);
  $("#memory-count-value").textContent = status.learning.memories;
  $("#knowledge-count-value").textContent = status.learning.web_memories;
  $("#reflection-count-value").textContent = status.learning.pending_reflections;
  $("#status-updated").textContent = `更新于 ${new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}`;
  $("#profile-presence-dot").classList.toggle("online", status.app.online);
  $("#drawer-runtime-dot").classList.toggle("online", status.app.online && status.model.online);
  $("#drawer-runtime-status").textContent = status.qq.online ? "全部核心连接正常" : "本地在线，QQ 未连接";
  updateRailStatus(status);
  const emptyStatus = $("#empty-status");
  if (emptyStatus) {
    emptyStatus.textContent = status.qq.online ? "大脑、记忆和 QQ 已同步" : "本地大脑在线，QQ 暂未连接";
  }
  updateQqControl(status.qq);
  renderCompactStatus(status);
  renderHomeStatus(status);
  if (!state.sending && state.recorder?.state !== "recording") {
    setOperation(status.model.online ? "idle" : "offline", "", status.model.online ? "对话已同步" : "语言模型当前不可用");
  }
  iconRefresh();
}

function updateRailStatus(status) {
  quickServiceEntries(status).forEach((service) => {
    const button = $(`[data-rail-service="${service.key}"]`);
    if (!button) return;
    const busy = state.quickControlBusy === service.key
      || (service.key === "qq" && state.qqControlBusy)
      || (service.key === "voice" && state.voiceControlBusy);
    button.dataset.quickService = service.key;
    button.dataset.action = service.enabled ? "offline" : "online";
    button.classList.toggle("online", service.enabled && service.online);
    button.classList.toggle("attention", service.enabled && !service.online);
    button.disabled = busy;
    button.setAttribute("aria-busy", String(busy));
    button.setAttribute("aria-pressed", String(service.enabled));
    const action = service.enabled ? "关闭" : "开启";
    const stateLabel = service.enabled ? (service.online ? "在线" : "等待连接") : "已关闭";
    button.title = busy ? `${service.label}正在切换` : `${service.label} · ${service.detail} · 点击${action}`;
    button.setAttribute("aria-label", `${service.label}：${stateLabel}，点击${action}`);
  });
}

function formatDuration(seconds) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours) return `${hours} 小时 ${minutes} 分`;
  return `${minutes} 分钟`;
}

function interestPresentation(interest) {
  const category = String(interest?.category || "").trim();
  const topic = String(interest?.topic || "").trim();
  const value = `${category} ${topic}`;
  if (/游戏|game|视觉小说|galgame/i.test(value)) return { icon: "gamepad-2", tone: "game" };
  if (/动漫|动画|漫画|anime|manga/i.test(value)) return { icon: "clapperboard", tone: "anime" };
  if (/音乐|歌曲|配乐|music/i.test(value)) return { icon: "music-2", tone: "music" };
  if (/美术|绘画|画面|视觉|art|design/i.test(value)) return { icon: "palette", tone: "art" };
  if (/故事|文学|小说|剧情|story|book/i.test(value)) return { icon: "book-open-text", tone: "story" };
  return { icon: "sparkles", tone: "general" };
}

function interestAffinityLabel(value) {
  const affinity = Number(value || 0);
  if (affinity >= 90) return "特别在意";
  if (affinity >= 75) return "持续关注";
  if (affinity >= 55) return "有些喜欢";
  return "偶尔留意";
}

function interestMatchesFilter(interest, filter) {
  if (filter === "core") return Boolean(interest.core);
  if (filter === "hot") return Number(interest.affinity ?? 50) >= 75;
  return true;
}

function stopLeadingInterestRotation() {
  if (state.leadingInterestTimer) clearInterval(state.leadingInterestTimer);
  if (state.leadingInterestTransitionTimer) clearTimeout(state.leadingInterestTransitionTimer);
  state.leadingInterestTimer = null;
  state.leadingInterestTransitionTimer = null;
  $("#growth-leading-content")?.classList.remove("is-changing");
}

function showLeadingInterest(index, animate = true) {
  const items = state.leadingInterests;
  if (!items.length) {
    $("#growth-leading-topic").textContent = "还没有形成明确偏好";
    $("#growth-leading-reason").textContent = "兴趣会随着学习和经历继续变化";
    $("#growth-leading-position").textContent = "0 / 0";
    return;
  }
  const nextIndex = ((Number(index) || 0) % items.length + items.length) % items.length;
  const content = $("#growth-leading-content");
  const apply = () => {
    const interest = items[nextIndex];
    state.leadingInterestIndex = nextIndex;
    $("#growth-leading-topic").textContent = interest.topic || "未命名兴趣";
    $("#growth-leading-reason").textContent = interest.reason || "兴趣会随着学习和经历继续变化";
    $("#growth-leading-position").textContent = `${nextIndex + 1} / ${items.length}`;
    $("#inspector-growth-title").textContent = `最在意 ${interest.topic || "这个方向"}`;
    $("#inspector-growth-copy").textContent = interest.reason || "兴趣会随着学习和经历继续变化";
    $$("[data-leading-interest]").forEach((button) => {
      const active = Number(button.dataset.leadingInterest) === nextIndex;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    content?.classList.remove("is-changing");
    state.leadingInterestTransitionTimer = null;
  };
  if (!animate || items.length === 1 || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    apply();
    return;
  }
  content?.classList.add("is-changing");
  if (state.leadingInterestTransitionTimer) clearTimeout(state.leadingInterestTransitionTimer);
  state.leadingInterestTransitionTimer = setTimeout(apply, 190);
}

function startLeadingInterestRotation() {
  if (state.leadingInterestTimer) clearInterval(state.leadingInterestTimer);
  state.leadingInterestTimer = null;
  if (state.currentView !== "growth" || state.leadingInterests.length <= 1) return;
  state.leadingInterestTimer = setInterval(() => {
    if (document.hidden || state.currentView !== "growth") return;
    showLeadingInterest(state.leadingInterestIndex + 1);
  }, 4800);
}

function setLeadingInterests(interests) {
  if (state.leadingInterestTransitionTimer) clearTimeout(state.leadingInterestTransitionTimer);
  state.leadingInterestTransitionTimer = null;
  $("#growth-leading-content")?.classList.remove("is-changing");
  const previousTopic = state.leadingInterests[state.leadingInterestIndex]?.topic;
  const maximum = interests.length
    ? Math.max(...interests.map((interest) => Number(interest.affinity ?? 50)))
    : -1;
  state.leadingInterests = interests.filter((interest) => Number(interest.affinity ?? 50) === maximum);
  const previousIndex = state.leadingInterests.findIndex((interest) => interest.topic === previousTopic);
  state.leadingInterestIndex = previousIndex >= 0 ? previousIndex : 0;
  const dots = $("#growth-leading-dots");
  dots.replaceChildren(...state.leadingInterests.map((interest, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.leadingInterest = String(index);
    button.title = interest.topic || `第 ${index + 1} 项兴趣`;
    button.setAttribute("aria-label", `查看最在意的兴趣：${interest.topic || `第 ${index + 1} 项`}`);
    button.addEventListener("click", () => {
      showLeadingInterest(index);
      startLeadingInterestRotation();
    });
    return button;
  }));
  dots.hidden = state.leadingInterests.length <= 1;
  showLeadingInterest(state.leadingInterestIndex, false);
  startLeadingInterestRotation();
}

function normalizedInterestCategory(interest) {
  const category = String(interest?.category || "未分类").trim() || "未分类";
  if (/游戏|game|视觉小说|galgame/i.test(category)) return "游戏";
  if (/动漫|动画|漫画|anime|manga/i.test(category)) return "动漫";
  if (/音乐|歌曲|配乐|music/i.test(category)) return "音乐";
  if (/美术|绘画|画面|视觉|设计|art|design/i.test(category)) return "美术";
  if (/故事|文学|小说|剧情|story|book/i.test(category)) return "故事";
  return category;
}

function interestCategoryRank(category) {
  const preferred = ["游戏", "动漫", "动画", "漫画", "音乐", "美术", "故事", "文学", "综合", "未分类"];
  const index = preferred.indexOf(category);
  return index >= 0 ? index : preferred.length;
}

function renderInterests(payload) {
  state.interests = structuredClone(payload || {});
  const interests = Array.isArray(state.interests) ? state.interests : (state.interests.interests || []);
  const renderChips = (host, count = 5) => {
    if (!host) return;
    host.replaceChildren(...interests.slice(0, count).map((interest) => {
      const chip = document.createElement("span");
      chip.className = "topic-chip";
      chip.textContent = interest.topic;
      return chip;
    }));
  };
  renderChips($("#home-interest-list"), 3);
  renderChips($("#inspector-growth-interests"), 5);
  const leading = [...interests].sort((left, right) => Number(right.affinity ?? 50) - Number(left.affinity ?? 50))[0];
  $("#inspector-growth-title").textContent = leading ? `最在意 ${leading.topic}` : "还没有形成明确偏好";
  $("#inspector-growth-copy").textContent = leading?.reason || "兴趣会随着学习和经历继续变化";
  const coreCount = interests.filter((interest) => Boolean(interest.core)).length;
  const categoryCount = new Set(interests.map((interest) => String(interest.category || "未分类").trim() || "未分类")).size;
  const averageAffinity = interests.length
    ? Math.round(interests.reduce((sum, interest) => sum + Number(interest.affinity ?? 50), 0) / interests.length)
    : 0;
  setLeadingInterests(interests);
  $("#growth-interest-count").textContent = interests.length.toLocaleString("zh-CN");
  $("#growth-core-count").textContent = coreCount.toLocaleString("zh-CN");
  $("#growth-affinity-average").textContent = interests.length ? String(averageAffinity) : "--";
  $("#growth-interest-summary").textContent = interests.length
    ? `${coreCount} 个核心 · ${categoryCount} 个领域`
    : "还没有兴趣档案";

  $$('[data-interest-filter]').forEach((button) => {
    const active = button.dataset.interestFilter === state.interestFilter;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  const visibleInterests = interests.filter((interest) => interestMatchesFilter(interest, state.interestFilter));

  const editor = $("#interest-editor");
  if (!visibleInterests.length) {
    renderEmpty(editor, state.interestFilter === "all" ? "还没有形成兴趣档案" : "这个筛选下还没有兴趣");
    return;
  }
  const createInterestRow = (interest, index) => {
    const row = document.createElement("div");
    const presentation = interestPresentation(interest);
    row.className = `interest-row interest-tone-${presentation.tone}${interest.core ? " is-core" : ""}`;

    const topic = document.createElement("div");
    topic.className = "interest-topic";
    const topicIcon = document.createElement("span");
    topicIcon.className = "interest-topic-icon";
    topicIcon.innerHTML = `<i data-lucide="${presentation.icon}"></i>`;
    const topicCopy = document.createElement("div");
    const strong = document.createElement("strong");
    strong.textContent = interest.topic;
    const topicMeta = document.createElement("div");
    topicMeta.className = "interest-topic-meta";
    const category = document.createElement("span");
    category.textContent = interest.category || "未分类";
    topicMeta.append(category);
    if (interest.core) {
      const core = document.createElement("span");
      core.className = "interest-core-mark";
      core.textContent = "核心兴趣";
      topicMeta.append(core);
    }
    topicCopy.append(strong, topicMeta);
    topic.append(topicIcon, topicCopy);

    const affinity = document.createElement("div");
    affinity.className = "affinity-control";
    const affinityLabel = document.createElement("span");
    affinityLabel.className = "affinity-label";
    affinityLabel.textContent = interestAffinityLabel(interest.affinity ?? 50);
    const range = document.createElement("input");
    range.type = "range"; range.min = "0"; range.max = "100"; range.step = "1"; range.value = interest.affinity ?? 50;
    const output = document.createElement("output");
    const outputValue = document.createElement("strong");
    outputValue.textContent = range.value;
    const outputUnit = document.createElement("small");
    outputUnit.textContent = "/100";
    output.append(outputValue, outputUnit);
    range.addEventListener("input", () => {
      outputValue.textContent = range.value;
      affinityLabel.textContent = interestAffinityLabel(range.value);
      interest.affinity = Number(range.value);
    });
    affinity.append(affinityLabel, output, range);

    const reasonField = document.createElement("label");
    reasonField.className = "interest-reason-field";
    const reasonLabel = document.createElement("span");
    reasonLabel.textContent = "她为什么在意";
    const reason = document.createElement("textarea");
    reason.className = "interest-reason";
    reason.value = interest.reason || "";
    reason.maxLength = 500;
    reason.rows = 2;
    reason.addEventListener("input", () => { interest.reason = reason.value; });
    reason.dataset.index = index;
    reasonField.append(reasonLabel, reason);
    row.append(topic, affinity, reasonField);
    return row;
  };

  const groupedInterests = new Map();
  visibleInterests.forEach((interest, index) => {
    const category = normalizedInterestCategory(interest);
    const group = groupedInterests.get(category) || [];
    group.push({ interest, index });
    groupedInterests.set(category, group);
  });
  const categorySections = [...groupedInterests.entries()]
    .sort(([left], [right]) => interestCategoryRank(left) - interestCategoryRank(right) || left.localeCompare(right, "zh-CN"))
    .map(([category, entries], categoryIndex) => {
      entries.sort((left, right) => {
        const coreDifference = Number(Boolean(right.interest.core)) - Number(Boolean(left.interest.core));
        return coreDifference || Number(right.interest.affinity ?? 50) - Number(left.interest.affinity ?? 50);
      });
      const presentation = interestPresentation({ category });
      const average = Math.round(entries.reduce((sum, entry) => sum + Number(entry.interest.affinity ?? 50), 0) / entries.length);
      const section = document.createElement("section");
      section.className = `interest-category-section interest-tone-${presentation.tone}`;
      const heading = document.createElement("button");
      heading.type = "button";
      heading.className = "interest-category-heading";
      const gridId = `interest-category-${categoryIndex}`;
      const isOpen = state.openInterestCategories.has(category);
      heading.setAttribute("aria-controls", gridId);
      heading.setAttribute("aria-expanded", String(isOpen));
      const identity = document.createElement("div");
      const icon = document.createElement("span");
      icon.className = "interest-category-icon";
      icon.innerHTML = `<i data-lucide="${presentation.icon}"></i>`;
      const copy = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = category;
      const count = document.createElement("span");
      count.textContent = `${entries.length} 项兴趣`;
      copy.append(title, count);
      identity.append(icon, copy);
      const summary = document.createElement("span");
      summary.className = "interest-category-summary";
      summary.textContent = `平均热度 ${average}`;
      const actions = document.createElement("span");
      actions.className = "interest-category-actions";
      const chevron = document.createElement("span");
      chevron.className = "interest-category-chevron";
      chevron.innerHTML = '<i data-lucide="chevron-down"></i>';
      actions.append(summary, chevron);
      heading.append(identity, actions);
      const grid = document.createElement("div");
      grid.id = gridId;
      grid.className = "interest-category-grid";
      grid.hidden = !isOpen;
      grid.replaceChildren(...entries.map(({ interest, index }) => createInterestRow(interest, index)));
      heading.classList.toggle("is-open", isOpen);
      heading.addEventListener("click", () => {
        const nextOpen = heading.getAttribute("aria-expanded") !== "true";
        heading.setAttribute("aria-expanded", String(nextOpen));
        heading.classList.toggle("is-open", nextOpen);
        grid.hidden = !nextOpen;
        if (nextOpen) state.openInterestCategories.add(category);
        else state.openInterestCategories.delete(category);
      });
      section.append(heading, grid);
      return section;
    });
  editor.replaceChildren(...categorySections);
  iconRefresh();
}

function renderMood(mood = {}) {
  const feelings = [];
  if (Number(mood.curiosity) > 0.55) feelings.push("好奇");
  if (Number(mood.joy) > 0.45) feelings.push("心情不错");
  if (Number(mood.longing) > 0.55) feelings.push("有些向往");
  if (Number(mood.concern) > 0.45) feelings.push("有点担心");
  if (Number(mood.irritation) > 0.45) feelings.push("有点不爽");
  const summary = feelings.slice(0, 2).join("，") || "很平静";
  const cause = mood.recent_cause || "没有特别强烈的情绪波动";
  ["#home-mood-summary", "#inspector-mood-summary"].forEach((selector) => { $(selector).textContent = summary; });
  ["#home-mood-cause", "#inspector-mood-cause"].forEach((selector) => { $(selector).textContent = cause; });
  $("#rail-mood-dot").classList.toggle("attention", summary !== "很平静");
  $("#inspector-mood-button").title = `当前心情 · ${summary}`;
  $("#inspector-mood-button").setAttribute("aria-label", `查看当前心情：${summary}`);
}

function fillSettings(settings) {
  applyAssistantIdentity(settings);
  $$('[data-setting]').forEach((input) => {
    const value = settings[input.dataset.setting];
    if (input.type === "checkbox") input.checked = Boolean(value);
    else input.value = value ?? "";
  });
  syncVoiceLanguageControl();
  updateOwnerChanceLabel();
  renderOwnerAddressList();
  applyOwnerProfile(settings);
  syncWeatherCityPreset();
  fillLocalSettings();
}

function syncWeatherCityPreset() {
  const input = $("#weather-city-setting");
  const preset = $("#weather-city-preset");
  if (!input || !preset) return;
  const city = input.value.trim();
  const matched = Array.from(preset.options).some((option) => option.value === city);
  preset.value = matched ? city : "";
}

function chooseWeatherCityPreset(event) {
  const city = event.currentTarget.value;
  const input = $("#weather-city-setting");
  if (!city || !input) return;
  input.value = city;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.focus({ preventScroll: true });
}

function ownerProfile(settings = state.bootstrap?.settings || {}) {
  return {
    name: String(settings.owner_display_name || "主人").trim() || "主人",
    relationship: String(settings.owner_relationship || "创造者与重要的人").trim() || "创造者与重要的人",
    addresses: parseOwnerAddresses(settings.owner_addresses || "主人"),
  };
}

function applyOwnerProfile(settings = state.bootstrap?.settings || {}) {
  const profile = ownerProfile(settings);
  const ownerQq = String(state.bootstrap?.qq_identity?.owner_qq_id || "").trim();
  const memoryScope = $("#owner-memory-scope");
  if (memoryScope) {
    memoryScope.value = ownerQq ? `user:${ownerQq}` : "";
    memoryScope.textContent = `关于 ${profile.name}`;
    memoryScope.disabled = !ownerQq;
  }
  if ($("#persona-owner-summary")) $("#persona-owner-summary").textContent = `${profile.name} · ${profile.relationship}`;
  if ($("#inspector-owner-relationship")) $("#inspector-owner-relationship").textContent = `${profile.name} · ${profile.relationship}`;
  if ($("#autonomous-private-copy")) $("#autonomous-private-copy").textContent = `在合适的随机时间主动找 ${profile.name} 聊天`;
  tickClock();
}

function firstRunConnection(kind) {
  if (kind === "language") {
    return {
      provider_name: $("#first-run-language-provider").value.trim(),
      base_url: $("#first-run-language-base-url").value.trim(),
      api_key: $("#first-run-language-api-key").value.trim(),
      model: $("#first-run-language-model").value.trim(),
    };
  }
  const shared = state.firstRun.visionMode === "same";
  return {
    provider_name: shared ? $("#first-run-language-provider").value.trim() : $("#first-run-vision-provider").value.trim(),
    base_url: shared ? $("#first-run-language-base-url").value.trim() : $("#first-run-vision-base-url").value.trim(),
    api_key: shared ? $("#first-run-language-api-key").value.trim() : $("#first-run-vision-api-key").value.trim(),
    model: $("#first-run-vision-model").value.trim(),
  };
}

function firstRunConnectionSignature(connection) {
  return JSON.stringify([connection.base_url, connection.api_key, connection.model]);
}

function setFirstRunTestStatus(kind, status, title, detail) {
  const host = $(`#first-run-${kind}-status`);
  if (!host) return;
  const icons = { idle: "circle-dashed", busy: "loader-circle", ok: "circle-check-big", error: "circle-alert" };
  host.dataset.state = status;
  const icon = document.createElement("i"); icon.dataset.lucide = icons[status] || icons.idle;
  const copy = document.createElement("span");
  const strong = document.createElement("strong"); strong.textContent = title;
  const small = document.createElement("small"); small.textContent = detail;
  copy.append(strong, small); host.replaceChildren(icon, copy); iconRefresh();
}

function invalidateFirstRunModelTest(kind) {
  state.firstRun[`${kind}Test`] = null;
  setFirstRunTestStatus(
    kind,
    "idle",
    "等待检测",
    kind === "language" ? "检测通过后才能进入下一步" : "确认模型确实支持图片输入",
  );
  if (kind === "language" && state.firstRun.visionMode === "same") {
    state.firstRun.visionTest = null;
    setFirstRunTestStatus("vision", "idle", "等待检测", "语言接口已经变化，请重新检测视觉模型");
  }
}

function firstRunStatusRow({ title, detail, status, icon }) {
  const row = document.createElement("article");
  row.className = `first-run-${status.core ? "check" : "capability"}-item ${status.state}`;
  const mark = document.createElement("i"); const markIcon = document.createElement("i"); markIcon.dataset.lucide = icon; mark.append(markIcon);
  const copy = document.createElement("div"); const strong = document.createElement("strong"); strong.textContent = title; const small = document.createElement("small"); small.textContent = detail; copy.append(strong, small);
  const label = document.createElement("em"); label.textContent = status.label;
  row.append(mark, copy, label); return row;
}

function renderFirstRunEnvironment() {
  const core = [
    { title: "本地后端", detail: "昔夕的配置与数据服务可以正常访问", ready: Boolean(state.bootstrap?.status?.app?.online), icon: "server" },
    { title: "桌面运行外壳", detail: "PyWebView 与原生窗口通信已经建立", ready: Boolean(window.pywebview?.api), icon: "panel-top" },
    { title: "界面运行环境", detail: "WebView2 已经能够加载昔夕界面", ready: document.readyState !== "loading", icon: "app-window" },
    { title: "独立数据空间", detail: "聊天、记忆与设置保存在独立目录", ready: Boolean(state.bootstrap?.settings), icon: "database" },
  ];
  state.firstRun.coreReady = core.every((item) => item.ready);
  $("#first-run-core-checks").replaceChildren(...core.map((item) => firstRunStatusRow({
    title: item.title,
    detail: item.detail,
    icon: item.ready ? "check" : item.icon,
    status: { core: true, state: item.ready ? "ok" : "missing", label: item.ready ? "可以使用" : "正在连接" },
  })));

  const featureMeta = new Map(environmentFeatureCatalog.map((item) => [item.key, item]));
  const items = (state.firstRun.environment?.items || []).filter((item) => item.key !== "chat_model");
  $("#first-run-environment-list").replaceChildren(...items.map((item) => {
    const meta = featureMeta.get(item.key) || { title: item.key, icon: "box" };
    const ok = ["ok", "optional"].includes(item.state);
    return firstRunStatusRow({
      title: meta.title,
      detail: item.detail || "等待检查",
      icon: ok ? "check" : (meta.icon || "box"),
      status: {
        core: false,
        state: item.state === "optional" ? "optional" : (ok ? "ok" : "missing"),
        label: item.status_label || (ok ? "已就绪" : "可稍后安装"),
      },
    });
  }));
  iconRefresh();
  if (state.firstRun.step === 1) $("#first-run-footer-note").textContent = state.firstRun.coreReady ? "核心环境检查通过，可以继续" : "正在等待桌面环境连接";
}

async function refreshFirstRunEnvironment() {
  const button = $("#first-run-refresh-environment");
  if (button) button.disabled = true;
  try {
    state.firstRun.environment = await api("/api/environment", { timeoutMs: 20000 });
  } catch (error) {
    state.firstRun.environment = { items: [] };
    toast(`环境检查未完全完成：${error.message}`, "error");
  } finally {
    renderFirstRunEnvironment();
    if (button) button.disabled = false;
  }
}

function setFirstRunVisionMode(mode) {
  state.firstRun.visionMode = mode === "separate" ? "separate" : "same";
  $$('[data-first-run-vision-mode]').forEach((button) => button.classList.toggle("active", button.dataset.firstRunVisionMode === state.firstRun.visionMode));
  $("#first-run-vision-separate-fields").hidden = state.firstRun.visionMode !== "separate";
  $("#first-run-vision-shared-note").hidden = state.firstRun.visionMode !== "same";
  invalidateFirstRunModelTest("vision");
}

function syncFirstRunVisionEnabled() {
  const enabled = $("#first-run-vision-enabled").checked;
  $("#first-run-vision-fields").hidden = !enabled;
  $("#first-run-vision-disabled-note").hidden = enabled;
  if (!enabled) state.firstRun.visionTest = null;
}

function syncFirstRunQqEnabled() {
  $("#first-run-qq-fields").hidden = !$("#first-run-feature-qq").checked;
}

async function discoverFirstRunModels(kind) {
  const connection = firstRunConnection(kind);
  if (!connection.base_url) throw new Error("请先填写 API 地址");
  const button = $(`#first-run-${kind}-discover`); button.disabled = true;
  try {
    const result = await api("/api/model/providers/discover", {
      method: "POST",
      body: JSON.stringify({ base_url: connection.base_url, api_key: connection.api_key }),
      timeoutMs: 30000,
    });
    const options = (result.models || []).map((model) => {
      const option = document.createElement("option"); option.value = model.id; option.label = model.name || model.id; return option;
    });
    $(`#first-run-${kind}-model-options`).replaceChildren(...options);
    if (result.base_url) {
      const input = kind === "language" || state.firstRun.visionMode === "same"
        ? $("#first-run-language-base-url") : $("#first-run-vision-base-url");
      input.value = result.base_url;
      invalidateFirstRunModelTest(kind === "vision" && state.firstRun.visionMode === "same" ? "language" : kind);
    }
    if (options.length === 1) $(`#first-run-${kind}-model`).value = options[0].value;
    toast(options.length ? `已获取 ${options.length} 个模型` : "接口没有返回模型目录，可以手动填写模型 ID");
  } finally {
    button.disabled = false;
  }
}

async function testFirstRunModel(kind) {
  const connection = firstRunConnection(kind);
  if (!connection.provider_name) throw new Error("请填写供应商名称");
  if (!connection.base_url || !connection.model) throw new Error("请填写 API 地址和模型 ID");
  const button = $(`#first-run-${kind}-test`); button.disabled = true;
  setFirstRunTestStatus(kind, "busy", "正在检测", "正在识别接口类型并发送最小测试请求");
  try {
    const result = await api("/api/model/connection/test", {
      method: "POST",
      body: JSON.stringify({ target: kind, connection }),
      timeoutMs: 35000,
    });
    state.firstRun[`${kind}Test`] = { signature: firstRunConnectionSignature(connection), result };
    setFirstRunTestStatus(kind, "ok", "连接成功", `${result.api_label || result.provider || "接口已识别"} · ${result.model || connection.model}`);
  } catch (error) {
    state.firstRun[`${kind}Test`] = null;
    setFirstRunTestStatus(kind, "error", "连接失败", error.message);
    throw error;
  } finally {
    button.disabled = false;
  }
}

function validateFirstRunStep(step) {
  if (step === 1 && !state.firstRun.coreReady) throw new Error("桌面环境还没有连接完成，请重新检查");
  if (step === 2) {
    const current = firstRunConnection("language");
    if (!state.firstRun.languageTest || state.firstRun.languageTest.signature !== firstRunConnectionSignature(current)) throw new Error("请先检测并确认语言模型可用");
  }
  if (step === 3 && $("#first-run-vision-enabled").checked) {
    const current = firstRunConnection("vision");
    if (!state.firstRun.visionTest || state.firstRun.visionTest.signature !== firstRunConnectionSignature(current)) throw new Error("请先检测视觉模型，或者关闭图片理解");
  }
  if (step === 4) {
    if (!$("#first-run-owner-name").value.trim() || !$("#first-run-owner-addresses").value.trim() || !$("#first-run-owner-relationship").value.trim()) throw new Error("请填写显示名称、称呼和关系");
  }
  if (step === 5) {
    if ($("#first-run-feature-weather").checked && !$("#first-run-city").value.trim()) throw new Error("启用天气提醒前请先填写城市");
    if ($("#first-run-feature-qq").checked) {
      const ownerQq = $("#first-run-owner-qq").value.trim(); const botQq = $("#first-run-bot-qq").value.trim();
      if (!/^[1-9]\d{4,11}$/.test(ownerQq) || !/^[1-9]\d{4,11}$/.test(botQq)) throw new Error("启用 QQ 时，请填写两个 5 到 12 位 QQ 号");
      if (ownerQq === botQq) throw new Error("使用者 QQ 和昔夕登录 QQ 不能相同");
    }
  }
  return true;
}

function renderFirstRunSummary() {
  const language = firstRunConnection("language"); const visionEnabled = $("#first-run-vision-enabled").checked; const vision = firstRunConnection("vision");
  const features = [
    [$("#first-run-feature-voice").checked, "语音"], [$("#first-run-feature-learning").checked, "持续学习"],
    [$("#first-run-feature-search").checked, "联网搜索"], [$("#first-run-feature-weather").checked, "天气提醒"], [$("#first-run-feature-qq").checked, "QQ"],
  ].filter(([enabled]) => enabled).map(([, label]) => label);
  const rows = [
    ["brain-circuit", "语言模型", `${language.provider_name} · ${language.model}`, "已检测"],
    ["scan-eye", "视觉模型", visionEnabled ? `${vision.provider_name} · ${vision.model}` : "暂不启用图片理解", visionEnabled ? "已检测" : "已跳过"],
    ["heart-handshake", "关系资料", `${$("#first-run-owner-name").value.trim()} · ${$("#first-run-owner-relationship").value.trim()}`, "已填写"],
    ["sliders-horizontal", "初始能力", features.join("、") || "全部保持关闭", `${features.length} 项启用`],
    ["hard-drive", "本地数据", "使用独立数据目录保存聊天、记忆与设置", "已隔离"],
  ];
  $("#first-run-summary").replaceChildren(...rows.map(([iconName, title, detail, label]) => {
    const row = document.createElement("div"); row.className = "first-run-summary-row";
    const icon = document.createElement("i"); icon.dataset.lucide = iconName;
    const copy = document.createElement("div"); const strong = document.createElement("strong"); strong.textContent = title; const small = document.createElement("small"); small.textContent = detail; copy.append(strong, small);
    const stateLabel = document.createElement("span"); stateLabel.textContent = label; row.append(icon, copy, stateLabel); return row;
  }));
  iconRefresh();
}

function setFirstRunStep(step) {
  const nextStep = Math.max(1, Math.min(6, Number(step) || 1));
  state.firstRun.step = nextStep;
  const meta = firstRunStepMeta[nextStep - 1];
  $$("[data-first-run-page]").forEach((page) => page.classList.toggle("active", Number(page.dataset.firstRunPage) === nextStep));
  $$('[data-first-run-nav]').forEach((item) => { const index = Number(item.dataset.firstRunNav); item.classList.toggle("active", index === nextStep); item.classList.toggle("complete", index < nextStep); });
  $$("#first-run-dialog .first-run-progress i").forEach((segment, index) => { segment.classList.toggle("active", index === nextStep - 1); segment.classList.toggle("complete", index < nextStep - 1); });
  $("#first-run-step-icon").setAttribute("data-lucide", meta.icon); $("#first-run-title").textContent = meta.title; $("#first-run-subtitle").textContent = meta.subtitle; $("#first-run-count").textContent = `${nextStep} / 6`; $("#first-run-footer-note").textContent = meta.note;
  $("#first-run-back").hidden = nextStep === 1; $("#first-run-next").hidden = nextStep === 6; $("#first-run-finish").hidden = nextStep !== 6;
  if (nextStep === 6) renderFirstRunSummary();
  $("#first-run-dialog .first-run-content").scrollTop = 0; iconRefresh();
}

function firstRunProviderName(baseUrl, fallback) {
  try { return new URL(baseUrl).hostname || fallback; }
  catch { return fallback; }
}

function openFirstRunSetup(settings = {}) {
  const dialog = $("#first-run-dialog");
  if (settings.setup_complete) {
    state.firstRun.active = false;
    document.body.classList.remove("app-booting", "first-run-active");
    if (dialog?.open) dialog.close();
    return;
  }
  state.firstRun.active = true;
  document.body.classList.remove("app-booting"); document.body.classList.add("first-run-active");
  const connection = state.bootstrap?.model_connection || {};
  const language = connection.language || {}; const vision = connection.vision || {};
  $("#first-run-language-provider").value = language.base_url ? firstRunProviderName(language.base_url, "模型供应商") : "";
  $("#first-run-language-base-url").value = language.base_url || ""; $("#first-run-language-api-key").value = ""; $("#first-run-language-api-key").placeholder = language.api_key_configured ? "密钥已保存，留空则继续使用" : "本地无鉴权接口可以留空"; $("#first-run-language-model").value = language.model || "";
  $("#first-run-vision-provider").value = vision.base_url ? firstRunProviderName(vision.base_url, "视觉供应商") : ""; $("#first-run-vision-base-url").value = vision.base_url || ""; $("#first-run-vision-api-key").value = ""; $("#first-run-vision-api-key").placeholder = vision.api_key_configured ? "密钥已保存，留空则继续使用" : "本地无鉴权接口可以留空"; $("#first-run-vision-model").value = vision.model || "";
  $("#first-run-owner-name").value = settings.owner_display_name === "主人" ? "" : (settings.owner_display_name || ""); $("#first-run-owner-addresses").value = settings.owner_addresses === "主人" ? "" : (settings.owner_addresses || ""); $("#first-run-owner-relationship").value = settings.owner_relationship || "创造者与重要的人"; $("#first-run-city").value = settings.weather_location === "未设置" ? "" : (settings.weather_location || "");
  $("#first-run-owner-qq").value = state.bootstrap?.qq_identity?.owner_qq_id || ""; $("#first-run-bot-qq").value = state.bootstrap?.qq_identity?.bot_qq_id || "";
  $("#first-run-feature-voice").checked = true; $("#first-run-feature-learning").checked = true; $("#first-run-feature-search").checked = true; $("#first-run-feature-weather").checked = Boolean(settings.weather_alert_enabled); $("#first-run-feature-qq").checked = Boolean(settings.qq_enabled);
  $("#first-run-vision-enabled").checked = true;
  setFirstRunVisionMode(language.base_url && vision.base_url && language.base_url !== vision.base_url ? "separate" : "same"); syncFirstRunVisionEnabled(); syncFirstRunQqEnabled();
  if (!dialog.open) dialog.showModal();
  setFirstRunStep(1); renderFirstRunEnvironment(); void refreshFirstRunEnvironment();
}

async function completeFirstRun(event) {
  event.preventDefault();
  if (state.firstRun.step !== 6) {
    validateFirstRunStep(state.firstRun.step);
    setFirstRunStep(state.firstRun.step + 1);
    return;
  }
  validateFirstRunStep(2); validateFirstRunStep(3); validateFirstRunStep(4); validateFirstRunStep(5);
  if (state.firstRun.busy) return;
  state.firstRun.busy = true;
  const finish = $("#first-run-finish"); finish.disabled = true; $("#first-run-back").disabled = true; $("#first-run-finish-status").hidden = false;
  try {
    const language = firstRunConnection("language");
    await api("/api/model/connection/apply", { method: "POST", body: JSON.stringify({ target: "language", provider_id: "first-run-primary", provider_name: language.provider_name, connection: language }), timeoutMs: 60000 });
    const visionEnabled = $("#first-run-vision-enabled").checked;
    if (visionEnabled) {
      const vision = firstRunConnection("vision");
      await api("/api/model/connection/apply", { method: "POST", body: JSON.stringify({ target: "vision", provider_id: state.firstRun.visionMode === "same" ? "first-run-primary" : "first-run-vision", provider_name: vision.provider_name, connection: vision }), timeoutMs: 60000 });
    }
    const city = $("#first-run-city").value.trim(); const qqEnabled = $("#first-run-feature-qq").checked;
    const values = {
      owner_display_name: $("#first-run-owner-name").value.trim(), owner_addresses: $("#first-run-owner-addresses").value.trim(), owner_relationship: $("#first-run-owner-relationship").value.trim(),
      brain_enabled: true, vision_enabled: visionEnabled, voice_enabled: $("#first-run-feature-voice").checked,
      learning_enabled: $("#first-run-feature-learning").checked, anime_learning_enabled: $("#first-run-feature-learning").checked,
      web_search_enabled: $("#first-run-feature-search").checked, weather_enabled: Boolean(city), weather_alert_enabled: $("#first-run-feature-weather").checked,
      qq_enabled: qqEnabled,
    };
    if (city) values.weather_location = city;
    await api("/api/settings", { method: "PUT", body: JSON.stringify(values) });
    if (qqEnabled) await api("/api/qq/identity", { method: "PUT", body: JSON.stringify({ owner_qq_id: $("#first-run-owner-qq").value.trim(), bot_qq_id: $("#first-run-bot-qq").value.trim() }) });
    await api("/api/settings", { method: "PUT", body: JSON.stringify({ setup_complete: true }) });
    const refreshed = await loadBootstrap();
    if (!refreshed) throw new Error("配置已经保存，但界面重新载入失败，请重启昔夕");
    setView("home"); toast("首次配置完成，欢迎来到昔夕");
  } catch (error) {
    $("#first-run-finish-status").hidden = true; toast(`配置未完成：${error.message}`, "error");
  } finally {
    state.firstRun.busy = false; finish.disabled = false; $("#first-run-back").disabled = false;
  }
}

function syncVoiceLanguageControl() {
  const input = $('[data-setting="voice_language"]');
  const language = ["zh", "ja", "en"].includes(input?.value) ? input.value : "zh";
  const prewarm = state.status?.voice?.prewarm;
  $$('[data-voice-language]').forEach((button) => {
    const active = button.dataset.voiceLanguage === language;
    const warming = active && prewarm?.state === "warming" && prewarm.language === language;
    button.classList.toggle("active", active);
    button.classList.toggle("warming", warming);
    button.setAttribute("aria-checked", String(active));
    button.setAttribute("aria-busy", String(warming));
  });
}

function watchVoicePrewarm() {
  if (state.voicePrewarmTimer) clearTimeout(state.voicePrewarmTimer);
  const poll = async () => {
    const status = await loadStatus();
    if (status?.voice?.prewarm?.state === "warming") {
      state.voicePrewarmTimer = setTimeout(poll, 1200);
    } else {
      state.voicePrewarmTimer = null;
    }
  };
  state.voicePrewarmTimer = setTimeout(poll, 250);
}

async function setVoiceLanguage(language) {
  const input = $('[data-setting="voice_language"]');
  const normalized = ["zh", "ja", "en"].includes(language) ? language : "zh";
  if (!input || state.voiceLanguageBusy) return false;
  const previous = ["zh", "ja", "en"].includes(input.value) ? input.value : "zh";
  if (normalized === previous && state.bootstrap?.settings?.voice_language === normalized) {
    return true;
  }

  state.voiceLanguageBusy = true;
  input.value = normalized;
  $$('[data-voice-language]').forEach((button) => { button.disabled = true; });
  syncVoiceLanguageControl();
  try {
    const applied = await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ voice_language: normalized }),
      timeoutMs: 10_000,
    });
    if (state.bootstrap?.settings) Object.assign(state.bootstrap.settings, applied);
    const label = { zh: "中文", ja: "日语", en: "英语" }[normalized];
    toast(`语音已切换为${label}，声线正在后台准备`);
    watchVoicePrewarm();
    return true;
  } catch (error) {
    input.value = previous;
    syncVoiceLanguageControl();
    toast(`语音语言切换失败：${error.message}`, "error");
    return false;
  } finally {
    state.voiceLanguageBusy = false;
    $$('[data-voice-language]').forEach((button) => { button.disabled = false; });
  }
}

function fillModelConnection(connection = {}) {
  const language = connection.language || {
    base_url: connection.base_url || "",
    api_key_configured: connection.api_key_configured,
    model: connection.language_model || state.bootstrap?.settings?.openai_model || "",
    api_type: connection.provider || "auto",
    api_label: "等待自动识别",
  };
  const vision = connection.vision || {
    base_url: connection.base_url || "",
    api_key_configured: connection.api_key_configured,
    model: connection.vision_model || state.bootstrap?.settings?.vision_model || "",
    api_type: "auto",
    api_label: "等待自动识别",
  };
  $("#active-model-name").textContent = language.model || "尚未配置";
  $("#active-model-provider").textContent = modelEndpointSummary(language);
  $("#active-vision-model-name").textContent = vision.model || "尚未配置";
  $("#active-vision-model-provider").textContent = modelEndpointSummary(vision);
  $("#active-model-dot").classList.toggle("online", Boolean(language.base_url && language.model && vision.base_url && vision.model));
}

function modelEndpointSummary(endpoint = {}) {
  const label = endpoint.api_label || "等待自动识别";
  return endpoint.base_url ? `${label} · ${endpoint.base_url}` : label;
}

function parsePersonaContent(content = "") {
  const lines = String(content || "").replace(/\r\n?/g, "\n").split("\n");
  const headingPattern = /^([^\s-][^：\n]{0,40})：\s*$/;
  const draft = { intro: [], sections: [] };
  let current = draft.intro;
  lines.forEach((line) => {
    const match = line.match(headingPattern);
    if (match) {
      const section = { title: match[1].trim(), lines: [] };
      draft.sections.push(section);
      current = section.lines;
    } else {
      current.push(line);
    }
  });
  return {
    intro: draft.intro.join("\n").trim(),
    sections: draft.sections.map((section) => ({ title: section.title, content: section.lines.join("\n").trim() })),
  };
}

function serializePersonaDraft(draft = state.personaDraft) {
  if (!draft) return "";
  const blocks = [];
  if (draft.intro?.trim()) blocks.push(draft.intro.trim());
  (draft.sections || []).forEach((section) => {
    const content = String(section.content || "").trim();
    if (content) blocks.push(`${section.title}：\n${content}`);
  });
  return blocks.join("\n\n").trim();
}

function personaSectionValue(key) {
  if (key === "__intro__") return state.personaDraft?.intro || "";
  return state.personaDraft?.sections?.find((section) => section.title === key)?.content || "";
}

function updatePersonaSection(key, value) {
  if (!state.personaDraft) state.personaDraft = parsePersonaContent("");
  if (key === "__intro__") {
    state.personaDraft.intro = value;
    return;
  }
  const section = state.personaDraft.sections.find((candidate) => candidate.title === key);
  if (section) section.content = value;
  else state.personaDraft.sections.push({ title: key, content: value });
}

function updatePersonaCharacterCount() {
  const raw = $("#persona-editor");
  const count = $("#persona-character-count");
  if (raw && count) count.textContent = `${raw.value.length.toLocaleString("zh-CN")} 字`;
}

function syncPersonaRawEditor() {
  const raw = $("#persona-editor");
  if (raw) raw.value = serializePersonaDraft();
  updatePersonaCharacterCount();
}

function renderPersonaStructuredFields() {
  const host = $("#persona-structured-editor");
  if (!host) return;
  host.replaceChildren();
  personaEditorGroups.forEach((group) => {
    const pane = document.createElement("div");
    pane.className = "persona-editor-pane";
    pane.dataset.personaPane = group.id;
    pane.hidden = state.personaEditorTab !== group.id;
    const stack = document.createElement("div");
    stack.className = "persona-field-stack";
    group.sections.forEach((definition) => {
      const block = document.createElement("article");
      block.className = "persona-field-block";
      const heading = document.createElement("div");
      heading.className = "persona-field-heading";
      const label = document.createElement("strong");
      label.textContent = assistantText(definition.label);
      const hint = document.createElement("span");
      hint.textContent = assistantText(definition.hint);
      heading.append(label, hint);
      const textarea = document.createElement("textarea");
      textarea.dataset.personaSection = definition.key;
      textarea.spellcheck = false;
      textarea.value = personaSectionValue(definition.key);
      textarea.rows = Math.min(14, Math.max(4, Math.ceil(Math.max(textarea.value.length, 160) / 80)));
      textarea.addEventListener("input", () => {
        updatePersonaSection(definition.key, textarea.value);
        syncPersonaRawEditor();
      });
      block.append(heading, textarea);
      stack.append(block);
    });
    pane.append(stack);
    host.append(pane);
  });
}

function activatePersonaTab(tab) {
  if (!personaEditorGroups.some((group) => group.id === tab) && tab !== "raw") return;
  if (state.personaEditorTab === "raw" && tab !== "raw") {
    state.personaDraft = parsePersonaContent($("#persona-editor")?.value || "");
    renderPersonaStructuredFields();
  }
  if (tab === "raw") syncPersonaRawEditor();
  state.personaEditorTab = tab;
  $$('[data-persona-tab]').forEach((button) => {
    const active = button.dataset.personaTab === tab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  $$('[data-persona-pane]').forEach((pane) => { pane.hidden = pane.dataset.personaPane !== tab; });
  updatePersonaCharacterCount();
}

function loadPersonaDraft(content, saved = true) {
  state.personaDraft = parsePersonaContent(content);
  if (saved) state.personaSavedContent = serializePersonaDraft();
  const raw = $("#persona-editor");
  if (raw) raw.value = serializePersonaDraft();
  renderPersonaStructuredFields();
  activatePersonaTab(state.personaEditorTab || "identity");
  updatePersonaCharacterCount();
}

function currentPersonaContent() {
  if (state.personaEditorTab === "raw") state.personaDraft = parsePersonaContent($("#persona-editor")?.value || "");
  return serializePersonaDraft();
}

function downloadPersonaFile(filename, body, type) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([body], { type }));
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

function exportPersonaCard() {
  const content = currentPersonaContent();
  const card = { format: "xixi-persona-card", version: 1, name: characterName(), exported_at: new Date().toISOString(), content };
  downloadPersonaFile(`${characterName()}-角色卡.json`, JSON.stringify(card, null, 2), "application/json;charset=utf-8");
  toast("角色卡已导出");
}

async function importPersonaFile(file) {
  if (!file) return;
  try {
    if (file.size > 160_000) throw new Error("角色卡超过 160 KB，无法载入");
    let content = await file.text();
    if (file.name.toLowerCase().endsWith(".json")) {
      const payload = JSON.parse(content);
      content = payload.content || payload.persona?.content || payload.card?.content || "";
    }
    if (!String(content).trim()) throw new Error("角色卡中没有找到人格文本");
    loadPersonaDraft(content, false);
    toast("角色卡已载入草稿，保存后才会生效");
  } catch (error) {
    toast(`角色卡导入失败：${error.message}`, "error");
  }
}

function showBootstrapFailure(error) {
  const screen = $("#boot-error-screen");
  const message = $("#boot-error-message");
  if (message) message.textContent = error?.message || "本地服务还没有准备好，请稍等片刻后重试。";
  if (screen) screen.hidden = false;
  document.body.classList.add("app-booting", "boot-failed");
  iconRefresh();
}

function hideBootstrapFailure() {
  $("#boot-error-screen")?.setAttribute("hidden", "");
  document.body.classList.remove("boot-failed");
}

async function loadBootstrap({ critical = false } = {}) {
  try {
    const data = await api("/api/bootstrap");
    state.bootstrap = data;
    if (!data.settings?.setup_complete) {
      window.location.replace("/setup.html");
      return null;
    }
    applyAssistantIdentity(data.settings || {});
    renderStatus(data.status);
    renderInterests(data.interests);
    renderHomeSnapshot(data.home);
    renderHomeAgent(data.agent || {});
    fillSettings(data.settings);
    fillModelConnection(data.model_connection || {});
    fillQqIdentity(data.qq_identity || {}, { force: true });
    loadPersonaDraft(data.persona.content);
    renderMood(data.mood);
    if (data.agent) renderAgentDashboard(data.agent);
    if (data.dependencies) renderDependencies(data.dependencies);
    applyOwnerProfile(data.settings || {});
    hideBootstrapFailure();
    document.body.classList.remove("app-booting", "first-run-active");
    return data;
  } catch (error) {
    if (critical) showBootstrapFailure(error);
    else toast(error.message, "error");
    return null;
  }
}

function qqIdentityPayload() {
  return {
    bot_qq_id: $("#bot-qq-id").value.trim(),
    owner_qq_id: $("#owner-qq-id").value.trim(),
  };
}

function fillQqIdentity(identity = {}, { force = false } = {}) {
  if (force || (!state.qqIdentityDirty && !state.qqAccountBusy)) {
    $("#bot-qq-id").value = identity.bot_qq_id || "";
    $("#owner-qq-id").value = identity.owner_qq_id || "";
  }
  const actual = $("#qq-actual-account");
  const match = $("#qq-account-match");
  actual.textContent = identity.actual_online
    ? `${identity.actual_nickname || "QQ"} · ${identity.actual_user_id}`
    : "未登录";
  match.dataset.state = identity.actual_online
    ? (identity.account_matches ? "online" : "warning")
    : "offline";
  match.textContent = identity.actual_online
    ? (identity.account_matches ? "账号一致" : "账号不一致")
    : "未连接";
}

function validateQqIdentity(identity) {
  if (!/^[1-9]\d{4,11}$/.test(identity.bot_qq_id)) throw new Error("昔夕登录 QQ 必须是 5 到 12 位数字");
  if (!/^[1-9]\d{4,11}$/.test(identity.owner_qq_id)) throw new Error("主人 QQ 必须是 5 到 12 位数字");
}

function updateQqIdentityNote(qq = state.status?.qq) {
  const note = $("#qq-identity-note");
  if (!note || !qq) return;
  if (qq.account_state === "switching") {
    note.textContent = `正在退出旧账号并切换到 ${qq.account_target}……`;
  } else if (qq.account_state === "waiting_login") {
    note.textContent = `等待 ${qq.account_target} 登录，请留意 QQ 登录窗口或二维码。`;
  } else if (qq.account_state === "starting") {
    note.textContent = `正在启动${characterName()} QQ ${qq.account_target}……`;
  } else if (qq.account_state === "error") {
    note.textContent = `换号失败：${qq.account_error || "请检查 NapCat 登录状态"}`;
  } else if (qq.online && qq.account_target) {
    note.textContent = `${qq.account_target} 已登录，${characterName()} QQ 在线。`;
  } else {
    note.textContent = `换号会结束当前${characterName()}专用 QQ 进程并等待新账号登录，不会关闭普通 QQ 客户端。`;
  }
}

async function monitorQqAccountSwitch(targetQq, generation) {
  const deadline = Date.now() + 130_000;
  while (Date.now() < deadline && generation === state.qqAccountMonitorGeneration) {
    const status = await loadStatus();
    const qq = status?.qq;
    updateQqIdentityNote(qq);
    if (!qq) break;
    if (qq.account_state === "online" && qq.configured_user_id === targetQq) {
      state.qqAccountBusy = false;
      if (state.bootstrap?.qq_identity) {
        state.bootstrap.qq_identity.bot_qq_id = targetQq;
        state.bootstrap.qq_identity.owner_qq_id = qq.owner_user_id || state.bootstrap.qq_identity.owner_qq_id;
        state.qqIdentityDirty = false;
        fillQqIdentity(state.bootstrap.qq_identity, { force: true });
      }
      toast("新 QQ 已登录并成为昔夕账号");
      break;
    }
    if (qq.account_state === "error" || qq.account_state === "idle") {
      state.qqAccountBusy = false;
      if (qq.account_state === "error") toast(qq.account_error || "QQ 换号失败", "error");
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  if (generation === state.qqAccountMonitorGeneration) {
    state.qqAccountBusy = false;
    $("#save-qq-identity").disabled = false;
    $("#switch-qq-account").disabled = false;
    updateQqIdentityNote();
    iconRefresh();
  }
}

async function updateQqIdentity(switchAccount) {
  if (state.qqAccountBusy) return false;
  const identity = qqIdentityPayload();
  try { validateQqIdentity(identity); } catch (error) { toast(error.message, "error"); return false; }
  if (switchAccount && !window.confirm(`切换昔夕登录 QQ 为 ${identity.bot_qq_id}？\n\n当前昔夕专用 QQ 进程会退出，随后请按登录窗口提示完成登录。`)) return false;
  const saveButton = $("#save-qq-identity");
  const switchButton = $("#switch-qq-account");
  const note = $("#qq-identity-note");
  state.qqAccountBusy = true;
  let backgroundSwitchStarted = false;
  saveButton.disabled = true;
  switchButton.disabled = true;
  note.textContent = switchAccount ? "正在切换账号并等待登录，请留意 QQ 登录窗口……" : "正在保存本机身份配置……";
  try {
    const result = await api(switchAccount ? "/api/qq/account/switch" : "/api/qq/identity", {
      method: switchAccount ? "POST" : "PUT",
      body: JSON.stringify(identity),
    });
    if (!switchAccount) {
      state.bootstrap.qq_identity = result.qq_identity;
      state.qqIdentityDirty = false;
      fillQqIdentity(result.qq_identity, { force: true });
    }
    await loadStatus();
    if (switchAccount) {
      const generation = ++state.qqAccountMonitorGeneration;
      backgroundSwitchStarted = true;
      toast("换号已开始，请按 QQ 提示完成登录");
      monitorQqAccountSwitch(identity.bot_qq_id, generation);
      return true;
    }
    toast("QQ 身份配置已保存");
    return true;
  } catch (error) {
    toast(error.message, "error");
    return false;
  } finally {
    if (!backgroundSwitchStarted) {
      state.qqAccountBusy = false;
      saveButton.disabled = false;
      switchButton.disabled = false;
      updateQqIdentityNote();
      iconRefresh();
    }
  }
}

async function loadStatus() {
  try {
    const status = await api("/api/status", { timeoutMs: 5000 });
    renderStatus(status);
    return status;
  } catch (error) {
    toast(error.message, "error");
    return null;
  }
}

function createAdvancedStateBadge(item = {}) {
  const badge = document.createElement("span");
  badge.className = "advanced-state-badge";
  badge.dataset.state = item.state || "neutral";
  badge.textContent = item.status || "未知";
  return badge;
}

function renderAdvancedRows(host, items = []) {
  if (!host) return;
  if (!items.length) {
    const empty = document.createElement("span");
    empty.className = "advanced-loading";
    empty.textContent = "没有可显示的信息";
    host.replaceChildren(empty);
    return;
  }
  host.replaceChildren(...items.map((item) => {
    const row = document.createElement("article");
    row.className = "advanced-info-row";
    row.dataset.advancedKey = item.key || "";
    const copy = document.createElement("div");
    const label = document.createElement("strong");
    label.textContent = item.label || "未命名项目";
    const detail = document.createElement("span");
    detail.textContent = item.detail || "暂无详情";
    copy.append(label, detail);
    row.append(copy, createAdvancedStateBadge(item));
    return row;
  }));
}

function renderAdvancedPaths(items = []) {
  const host = $("#advanced-path-list");
  if (!host) return;
  host.replaceChildren(...items.map((item) => {
    const row = document.createElement("article");
    row.className = "advanced-path-row";
    const heading = document.createElement("div");
    const label = document.createElement("strong");
    label.textContent = item.label || "未命名路径";
    const stateLabel = document.createElement("span");
    stateLabel.className = "advanced-path-state";
    stateLabel.dataset.state = item.exists ? "online" : "attention";
    stateLabel.textContent = item.exists ? "存在" : "未创建";
    heading.append(label, stateLabel);

    const value = document.createElement("div");
    value.className = "advanced-path-value";
    const input = document.createElement("input");
    input.type = "text";
    input.readOnly = true;
    input.value = item.path || "";
    input.setAttribute("aria-label", `${item.label || "本地"}路径`);
    const copyButton = document.createElement("button");
    copyButton.className = "icon-button advanced-copy-button";
    copyButton.type = "button";
    copyButton.dataset.copyPath = item.path || "";
    copyButton.title = `复制${item.label || ""}路径`;
    copyButton.setAttribute("aria-label", copyButton.title);
    const icon = document.createElement("i");
    icon.dataset.lucide = "copy";
    copyButton.append(icon);
    value.append(input, copyButton);
    row.append(heading, value);
    return row;
  }));
}

function renderAdvancedInfo(payload = {}) {
  state.advancedInfo = payload;
  const buildDate = new Date(payload.build_time || "");
  $("#advanced-build-time").textContent = Number.isNaN(buildDate.getTime())
    ? `${characterName()} Studio ${payload.release || "本地版"}`
    : `当前构建更新于 ${buildDate.toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}`;
  renderAdvancedRows($("#advanced-identity-list"), payload.identity || []);

  const windows = [...(payload.windows || [])];
  if (!windows.some((item) => item.key === "desktop-window")) {
    const desktopClient = Boolean(window.pywebview?.api);
    windows.unshift({
      key: desktopClient ? "current-desktop" : "current-browser",
      label: desktopClient ? "xixi-desktop" : "xixi-web",
      detail: `${desktopClient ? "PyWebView" : "浏览器窗口"} · ${window.innerWidth} × ${window.innerHeight}`,
      status: document.hidden ? "后台" : "可见",
      state: document.hidden ? "paused" : "online",
    });
  }
  renderAdvancedRows($("#advanced-window-list"), windows);
  const visibleWindows = windows.filter((item) => item.status === "可见").length;
  $("#advanced-window-summary").textContent = `${windows.length} 个运行项 · ${visibleWindows} 个可见窗口`;

  renderAdvancedRows($("#advanced-service-list"), payload.services || []);
  renderAdvancedPaths(payload.paths || []);
  iconRefresh();
}

async function loadAdvancedSettings() {
  const button = $("#refresh-advanced");
  if (button) {
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
  }
  try {
    const payload = await api("/api/advanced", { timeoutMs: 6000 });
    renderAdvancedInfo(payload);
  } catch (error) {
    toast(`高级设置读取失败：${error.message}`, "error");
  } finally {
    if (button) {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }
  }
}

async function copyAdvancedPath(path) {
  if (!path) return;
  try {
    await navigator.clipboard.writeText(path);
    toast("路径已复制");
  } catch {
    toast("无法访问剪贴板", "error");
  }
}

async function monitorQqControl(action, generation) {
  const deadline = Date.now() + (action === "online" ? 620_000 : 20_000);
  while (Date.now() < deadline && generation === state.qqAccountMonitorGeneration) {
    const status = await loadStatus();
    const qq = status?.qq;
    if (!qq) break;
    if (action === "online" && qq.online) {
      toast("昔夕 QQ 已上线");
      return;
    }
    if (action === "offline" && !qq.enabled && !qq.napcat_online) {
      toast("昔夕 QQ 已完全下线");
      return;
    }
    if (qq.account_state === "error") {
      toast(qq.account_error || "QQ 操作失败", "error");
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}

async function controlQqAction(action) {
  if (state.qqControlBusy) return;
  const button = $("#toggle-qq");
  state.qqControlBusy = true;
  if (button) {
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
  }
  try {
    const result = await api("/api/qq/control", {
      method: "POST",
      body: JSON.stringify({ action }),
      timeoutMs: 20000,
    });
    if (result?.qq) renderStatus({ ...state.status, qq: result.qq });
    const status = result?.qq || state.status?.qq;
    const generation = ++state.qqAccountMonitorGeneration;
    const settled = action === "online"
      ? Boolean(status?.online)
      : Boolean(status && !status.enabled && !status.napcat_online && !status.qq_process_online && !status.process_online);
    if (action === "online") {
      toast(status?.online ? "昔夕 QQ 已上线" : "上线请求已接受，正在后台连接");
      if (!status?.online) setTimeout(openQqQrDialog, 150);
    } else {
      state.qqAccountBusy = false;
      $("#save-qq-identity").disabled = false;
      $("#switch-qq-account").disabled = false;
      updateQqIdentityNote(status);
      toast(status?.napcat_online ? "下线请求已接受，正在退出 QQ" : "昔夕 QQ 已完全下线");
    }
    if (!settled) void monitorQqControl(action, generation);
  } catch (error) {
    toast(error.message, "error");
    setTimeout(loadStatus, 800);
  } finally {
    state.qqControlBusy = false;
    button?.removeAttribute("aria-busy");
    if (state.status) {
      updateQqControl(state.status.qq);
      renderQqSettings(state.status.qq);
      renderCompactStatus(state.status);
    }
    iconRefresh();
  }
}

async function toggleQq() {
  const button = $("#toggle-qq");
  const action = button?.dataset.action || (state.status?.qq.enabled ? "offline" : "online");
  await controlQqAction(action);
}

async function loginQqWithQr() {
  if (state.qqControlBusy || state.qqAccountBusy) return;
  const target = $("#bot-qq-id").value.trim();
  const configured = String(state.status?.qq.configured_user_id || "");
  if (target && configured && target !== configured) {
    await updateQqIdentity(true);
    return;
  }
  await controlQqAction("online");
  openQqQrDialog();
}

function focusQqIdentitySetup() {
  const identity = qqIdentityPayload();
  const target = !/^[1-9]\d{4,11}$/.test(identity.bot_qq_id) ? $("#bot-qq-id") : $("#owner-qq-id");
  $(".qq-identity-group")?.scrollIntoView({ behavior: "smooth", block: "center" });
  setTimeout(() => target?.focus(), 260);
}

async function runQqSetupGuide() {
  const guide = $("#qq-install-guide");
  const stage = guide?.dataset.stage || "checking";
  if (stage === "install") {
    await installNapcatFromQqSettings();
    return;
  }
  if (stage === "identity") {
    if (!qqIdentityReady()) {
      focusQqIdentitySetup();
      toast("请先填写昔夕登录 QQ 和主人 QQ");
      return;
    }
    const saved = await updateQqIdentity(false);
    if (!saved) return;
    await loginQqWithQr();
    return;
  }
  if (stage === "waiting") {
    openQqQrDialog();
    return;
  }
  if (stage === "connect") {
    await controlQqAction("online");
    return;
  }
  if (stage === "login" || stage === "error") {
    if (!qqIdentityReady()) {
      focusQqIdentitySetup();
      toast("请先填写昔夕登录 QQ 和主人 QQ");
      return;
    }
    await loginQqWithQr();
  }
}

function closeQqQrDialog() {
  if (state.qqQrTimer) clearInterval(state.qqQrTimer);
  state.qqQrTimer = null;
  if (state.qqQrObjectUrl) URL.revokeObjectURL(state.qqQrObjectUrl);
  state.qqQrObjectUrl = "";
  const dialog = $("#qq-qr-dialog");
  if (dialog?.open) dialog.close();
}

async function refreshQqQrImage() {
  const dialog = $("#qq-qr-dialog");
  if (!dialog?.open || state.qqQrRefreshing) return;
  state.qqQrRefreshing = true;
  const image = $("#qq-qr-image");
  const placeholder = $("#qq-qr-placeholder");
  const status = $("#qq-qr-status");
  try {
    const latest = await api("/api/status", { timeoutMs: 5000 });
    renderStatus(latest);
    const qq = latest.qq || {};
    if (qq.online) {
      image.hidden = true;
      placeholder.hidden = false;
      status.textContent = "QQ 已登录，昔夕已经上线";
      setTimeout(closeQqQrDialog, 500);
      return;
    }
    if (qq.qq_login_online || qq.napcat_online || qq.napcat_service_online) {
      image.hidden = true;
      placeholder.hidden = false;
      status.textContent = qq.onebot_online
        ? "扫码成功，正在连接消息通道"
        : "扫码成功，正在启动 OneBot 服务";
      return;
    }
    if (qq.account_state === "error") {
      image.hidden = true;
      placeholder.hidden = false;
      status.textContent = qq.account_error || "QQ 登录启动失败";
      return;
    }
    const response = await fetch(`/api/qq/qrcode?t=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error("二维码尚未生成");
    const blob = await response.blob();
    if (state.qqQrObjectUrl) URL.revokeObjectURL(state.qqQrObjectUrl);
    state.qqQrObjectUrl = URL.createObjectURL(blob);
    image.src = state.qqQrObjectUrl;
    image.hidden = false;
    placeholder.hidden = true;
    status.textContent = "二维码已生成，请使用手机 QQ 扫码";
  } catch (error) {
    image.hidden = true;
    placeholder.hidden = false;
    const latestQq = state.status?.qq || {};
    if (latestQq.account_state === "error") {
      status.textContent = latestQq.account_error || "QQ 登录启动失败";
    } else if (state.qqQrStartedAt && Date.now() - state.qqQrStartedAt > 45000) {
      status.textContent = "二维码生成超时，请点击刷新二维码重新启动登录";
    } else {
      status.textContent = error?.message && error.message !== "二维码尚未生成"
        ? error.message
        : "正在启动 NapCat 并生成二维码";
    }
  } finally {
    state.qqQrRefreshing = false;
  }
}

function openQqQrDialog() {
  const dialog = $("#qq-qr-dialog");
  if (!dialog) return;
  if (!dialog.open) dialog.showModal();
  state.qqQrStartedAt = Date.now();
  void refreshQqQrImage();
  if (state.qqQrTimer) clearInterval(state.qqQrTimer);
  state.qqQrTimer = setInterval(refreshQqQrImage, 1000);
  iconRefresh();
}

async function restartQqQrLogin() {
  if (state.qqQrRefreshing) return;
  const button = $("#qq-qr-refresh");
  button.disabled = true;
  state.qqQrStartedAt = Date.now();
  try {
    const result = await api("/api/qq/qrcode/refresh", {
      method: "POST",
      body: JSON.stringify({}),
      timeoutMs: 20000,
    });
    if (result?.qq) renderStatus({ ...state.status, qq: result.qq });
    await refreshQqQrImage();
  } catch (error) {
    $("#qq-qr-status").textContent = `刷新失败：${error.message}`;
  } finally {
    button.disabled = false;
    iconRefresh();
  }
}

async function waitForQqFullyOffline() {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const status = await api("/api/status", { timeoutMs: 5000 });
    renderStatus(status);
    const qq = status.qq || {};
    if (!qq.enabled && !qq.napcat_online && !qq.qq_process_online && !qq.process_online) return qq;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error("QQ 进程没有在预期时间内退出，请稍后重试");
}

async function restartQqChannel() {
  if (state.qqControlBusy || state.qqAccountBusy) return;
  const button = $("#qq-restart-channel");
  state.qqControlBusy = true;
  button.setAttribute("aria-busy", "true");
  renderQqSettings(state.status?.qq || {});
  iconRefresh();
  try {
    const stopped = await api("/api/qq/control", {
      method: "POST",
      body: JSON.stringify({ action: "offline" }),
      timeoutMs: 25000,
    });
    if (stopped?.qq) renderStatus({ ...state.status, qq: stopped.qq });
    await waitForQqFullyOffline();
    const started = await api("/api/qq/control", {
      method: "POST",
      body: JSON.stringify({ action: "online" }),
      timeoutMs: 20000,
    });
    if (started?.qq) renderStatus({ ...state.status, qq: started.qq });
    const generation = ++state.qqAccountMonitorGeneration;
    toast(started?.qq?.online ? "NapCat 已重启，QQ 通道已连接" : "NapCat 已重启，正在等待 QQ 登录");
    monitorQqControl("online", generation);
  } catch (error) {
    toast(`重启失败：${error.message}`, "error");
    setTimeout(loadStatus, 800);
  } finally {
    state.qqControlBusy = false;
    button.removeAttribute("aria-busy");
    if (state.status) renderQqSettings(state.status.qq);
    iconRefresh();
  }
}

async function installNapcatFromQqSettings() {
  if (state.status?.qq?.napcat_installed) {
    toast("NapCat 已经安装好了");
    return;
  }
  await installEnvironmentDependencies(["qq_channel"]);
  await loadStatus();
}

function openNapcatInstallGuide() {
  setView("tuning");
  showTuningPanel("environment");
  setTimeout(() => {
    $(`[data-environment-feature="qq_channel"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, 40);
}

async function toggleVoice(button) {
  if (state.voiceControlBusy) return;
  const action = button.dataset.action;
  if (action === "online" && state.status?.voice?.release_ready === false) {
    setInspector(false);
    setView("tuning");
    showTuningPanel("environment");
    setTimeout(() => {
      $(`[data-environment-feature="local_voice"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    }, 40);
    toast("请先安装或修复昔夕本地语音系统", "error");
    return;
  }
  state.voiceControlBusy = true;
  button.disabled = true;
  try {
    await api("/api/voice/control", {
      method: "POST",
      body: JSON.stringify({ action }),
    });
    await loadStatus();
    toast(action === "online" ? "语音合成已开启" : "语音合成已关闭");
  } catch (error) {
    toast(error.message, "error");
    await loadStatus();
  } finally {
    state.voiceControlBusy = false;
    if (state.status) renderStatus(state.status);
  }
}

function showTuningPanel(name) {
  if (!$("#tuning-" + name)) return;
  state.currentTuning = name;
  $$(".tuning-tab").forEach((item) => item.classList.toggle("active", item.dataset.tuning === name));
  $$(".tuning-panel").forEach((panel) => panel.classList.toggle("active", panel.id === `tuning-${name}`));
  const content = $(".settings-content");
  if (content) content.scrollTop = 0;
  renderTuningContext();
  if (name === "data") loadBackups();
  if (name === "game") loadGamePreferences();
  if (name === "model") loadModelWorkspace();
  if (name === "environment") loadEnvironment();
  if (name === "advanced") loadAdvancedSettings();
}

function searchSettings(query) {
  const normalized = query.trim().toLowerCase();
  $$(".settings-group").forEach((group) => group.classList.remove("search-match"));
  $$(".setting-row, .setting-action").forEach((row) => row.classList.remove("search-match"));
  const tabs = $$(".tuning-tab");
  const panels = $$(".tuning-panel");
  const empty = $("#settings-search-empty");
  if (!normalized) {
    tabs.forEach((tab) => { tab.hidden = false; tab.removeAttribute("aria-hidden"); });
    if (empty) empty.hidden = true;
    return;
  }

  const matches = panels.filter((panel) => panel.textContent.toLowerCase().includes(normalized));
  tabs.forEach((tab) => {
    const panel = $("#tuning-" + tab.dataset.tuning);
    const visible = matches.includes(panel);
    tab.hidden = !visible;
    tab.setAttribute("aria-hidden", String(!visible));
  });
  if (empty) empty.hidden = matches.length > 0;
  if (!matches.length) return;

  const panel = matches.find((candidate) => candidate.id === `tuning-${state.currentTuning}`) || matches[0];
  showTuningPanel(panel.id.replace("tuning-", ""));
  const row = $$(".setting-row, .setting-action", panel)
    .find((candidate) => candidate.textContent.toLowerCase().includes(normalized));
  const group = $$(".settings-group", panel)
    .find((candidate) => candidate.textContent.toLowerCase().includes(normalized));
  (row || group)?.classList.add("search-match");
  if (row) setTimeout(() => row.scrollIntoView({ behavior: "smooth", block: "center" }), 20);
}

function openWeatherCityDialog() {
  const dialog = $("#weather-city-dialog");
  const input = $("#weather-city-input");
  input.value = state.status?.weather.location || state.bootstrap?.settings?.weather_location || "";
  dialog.showModal();
  iconRefresh();
  setTimeout(() => { input.focus(); input.select(); }, 0);
}

async function saveWeatherCity(event) {
  event.preventDefault();
  const dialog = $("#weather-city-dialog");
  const input = $("#weather-city-input");
  const saveButton = $("#weather-city-save");
  const city = input.value.trim();
  if (!city) {
    toast("请输入城市名称", "error");
    input.focus();
    return;
  }
  saveButton.disabled = true;
  try {
    const applied = await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ weather_location: city, weather_enabled: true }),
    });
    if (state.bootstrap?.settings) Object.assign(state.bootstrap.settings, applied);
    fillSettings(state.bootstrap?.settings || applied);
    await loadStatus();
    dialog.close();
    toast(`天气城市已更换为${city}`);
  } catch (error) {
    toast(error.message, "error");
  } finally {
    saveButton.disabled = false;
  }
}

async function handleServiceControl(button) {
  if (button.dataset.control === "qq") {
    await toggleQq();
    return;
  }
  if (button.dataset.action === "change-city") {
    openWeatherCityDialog();
    return;
  }
  if (button.dataset.control === "voice" && ["online", "offline"].includes(button.dataset.action)) {
    await toggleVoice(button);
    return;
  }
  if (button.dataset.control === "model" && ["online", "offline"].includes(button.dataset.action)) {
    if (state.serviceControlBusy) return;
    const action = button.dataset.action;
    state.serviceControlBusy = "brain_enabled";
    button.disabled = true;
    try {
      await api("/api/model/control", { method: "POST", body: JSON.stringify({ action }) });
      await loadStatus();
      toast(action === "online" ? "语言模型已开启" : "语言模型已关闭");
    } catch (error) {
      toast(error.message, "error");
      await loadStatus();
    } finally {
      state.serviceControlBusy = "";
      if (state.status) renderStatus(state.status);
    }
    return;
  }
  if (button.dataset.panel) {
    setView("tuning");
    showTuningPanel(button.dataset.panel);
    const capability = button.dataset.modelCapability;
    if (capability) {
      setTimeout(() => focusModelCapability(capability), 40);
      return;
    }
    const focusSetting = button.dataset.focusSetting;
    if (focusSetting) setTimeout(() => $(`[data-setting="${focusSetting}"]`)?.focus(), 0);
    return;
  }

  const setting = button.dataset.setting;
  if (!setting || state.serviceControlBusy) return;
  const enabled = button.dataset.enabled === "true";
  state.serviceControlBusy = setting;
  button.disabled = true;
  try {
    const applied = await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({
        [setting]: !enabled,
        ...(setting === "weather_alert_enabled" && !enabled ? { weather_enabled: true } : {}),
      }),
    });
    if (state.bootstrap?.settings) Object.assign(state.bootstrap.settings, applied);
    await loadStatus();
    const labels = {
      vision_enabled: "图片理解",
      learning_enabled: "持续学习",
      weather_alert_enabled: "天气提醒",
    };
    toast(`${labels[setting]}已${enabled ? "关闭" : "开启"}`);
  } catch (error) {
    toast(error.message, "error");
  } finally {
    state.serviceControlBusy = "";
    if (state.status) renderStatus(state.status);
  }
}

function addMessage(role, text, options = {}) {
  $("#empty-chat")?.remove();
  const message = document.createElement("div");
  message.className = `message ${role}${options.pending ? " pending" : ""}`;
  message.dataset.role = role;
  message.dataset.messageId = String(options.id || `local-${Date.now()}-${Math.random().toString(16).slice(2)}`);
  message.dataset.text = text || "";
  if (options.pending) message.setAttribute("aria-label", `${characterName()}正在思考`);
  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.setAttribute("aria-hidden", "true");
  if (role === "user") {
    setUserAvatarContent(avatar, state.appearance?.user_avatar || "");
  } else {
    const portrait = document.createElement("img");
    portrait.dataset.xixiAvatar = "true";
    portrait.src = xixiAvatarSource();
    portrait.alt = "";
    avatar.append(portrait);
  }
  const body = document.createElement("div");
  body.className = "message-body";
  const meta = document.createElement("div");
  meta.className = "message-meta";
  const author = document.createElement("span");
  author.textContent = role === "user" ? "你" : characterName();
  meta.append(author);
  if (options.pending) {
    const thinking = document.createElement("span");
    thinking.className = "message-thinking";
    thinking.textContent = "正在思考";
    meta.append(thinking);
  }
  if (options.createdAt) {
    const time = document.createElement("time");
    time.dateTime = options.createdAt;
    time.textContent = formatDate(options.createdAt);
    meta.append(time);
  }
  body.append(meta);
  if (options.images?.length) {
    const images = document.createElement("div");
    images.className = "message-images";
    options.images.forEach((source) => {
      const image = document.createElement("img"); image.src = source; image.alt = "聊天图片"; images.append(image);
    });
    body.append(images);
  }
  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  if (options.pending) bubble.innerHTML = '<span class="typing-dots"><i></i><i></i><i></i></span>';
  else {
    if (options.quote) {
      const quote = document.createElement("div");
      quote.className = "message-quote";
      quote.textContent = options.quote;
      bubble.append(quote);
    }
    const content = document.createElement("span");
    content.className = "message-text";
    appendHighlightedText(content, text, options.highlight || "");
    bubble.append(content);
  }
  body.append(bubble);
  if (!options.pending) {
    const footer = document.createElement("div");
    footer.className = "message-footer";
    if (role === "assistant") {
      const voiceTools = document.createElement("div");
      voiceTools.className = "message-voice-tools";
      const speak = document.createElement("button");
      speak.type = "button";
      speak.className = "message-voice-play";
      speak.dataset.messageAction = "speak";
      speak.title = "朗读这条回复";
      speak.setAttribute("aria-label", "朗读这条回复");
      speak.setAttribute("aria-pressed", "false");
      speak.innerHTML = '<i data-lucide="volume-2"></i>';
      const languages = document.createElement("div");
      languages.className = "voice-language-control message-voice-language";
      languages.setAttribute("role", "radiogroup");
      languages.setAttribute("aria-label", "这条回复的朗读语言");
      [
        ["zh", "中", "使用中文朗读"],
        ["ja", "日", "使用日语朗读"],
        ["en", "EN", "使用英语朗读"],
      ].forEach(([language, label, title]) => {
        const languageButton = document.createElement("button");
        languageButton.type = "button";
        languageButton.dataset.messageAction = "voice-language";
        languageButton.dataset.voiceLanguage = language;
        languageButton.setAttribute("role", "radio");
        languageButton.title = title;
        languageButton.setAttribute("aria-label", title);
        languageButton.textContent = label;
        languages.append(languageButton);
      });
      voiceTools.append(speak, languages);
      footer.append(voiceTools);
    }
    const actions = document.createElement("div");
    actions.className = "message-actions";
    const copy = document.createElement("button");
    copy.type = "button"; copy.dataset.messageAction = "copy"; copy.title = "复制消息"; copy.setAttribute("aria-label", "复制消息"); copy.innerHTML = '<i data-lucide="copy"></i>';
    const reply = document.createElement("button");
    reply.type = "button"; reply.dataset.messageAction = "reply"; reply.title = "引用回复"; reply.setAttribute("aria-label", "引用回复"); reply.innerHTML = '<i data-lucide="corner-up-left"></i>';
    actions.append(copy, reply);
    footer.append(actions);
    body.append(footer);
  }
  if (role === "user") message.append(body, avatar);
  else message.append(avatar, body);
  $("#message-stream").append(message);
  $("#message-stream").scrollTop = $("#message-stream").scrollHeight;
  syncVoiceLanguageControl();
  iconRefresh();
  return message;
}

function setUserAvatarContent(host, source) {
  if (!host) return;
  host.replaceChildren();
  if (normalizeAppearanceImage(source)) {
    const image = document.createElement("img");
    image.src = source;
    image.alt = "";
    host.append(image);
  } else {
    host.innerHTML = '<i data-lucide="user-round"></i>';
  }
}

function appendHighlightedText(host, text, query) {
  const source = String(text || "");
  const needle = String(query || "").trim();
  if (!needle) {
    host.textContent = source;
    return;
  }
  const foldedSource = source.toLocaleLowerCase();
  const foldedNeedle = needle.toLocaleLowerCase();
  let cursor = 0;
  while (cursor < source.length) {
    const index = foldedSource.indexOf(foldedNeedle, cursor);
    if (index < 0) {
      host.append(document.createTextNode(source.slice(cursor)));
      break;
    }
    if (index > cursor) host.append(document.createTextNode(source.slice(cursor, index)));
    const mark = document.createElement("mark");
    mark.textContent = source.slice(index, index + needle.length);
    host.append(mark);
    cursor = index + needle.length;
  }
}

function scrollChatToLatest() {
  const stream = $("#message-stream");
  if (!stream || state.currentView !== "chat") return;
  const apply = () => { stream.scrollTop = stream.scrollHeight; };
  requestAnimationFrame(() => {
    apply();
    requestAnimationFrame(apply);
  });
}

function renderEmptyChatState() {
  const stream = $("#message-stream");
  if (!stream) return;
  stream.replaceChildren();
  const empty = document.createElement("div");
  empty.className = "empty-chat";
  empty.id = "empty-chat";
  empty.innerHTML = `<div class="empty-avatar"><img data-xixi-avatar src="${xixiAvatarSource()}" alt="${characterName()}"><span></span></div>`;
  const title = document.createElement("strong");
  title.textContent = `${characterName()}在这里`;
  const detail = document.createElement("span");
  detail.textContent = "开始一段新的对话吧";
  empty.append(title, detail);
  stream.append(empty);
}

async function clearChatHistory() {
  if (state.sending) {
    toast("请等当前回复结束后再清理聊天记录", "error");
    return;
  }
  const confirmed = await confirmAction({
    kicker: "整理当前对话",
    title: "清除聊天记录？",
    message: "当前聊天页面会回到空白状态，可见的历史对话将从这里清除。",
    detail: "重要记忆、关系状态、成长记录和人格资料都会保留。",
    note: "这不会改变昔夕对你的长期记忆。",
    confirmLabel: "清除记录",
    icon: "brush",
    actionIcon: "brush",
  });
  if (!confirmed) return;

  const button = $("#clear-chat-history");
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.innerHTML = '<i data-lucide="loader-circle"></i>';
  iconRefresh();
  try {
    stopMessageVoicePlayback({ abortRequest: true });
    state.messageVoiceCache.clear();
    clearReply();
    await api("/api/chat/history", { method: "DELETE", timeoutMs: 15_000 });
    state.chatHistoryRequestId += 1;
    state.chatHistory = [];
    state.currentChatQuery = "";
    renderEmptyChatState();
    if (state.bootstrap?.home) state.bootstrap.home.recent_conversation = null;
    setOperation(state.status?.model?.online ? "idle" : "offline", "", "聊天记录已清除");
    await loadChatContextMemories();
    toast("聊天记录已清除，昔夕的重要记忆仍然保留");
  } catch (error) {
    toast(`聊天记录清理失败：${error.message}`, "error");
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
    button.innerHTML = '<i data-lucide="brush"></i>';
    iconRefresh();
  }
}

function clearReply() {
  state.replyTo = null;
  $("#reply-preview").hidden = true;
  $("#reply-preview-text").textContent = "";
  $("#inspector-reply-title").textContent = "没有引用消息";
  $("#inspector-reply-copy").textContent = "这次回复会直接接着当前对话";
  $("#inspector-clear-reply").hidden = true;
}

function beginReply(message) {
  const text = message?.dataset.text?.trim();
  if (!text) return;
  state.replyTo = { role: message.dataset.role, text };
  $("#reply-preview-text").textContent = text.slice(0, 120);
  $("#reply-preview").hidden = false;
  $("#inspector-reply-title").textContent = message.dataset.role === "assistant" ? `引用${characterName()}的消息` : "引用你的消息";
  $("#inspector-reply-copy").textContent = text.slice(0, 140);
  $("#inspector-clear-reply").hidden = false;
  $("#chat-input").focus();
}

function resetMessageVoiceButton(button) {
  if (!button) return;
  button.disabled = false;
  button.classList.remove("loading", "playing");
  button.setAttribute("aria-busy", "false");
  button.setAttribute("aria-pressed", "false");
  button.title = "朗读这条回复";
  button.setAttribute("aria-label", "朗读这条回复");
  button.innerHTML = '<i data-lucide="volume-2"></i>';
}

function stopMessageVoicePlayback({ abortRequest = false } = {}) {
  if (abortRequest && state.messageVoiceRequestController) {
    state.messageVoiceRequestController.abort();
  }
  state.messageVoiceRequestController = null;
  if (state.messageVoiceAudio) {
    state.messageVoiceAudio.pause();
    state.messageVoiceAudio.currentTime = 0;
  }
  resetMessageVoiceButton(state.messageVoiceButton);
  state.messageVoiceAudio = null;
  state.messageVoiceButton = null;
  if (!state.voiceCallActive && state.presence === "speaking") {
    setOperation("idle", "", "消息朗读结束");
  }
  iconRefresh();
}

async function playMessageVoice(message, button) {
  const text = String(message?.dataset.text || "").trim();
  if (!text || message?.dataset.role !== "assistant") return;
  if (state.status?.voice?.enabled === false) {
    toast("语音系统已关闭，请先在运行状态中开启语音", "error");
    return;
  }

  if (state.messageVoiceButton === button && state.messageVoiceAudio && !state.messageVoiceAudio.paused) {
    state.messageVoiceAudio.currentTime = 0;
    await state.messageVoiceAudio.play();
    return;
  }

  stopMessageVoicePlayback({ abortRequest: true });
  const language = $('[data-setting="voice_language"]')?.value || "zh";
  const cacheKey = `${message.dataset.messageId}:${language}`;
  let source = state.messageVoiceCache.get(cacheKey) || "";

  if (!source) {
    const controller = new AbortController();
    state.messageVoiceRequestController = controller;
    state.messageVoiceButton = button;
    button.disabled = true;
    button.classList.add("loading");
    button.setAttribute("aria-busy", "true");
    button.title = "正在生成语音";
    button.setAttribute("aria-label", "正在生成语音");
    button.innerHTML = '<i data-lucide="loader-circle"></i>';
    iconRefresh();
    setOperation("thinking", "正在生成声音", "正在朗读这条回复");
    try {
      const rendered = await api("/api/voice/render", {
        method: "POST",
        signal: controller.signal,
        body: JSON.stringify({ text, language, quality: "complete" }),
        timeoutMs: 180_000,
      });
      if (state.messageVoiceRequestController !== controller) return;
      source = String(rendered.audio_url || "").trim();
      if (!source) throw new Error("语音文件没有生成成功");
      state.messageVoiceCache.set(cacheKey, source);
    } catch (error) {
      if (error.name !== "AbortError") toast(`这条回复暂时无法朗读：${error.message}`, "error");
      if (state.messageVoiceRequestController === controller) stopMessageVoicePlayback();
      return;
    } finally {
      if (state.messageVoiceRequestController === controller) {
        state.messageVoiceRequestController = null;
        button.disabled = false;
        button.classList.remove("loading");
        button.setAttribute("aria-busy", "false");
      }
    }
  }

  const audio = new Audio(source);
  state.messageVoiceAudio = audio;
  state.messageVoiceButton = button;
  audio.volume = 1;
  button.classList.add("playing");
  button.setAttribute("aria-pressed", "true");
  button.title = "重新播放这条回复";
  button.setAttribute("aria-label", "重新播放这条回复");
  button.innerHTML = '<i data-lucide="volume-2"></i>';
  iconRefresh();
  setOperation("speaking", `${characterName()}正在说话`, "正在朗读这条回复");
  const finish = () => {
    if (state.messageVoiceAudio !== audio) return;
    stopMessageVoicePlayback();
  };
  audio.addEventListener("ended", finish, { once: true });
  audio.addEventListener("error", () => {
    finish();
    toast("语音播放失败，请再点一次", "error");
  }, { once: true });
  try {
    await audio.play();
  } catch (error) {
    finish();
    toast(`语音播放失败：${error.message}`, "error");
  }
}

async function handleMessageAction(event) {
  const button = event.target.closest("[data-message-action]");
  if (!button) return;
  const message = button.closest(".message");
  if (!message) return;
  if (button.dataset.messageAction === "voice-language") {
    await setVoiceLanguage(button.dataset.voiceLanguage);
  } else if (button.dataset.messageAction === "speak") {
    await playMessageVoice(message, button);
  } else if (button.dataset.messageAction === "copy") {
    try { await navigator.clipboard.writeText(message.dataset.text || ""); toast("消息已复制"); }
    catch { toast("无法访问剪贴板", "error"); }
  } else if (button.dataset.messageAction === "reply") {
    beginReply(message);
  }
}

function setOperation(presence, title = "", detail = "") {
  state.presence = presence;
  const labels = { idle: "空闲中", listening: "正在听", thinking: "正在思考", speaking: "正在说话", offline: "暂时离线" };
  const label = labels[presence] || labels.idle;
  document.body.dataset.presence = presence;
  $("#home-presence").dataset.presence = presence;
  $("#home-presence-label").textContent = label;
  $("#inspector-chat-presence").textContent = label;
  $("#home-presence-detail").textContent = assistantText(detail || (presence === "idle" ? "可以随时找她说话" : title));
  $("#inspector-chat-operation").textContent = assistantText(detail || title || "对话已同步");
  const online = presence !== "offline";
  $("#home-presence-dot").classList.toggle("online", online);
}

async function loadChatHistory() {
  if (state.sending) return;
  stopMessageVoicePlayback({ abortRequest: true });
  const requestId = ++state.chatHistoryRequestId;
  state.currentChatQuery = "";
  try {
    const result = await api("/api/chat/history?limit=160");
    if (requestId !== state.chatHistoryRequestId) return;
    state.chatHistory = result.items || [];
    const stream = $("#message-stream");
    stream.replaceChildren();
    state.chatHistory.forEach((item) => addMessage(item.role, item.content, {
      id: item.id,
      createdAt: item.created_at,
    }));
    if (!state.chatHistory.length) {
      renderEmptyChatState();
    }
    setOperation(state.status?.model?.online ? "idle" : "offline", "", "历史消息已同步");
    scrollChatToLatest();
    if (state.currentView === "chat") loadChatContextMemories();
  } catch (error) {
    if (requestId !== state.chatHistoryRequestId) return;
    setOperation("offline", "历史读取失败", error.message);
    toast(error.message, "error");
  }
}

async function fileToDataUrl(file) {
  return await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function renderImageStrip() {
  const strip = $("#image-strip");
  strip.hidden = state.images.length === 0;
  strip.replaceChildren(...state.images.map((source, index) => {
    const preview = document.createElement("div"); preview.className = "image-preview";
    const image = document.createElement("img"); image.src = source; image.alt = `图片 ${index + 1}`;
    const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "×"; remove.title = "移除图片";
    remove.addEventListener("click", () => { state.images.splice(index, 1); renderImageStrip(); });
    preview.append(image, remove); return preview;
  }));
}

async function sendMessage(options = {}) {
  if (state.sending) return;
  const input = $("#chat-input");
  const text = String(options.text ?? input.value).trim();
  if (!text && !state.images.length) return;
  const images = [...state.images];
  const replyTo = state.replyTo;
  const displayText = text || "[图片]";
  if (options.displayUser !== false) addMessage("user", displayText, { images, quote: replyTo?.text });
  state.lastUserMessage = text;
  input.value = ""; state.images = []; renderImageStrip();
  clearReply();
  const pending = addMessage("assistant", "", { pending: true });
  state.sending = true;
  state.abortController = new AbortController();
  $("#send-message").hidden = true;
  $("#stop-message").hidden = false;
    setOperation("thinking", images.length ? "正在看图并思考" : `${characterName()}正在思考`, replyTo ? "正在结合你引用的内容" : "正在整理上下文");
  try {
    let requestPlan = { vision: images.length > 0, web_search: false, voice: false };
    try {
      requestPlan = await api("/api/chat/plan", {
        method: "POST",
        signal: state.abortController.signal,
        body: JSON.stringify({ text, images, voice: false }),
      });
    } catch (error) {
      if (error.name === "AbortError") throw error;
    }
    if (requestPlan.vision && requestPlan.web_search) setOperation("thinking", "正在看图并联网查找", "读取图片和相关资料");
    else if (requestPlan.vision) setOperation("thinking", "正在理解图片", "结合图片内容组织回答");
    else if (requestPlan.web_search) setOperation("thinking", "正在联网查找", "核对最新资料并形成自己的回答");
    const result = await api("/api/chat", {
      method: "POST",
      signal: state.abortController.signal,
      body: JSON.stringify({ text, images, quote: replyTo, voice: false }),
    });
    pending.remove();
    addMessage("assistant", result.reply);
    setOperation("idle", "", "刚刚回复了你");
  } catch (error) {
    pending.remove();
    if (error.name === "AbortError") {
      addMessage("assistant", "已停止等待这次回复。服务器可能仍在完成这次思考，但结果不会再显示在这里。");
      setOperation("idle", "", "已停止等待");
    } else {
      addMessage("assistant", `这次没接上：${error.message}`);
      setOperation("offline", "回复失败", error.message);
    }
  } finally {
    state.abortController = null;
    state.sending = false;
    $("#send-message").hidden = false;
    $("#stop-message").hidden = true;
    input.focus();
  }
}

function stopWaiting() {
  if (!state.abortController) return;
  state.abortController.abort();
}

const commands = [
  { id: "chat", label: "打开对话", hint: "和昔夕聊天", icon: "message-square-text", run: () => setView("chat") },
  { id: "voice-call", label: "语音通话", hint: "直接和昔夕说话", icon: "phone", run: () => { setView("chat"); startVoiceCall(); } },
  { id: "memory", label: "搜索记忆", hint: "浏览长期记忆与知识", icon: "brain", run: () => { setView("memory"); $("#memory-query").focus(); } },
  { id: "growth", label: "查看成长", hint: "兴趣与主观想法", icon: "sprout", run: () => setView("growth") },
  { id: "game", label: "打开游戏陪伴", hint: "让昔夕看你玩游戏并陪你聊天", icon: "gamepad-2", run: () => setView("game") },
  { id: "system", label: "检查系统状态", hint: "服务、诊断与运行日志", icon: "activity", run: () => { setView("system"); showSystemTab("overview"); } },
  { id: "settings", label: "打开设置", hint: "外观、模型、声音和 QQ", icon: "settings-2", run: () => setView("tuning") },
  { id: "refresh", label: "刷新当前页面", hint: "重新读取实时数据", icon: "refresh-cw", run: refreshCurrentView },
  { id: "notifications", label: "查看通知", hint: "异常、天气与重要活动", icon: "bell", run: () => setNotificationPanel(true) },
];

function renderCommands(query = "") {
  const normalized = query.trim().toLowerCase();
  const filtered = commands.filter((command) => `${command.label} ${command.hint}`.toLowerCase().includes(normalized));
  $("#command-list").replaceChildren(...filtered.map((command, index) => {
    const button = document.createElement("button");
    button.type = "button"; button.className = `command-item${index === 0 ? " selected" : ""}`; button.dataset.commandId = command.id;
    button.innerHTML = `<i data-lucide="${command.icon}"></i><span><strong>${command.label}</strong><small>${command.hint}</small></span><i data-lucide="corner-down-left"></i>`;
    return button;
  }));
  iconRefresh();
}

function openCommandPalette() {
  renderCommands();
  $("#command-input").value = "";
  $("#command-dialog").showModal();
  setTimeout(() => $("#command-input").focus(), 0);
}

function runCommand(commandId) {
  const command = commands.find((item) => item.id === commandId);
  if (!command) return;
  $("#command-dialog").close();
  command.run();
}

function moveCommandSelection(direction) {
  const items = $$(".command-item", $("#command-list"));
  if (!items.length) return;
  const current = Math.max(0, items.findIndex((item) => item.classList.contains("selected")));
  const next = (current + direction + items.length) % items.length;
  items.forEach((item, index) => item.classList.toggle("selected", index === next));
  items[next].scrollIntoView({ block: "nearest" });
}

function readNotificationIds() {
  try { return new Set(JSON.parse(localStorage.getItem(notificationReadKey) || "[]")); }
  catch { return new Set(); }
}

function renderNotifications() {
  const read = readNotificationIds();
  const unread = state.notifications.filter((item) => !read.has(item.id));
  $("#notification-badge").hidden = unread.length === 0;
  $("#notification-badge").textContent = unread.length > 99 ? "99+" : String(unread.length);
  $("#notification-summary").textContent = unread.length ? `${unread.length} 条未读` : "没有未读通知";
  const host = $("#notification-list");
  if (!state.notifications.length) {
    host.innerHTML = '<div class="notification-empty"><i data-lucide="bell-ring"></i><strong>现在没有需要留意的事</strong><span>服务状态和重要活动会显示在这里</span></div>';
    iconRefresh();
    return;
  }
  host.replaceChildren(...state.notifications.map((item) => {
    const row = document.createElement("article");
    row.className = `notification-item ${item.kind || "info"}${read.has(item.id) ? " read" : ""}`;
    row.dataset.notificationId = item.id;
    const icon = item.kind === "error" ? "circle-alert" : item.kind === "warning" ? "triangle-alert" : "info";
    const iconHost = document.createElement("i"); iconHost.dataset.lucide = icon;
    const body = document.createElement("div");
    const title = document.createElement("strong"); title.textContent = item.title;
    const detail = document.createElement("p"); detail.textContent = item.detail || "";
    const time = document.createElement("time"); time.textContent = formatDate(item.created_at);
    body.append(title, detail, time); row.append(iconHost, body);
    return row;
  }));
  iconRefresh();
}

async function loadNotifications() {
  try {
    const result = await api("/api/notifications?limit=40");
    state.notifications = result.items || [];
    const activeIds = new Set(state.notifications.map((item) => item.id));
    const retainedReadIds = [...readNotificationIds()].filter((id) => activeIds.has(id));
    localStorage.setItem(notificationReadKey, JSON.stringify(retainedReadIds));
    renderNotifications();
  } catch (error) {
    console.warn("notifications unavailable", error);
  }
}

function setNotificationPanel(open) {
  $("#notification-panel").classList.toggle("open", open);
  $("#notification-panel").setAttribute("aria-hidden", String(!open));
  $("#open-notifications").setAttribute("aria-expanded", String(open));
  if (open) loadNotifications();
}

function markNotificationsRead() {
  localStorage.setItem(notificationReadKey, JSON.stringify(state.notifications.map((item) => item.id).slice(0, 200)));
  renderNotifications();
}

function updateVoiceInput(stateName, status) {
  const overlay = $("#voice-input-overlay");
  const control = $("#voice-record-control");
  if (!overlay || !control) return;
  overlay.dataset.state = stateName;
  $("#voice-input-status").textContent = status;
  const recording = stateName === "recording";
  control.setAttribute("aria-pressed", String(recording));
  control.setAttribute("aria-label", recording ? "结束录音" : "开始录音");
  control.disabled = stateName === "requesting" || stateName === "recognizing";
}

function voiceRecognitionContext() {
  return state.chatHistory
    .slice(-6)
    .map((item) => String(item.content || "").replace(/\s+/g, " ").slice(0, 120))
    .filter(Boolean)
    .join("；")
    .slice(-600);
}

function createVoiceRecorder(stream) {
  const mimeType = getVoiceCallMimeType();
  const options = { audioBitsPerSecond: 128000 };
  if (mimeType) options.mimeType = mimeType;
  return new MediaRecorder(stream, options);
}

function showMicrophonePermissionDialog({ blocked = false } = {}) {
  if (pendingMicrophonePermission) return pendingMicrophonePermission.promise;
  const dialog = $("#microphone-permission-dialog");
  dialog.dataset.mode = blocked ? "blocked" : "request";
  $("#microphone-permission-kicker").textContent = blocked ? "需要重新授权" : "设备权限";
  $("#microphone-permission-title").textContent = blocked ? "麦克风目前无法使用" : "允许昔夕使用麦克风？";
  $("#microphone-permission-message").textContent = blocked
    ? "之前的拒绝已经被记录，重新授权后才能继续语音输入、通话和游戏陪伴。"
    : "麦克风只在你主动使用语音输入、语音通话或游戏陪伴时开启。";
  $("#microphone-permission-detail").textContent = blocked
    ? "若重新授权后仍不可用，请打开 Windows 麦克风设置，确认设备访问和桌面应用访问均已开启。"
    : "关闭通话或语音输入后，录音轨道会立即停止。";
  $("#microphone-permission-allow").innerHTML = `<i data-lucide="${blocked ? "shield-check" : "mic"}"></i><span>${blocked ? "重新授权" : "允许麦克风"}</span>`;
  const promise = new Promise((resolve) => {
    pendingMicrophonePermission = { resolve, promise: null };
  });
  pendingMicrophonePermission.promise = promise;
  dialog.showModal();
  iconRefresh();
  return promise;
}

async function settleMicrophonePermissionDialog(allowed) {
  const pending = pendingMicrophonePermission;
  if (!pending) return;
  const dialog = $("#microphone-permission-dialog");
  const buttons = $$("button", dialog);
  buttons.forEach((button) => { button.disabled = true; });
  try {
    await applyMicrophonePermission(Boolean(allowed));
    pendingMicrophonePermission = null;
    if (dialog.open) dialog.close();
    pending.resolve(Boolean(allowed));
  } catch (error) {
    toast(`麦克风权限修改失败：${error.message || error}`, "error");
  } finally {
    buttons.forEach((button) => { button.disabled = false; });
  }
}

async function ensureMicrophonePermission() {
  if (state.microphonePermission.enabled) return true;
  const allowed = await showMicrophonePermissionDialog({
    blocked: state.microphonePermission.browser === "denied",
  });
  if (!allowed) throw new Error("麦克风权限未开启，可在设置的基础与启动页面重新打开");
  return true;
}

async function acquireMicrophoneStream() {
  const preferred = {
    audio: {
      echoCancellation: { ideal: true },
      noiseSuppression: { ideal: true },
      autoGainControl: { ideal: true },
      channelCount: { ideal: 1 },
      sampleRate: { ideal: 48000 },
      sampleSize: { ideal: 16 },
    },
  };
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia(preferred);
  } catch (error) {
    if (["NotAllowedError", "SecurityError"].includes(String(error?.name || ""))) throw error;
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  }
  stream.getAudioTracks().forEach((track) => {
    try { track.contentHint = "speech"; } catch {}
  });
  return stream;
}

async function requestMicrophoneStream({ allowPermissionRetry = true } = {}) {
  await ensureMicrophonePermission();
  try {
    const stream = await acquireMicrophoneStream();
    state.microphonePermission.browser = "granted";
    state.microphonePermission.enabled = true;
    renderMicrophonePermission();
    return stream;
  } catch (error) {
    const permissionError = ["NotAllowedError", "SecurityError"].includes(String(error?.name || ""));
    if (!permissionError) throw error;
    await applyMicrophonePermission(false);
    state.microphonePermission.browser = "denied";
    renderMicrophonePermission();
    if (allowPermissionRetry) {
      const retry = await showMicrophonePermissionDialog({ blocked: true });
      if (retry) return requestMicrophoneStream({ allowPermissionRetry: false });
    }
    throw new Error("麦克风权限被系统或应用阻止，请重新授权后再试");
  }
}

async function verifyMicrophonePermission() {
  if (state.microphonePermission.busy) return;
  try {
    await applyMicrophonePermission(true);
    const stream = await requestMicrophoneStream({ allowPermissionRetry: false });
    stream.getTracks().forEach((track) => track.stop());
    state.microphonePermission.browser = "granted";
    state.microphonePermission.enabled = true;
    renderMicrophonePermission();
    toast("麦克风权限正常，可以使用语音输入和通话");
  } catch (error) {
    toast(error.message || "麦克风仍然不可用", "error");
    void showMicrophonePermissionDialog({ blocked: true });
  }
}

async function toggleMicrophonePermission(event) {
  const enabled = Boolean(event.currentTarget.checked);
  if (enabled) {
    await verifyMicrophonePermission();
    return;
  }
  await applyMicrophonePermission(false);
  if (state.voiceInputOpen) closeVoiceInput();
  if (state.voiceCallActive) endVoiceCall({ silent: true });
  toast("麦克风访问已关闭");
}

function openVoiceInput() {
  if (state.voiceInputOpen) return;
  state.voiceInputSession += 1;
  state.voiceInputOpen = true;
  state.voiceRecordingCancelled = false;
  state.voiceStopRequested = false;
  const overlay = $("#voice-input-overlay");
  overlay.hidden = false;
  document.body.classList.add("voice-input-open");
  updateVoiceInput("ready", "准备聆听");
  requestAnimationFrame(() => $("#voice-record-control").focus());
}

function closeVoiceInput() {
  if (!state.voiceInputOpen) return;
  state.voiceInputSession += 1;
  state.voiceInputOpen = false;
  state.voiceSpaceHeld = false;
  state.voiceStopRequested = true;
  state.voiceRecordingCancelled = true;
  if (state.recorder?.state === "recording") state.recorder.stop();
  else {
    state.recordingStream?.getTracks().forEach((track) => track.stop());
    state.recordingStream = null;
    state.voiceRecordingStarting = false;
  }
  $("#voice-input-overlay").hidden = true;
  document.body.classList.remove("voice-input-open");
  setOperation("idle", "", "语音输入已取消");
  $("#record-voice").focus();
}

async function startVoiceRecording() {
  if (!state.voiceInputOpen || state.voiceRecordingStarting || state.recorder?.state === "recording") return;
  const session = state.voiceInputSession;
  state.voiceRecordingStarting = true;
  state.voiceRecordingCancelled = false;
  state.voiceStopRequested = false;
  updateVoiceInput("requesting", "正在启用麦克风");
  try {
    const stream = await requestMicrophoneStream();
    if (!state.voiceInputOpen || session !== state.voiceInputSession) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    state.recordingStream = stream;
    state.chunks = [];
    const chunks = [];
    const recorder = createVoiceRecorder(state.recordingStream);
    state.recorder = recorder;
    recorder.addEventListener("dataavailable", (event) => { if (event.data.size) chunks.push(event.data); });
    recorder.addEventListener("stop", async () => {
      stream.getTracks().forEach((track) => track.stop());
      if (state.recordingStream === stream) state.recordingStream = null;
      if (state.recorder === recorder) state.recorder = null;
      const cancelled = state.voiceRecordingCancelled || session !== state.voiceInputSession || !state.voiceInputOpen;
      const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      if (cancelled) return;
      updateVoiceInput("recognizing", "正在识别你说的话");
      setOperation("thinking", "正在识别语音", "把录音转换成文字");
      try {
        const audio = await fileToDataUrl(blob);
        const result = await api("/api/transcribe", {
          method: "POST",
          body: JSON.stringify({ audio, language: "zh", context: voiceRecognitionContext() }),
        });
        if (!state.voiceInputOpen || session !== state.voiceInputSession) return;
        $("#chat-input").value = result.text;
        state.voiceInputOpen = false;
        $("#voice-input-overlay").hidden = true;
        document.body.classList.remove("voice-input-open");
        setOperation("idle", "", "语音已转成文字");
        $("#chat-input").focus();
      } catch (error) {
        if (!state.voiceInputOpen || session !== state.voiceInputSession) return;
        updateVoiceInput("error", "没有识别成功，点击麦克风重试");
        setOperation("offline", "语音识别失败", error.message);
        toast(error.message, "error");
      }
    });
    recorder.start();
    updateVoiceInput("recording", "正在听你说话");
    setOperation("listening", "正在听你说话", "松开空格或点击麦克风结束");
    if (state.voiceStopRequested) stopVoiceRecording();
  } catch (error) {
    updateVoiceInput("error", "麦克风不可用，点击重试");
    setOperation("idle", "", "麦克风未启用");
    toast(`无法使用麦克风：${error.message}`, "error");
  } finally {
    if (session === state.voiceInputSession) state.voiceRecordingStarting = false;
  }
}

function stopVoiceRecording() {
  state.voiceStopRequested = true;
  if (state.recorder?.state !== "recording") return;
  state.recorder.stop();
}

function toggleVoiceRecording() {
  if (state.recorder?.state === "recording") stopVoiceRecording();
  else startVoiceRecording();
}

function setVoiceCallPhase(phase, caption = "") {
  const labels = {
    connecting: "正在连接",
    calibrating: "正在准备麦克风",
    listening: "正在听你说话",
    recording: "正在听你说话",
    recognizing: "正在识别",
    thinking: `${characterName()}正在想`,
    speaking: `${characterName()}正在说话`,
    muted: "麦克风已关闭",
    error: "通话遇到问题",
  };
  const panel = $("#voice-call-panel");
  if (!panel) return;
  panel.dataset.phase = phase;
  $("#voice-call-status").textContent = labels[phase] || "通话中";
  $("#voice-call-caption").textContent = caption || labels[phase] || "通话中";
  const dockPhase = phase === "speaking" ? `${characterName()}正在说话` : phase === "thinking" || phase === "recognizing" ? "正在回应" : state.voiceCallMuted ? "麦克风已关闭" : "通话中";
  $("#voice-call-dock-status").dataset.phaseLabel = dockPhase;
  panel.style.setProperty("--call-level", phase === "speaking" ? "0.6" : "0");
  void syncNativeVoiceCallOverlay();
}

function voiceCallTranscriptEntries() {
  return [...document.querySelectorAll("#voice-call-dock-transcript .voice-call-dock-line")].map((line) => ({
    role: line.classList.contains("user") ? "user" : "assistant",
    text: String(line.querySelector("p")?.textContent || "").trim(),
  })).filter((item) => item.text).slice(-6);
}

const callOverlayThemeKeys = [
  "canvas",
  "surface",
  "surface-soft",
  "surface-strong",
  "ink",
  "ink-strong",
  "muted",
  "line",
  "line-soft",
  "accent",
  "accent-deep",
  "accent-soft",
  "blue",
  "danger",
];

function callOverlayThemeSnapshot() {
  const styles = getComputedStyle(document.documentElement);
  const theme = Object.fromEntries(callOverlayThemeKeys.map((key) => [
    key,
    styles.getPropertyValue(`--${key}`).trim(),
  ]).filter(([, value]) => value));
  theme.colorScheme = styles.colorScheme === "dark" ? "dark" : "light";
  return theme;
}

async function syncNativeVoiceCallOverlay() {
  state.voiceCallOverlaySyncQueued = true;
  if (state.voiceCallOverlaySyncRunning) return;
  state.voiceCallOverlaySyncRunning = true;
  try {
    while (state.voiceCallOverlaySyncQueued) {
      state.voiceCallOverlaySyncQueued = false;
      const desktopApi = window.pywebview?.api;
      const available = typeof desktopApi?.sync_call_overlay === "function";
      document.body.classList.toggle("native-call-overlay-enabled", available);
      if (!available) continue;
      const phaseLabel = $("#voice-call-dock-status")?.dataset.phaseLabel || "通话中";
      const duration = $("#voice-call-duration")?.textContent || "00:00";
      try {
        await desktopApi.sync_call_overlay({
          active: state.voiceCallActive,
          minimized: state.voiceCallMinimized,
          assistant_name: characterName(),
          status: phaseLabel,
          duration,
          entries: voiceCallTranscriptEntries(),
          theme: callOverlayThemeSnapshot(),
        });
      } catch (error) {
        console.debug("native call overlay sync was not available", error);
      }
    }
  } finally {
    state.voiceCallOverlaySyncRunning = false;
    if (state.voiceCallOverlaySyncQueued) void syncNativeVoiceCallOverlay();
  }
}

function resetVoiceCallTranscript() {
  const transcript = $("#voice-call-dock-transcript");
  if (transcript) {
    transcript.replaceChildren();
    const empty = document.createElement("p");
    empty.className = "voice-call-dock-empty";
    empty.textContent = "等待你开口";
    transcript.append(empty);
  }
  void syncNativeVoiceCallOverlay();
}

function appendVoiceCallTranscript(role, value) {
  const text = String(value || "").trim();
  const transcript = $("#voice-call-dock-transcript");
  if (!text || !transcript) return;
  transcript.querySelector(".voice-call-dock-empty")?.remove();
  const line = document.createElement("div");
  line.className = `voice-call-dock-line ${role === "user" ? "user" : "assistant"}`;
  const speaker = document.createElement("span");
  speaker.textContent = role === "user" ? "你" : characterName();
  const content = document.createElement("p");
  content.textContent = text.slice(0, 240);
  line.append(speaker, content);
  transcript.append(line);
  const lines = [...transcript.querySelectorAll(".voice-call-dock-line")];
  lines.slice(0, Math.max(0, lines.length - 6)).forEach((item) => item.remove());
  transcript.scrollTop = transcript.scrollHeight;
  void syncNativeVoiceCallOverlay();
}

function setVoiceCallEntryState(active) {
  const chatButton = $("#start-voice-call");
  if (chatButton) chatButton.setAttribute("aria-pressed", String(active));
  const gameButton = $("#game-voice-call");
  if (gameButton) {
    gameButton.setAttribute("aria-pressed", String(active));
    gameButton.innerHTML = active
      ? '<i data-lucide="phone-call"></i><span>通话中</span>'
      : '<i data-lucide="phone"></i><span>语音通话</span>';
  }
  iconRefresh();
}

function formatVoiceCallDuration(totalSeconds) {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  return hours
    ? `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
    : `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

function updateVoiceCallTimer() {
  if (!state.voiceCallActive) return;
  const elapsed = (Date.now() - state.voiceCallStartedAt) / 1000;
  const formatted = formatVoiceCallDuration(elapsed);
  const duration = $("#voice-call-duration");
  duration.textContent = formatted;
  duration.dateTime = `PT${Math.floor(elapsed)}S`;
  const phaseLabel = $("#voice-call-dock-status").dataset.phaseLabel || "通话中";
  $("#voice-call-dock-status").textContent = `${phaseLabel} · ${formatted}`;
  void syncNativeVoiceCallOverlay();
}

function readVoiceCallDockPosition() {
  try {
    const position = JSON.parse(localStorage.getItem(voiceCallDockPositionKey) || "null");
    if (Number.isFinite(position?.x) && Number.isFinite(position?.y)) return position;
  } catch {}
  return null;
}

function saveVoiceCallDockPosition(x, y) {
  try {
    localStorage.setItem(voiceCallDockPositionKey, JSON.stringify({ x: Math.round(x), y: Math.round(y) }));
  } catch {}
}

function positionVoiceCallDock(x, y, persist = false) {
  const dock = $("#voice-call-dock");
  const rect = dock.getBoundingClientRect();
  const chromeHeight = Number.parseFloat(
    getComputedStyle(document.documentElement).getPropertyValue("--window-height")
  ) || 0;
  const margin = 8;
  const maxX = Math.max(margin, window.innerWidth - rect.width - margin);
  const minY = chromeHeight + margin;
  const maxY = Math.max(minY, window.innerHeight - rect.height - margin);
  const left = Math.min(maxX, Math.max(margin, Number(x) || margin));
  const top = Math.min(maxY, Math.max(minY, Number(y) || minY));
  dock.classList.add("is-positioned");
  dock.style.left = `${Math.round(left)}px`;
  dock.style.top = `${Math.round(top)}px`;
  if (persist) saveVoiceCallDockPosition(left, top);
}

function restoreVoiceCallDockPosition() {
  const position = readVoiceCallDockPosition();
  if (position) positionVoiceCallDock(position.x, position.y);
}

function keepVoiceCallDockInView() {
  const dock = $("#voice-call-dock");
  if (!state.voiceCallMinimized || !dock.classList.contains("is-positioned")) return;
  positionVoiceCallDock(Number.parseFloat(dock.style.left), Number.parseFloat(dock.style.top), true);
}

function beginVoiceCallDockDrag(event) {
  if (!state.voiceCallMinimized || event.button !== 0) return;
  const dock = $("#voice-call-dock");
  const rect = dock.getBoundingClientRect();
  state.voiceCallDockDrag = {
    pointerId: event.pointerId,
    pointerX: event.clientX,
    pointerY: event.clientY,
    dockX: rect.left,
    dockY: rect.top,
    moved: false,
  };
  event.currentTarget.setPointerCapture(event.pointerId);
}

function moveVoiceCallDock(event) {
  const drag = state.voiceCallDockDrag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  const deltaX = event.clientX - drag.pointerX;
  const deltaY = event.clientY - drag.pointerY;
  if (!drag.moved && Math.hypot(deltaX, deltaY) < 5) return;
  drag.moved = true;
  $("#voice-call-dock").classList.add("is-dragging");
  positionVoiceCallDock(drag.dockX + deltaX, drag.dockY + deltaY);
  event.preventDefault();
}

function endVoiceCallDockDrag(event) {
  const drag = state.voiceCallDockDrag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  state.voiceCallDockDrag = null;
  const dock = $("#voice-call-dock");
  dock.classList.remove("is-dragging");
  if (!drag.moved) return;
  const rect = dock.getBoundingClientRect();
  positionVoiceCallDock(rect.left, rect.top, true);
  state.voiceCallDockSuppressClick = true;
  setTimeout(() => { state.voiceCallDockSuppressClick = false; }, 0);
}

function getVoiceCallMimeType() {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") return "";
  return ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find((type) => MediaRecorder.isTypeSupported(type)) || "";
}

function startVoiceCallSegment(generation = state.voiceCallGeneration) {
  if (!state.voiceCallActive || generation !== state.voiceCallGeneration || state.voiceCallMuted || state.voiceCallProcessing) return;
  if (!state.voiceCallStream?.active || state.voiceCallRecorder?.state === "recording") return;
  const chunks = [];
  const mimeType = getVoiceCallMimeType();
  const recorder = createVoiceRecorder(state.voiceCallStream);
  state.voiceCallChunks = chunks;
  state.voiceCallRecorder = recorder;
  state.voiceCallDiscardSegment = false;
  state.voiceCallRecordingStartedAt = performance.now();
  state.voiceCallSpeechStartedAt = 0;
  state.voiceCallSilenceStartedAt = 0;
  state.voiceCallVoiceFrames = 0;
  recorder.addEventListener("dataavailable", (event) => { if (event.data.size) chunks.push(event.data); });
  recorder.addEventListener("stop", () => {
    if (state.voiceCallRecorder === recorder) state.voiceCallRecorder = null;
    const discard = state.voiceCallDiscardSegment;
    const blob = new Blob(chunks, { type: recorder.mimeType || mimeType || "audio/webm" });
    state.voiceCallChunks = [];
    if (!state.voiceCallActive || generation !== state.voiceCallGeneration) return;
    if (discard || !blob.size) {
      if (state.voiceCallCompanionPlaying) return;
      state.voiceCallProcessing = false;
      if (!state.voiceCallMuted) startVoiceCallSegment(generation);
      return;
    }
    void processVoiceCallSegment(blob, generation);
  }, { once: true });
  recorder.start(250);
}

function stopVoiceCallSegment(discard = false) {
  const recorder = state.voiceCallRecorder;
  if (!recorder || recorder.state === "inactive") return;
  state.voiceCallDiscardSegment = discard;
  if (!discard) {
    state.voiceCallProcessing = true;
    setVoiceCallPhase("recognizing", "我听到了，正在识别");
    setOperation("thinking", "正在识别语音", "把通话内容转换成文字");
  }
  try { recorder.stop(); } catch (error) { console.warn("voice call recorder stop failed", error); }
}

function resumeVoiceCallListening(generation = state.voiceCallGeneration, caption = "你说吧，我在听") {
  if (!state.voiceCallActive || generation !== state.voiceCallGeneration) return;
  state.voiceCallProcessing = false;
  state.voiceCallSpeechStartedAt = 0;
  state.voiceCallSilenceStartedAt = 0;
  state.voiceCallVoiceFrames = 0;
  if (state.voiceCallMuted) {
    setVoiceCallPhase("muted", "打开麦克风后可以继续说");
    setOperation("idle", "", "通话麦克风已关闭");
    return;
  }
  setVoiceCallPhase("listening", caption);
  setOperation("listening", "正在听你说话", "停顿后会自动发送");
  startVoiceCallSegment(generation);
}

async function processVoiceCallSegment(blob, generation) {
  if (!state.voiceCallActive || generation !== state.voiceCallGeneration) return;
  const controller = new AbortController();
  state.voiceCallAbortController = controller;
  try {
    const audio = await fileToDataUrl(blob);
    const selectedLanguage = $('[data-setting="voice_language"]')?.value || "zh";
    const transcript = await api("/api/transcribe", {
      method: "POST",
      signal: controller.signal,
      body: JSON.stringify({ audio, language: "zh", call_mode: true, context: voiceRecognitionContext() }),
      timeoutMs: 60_000,
    });
    if (!state.voiceCallActive || generation !== state.voiceCallGeneration) return;
    const text = String(transcript.text || "").trim();
    if (!text) {
      setVoiceCallPhase("listening", "这句没听清，再说一次吧");
      setTimeout(() => resumeVoiceCallListening(generation), 900);
      return;
    }
    addMessage("user", text);
    appendVoiceCallTranscript("user", text);
    state.lastUserMessage = text;
    setVoiceCallPhase("thinking", `听到：${text.slice(0, 34)}`);
    setOperation("thinking", `${characterName()}正在想`, "正在回应刚才的话");
    const result = await api("/api/chat", {
      method: "POST",
      signal: controller.signal,
      body: JSON.stringify({
        text,
        images: [],
        quote: null,
        voice: false,
        call_mode: true,
        game_context: state.currentView === "game" || Boolean(state.game?.active),
      }),
      timeoutMs: 180_000,
    });
    if (!state.voiceCallActive || generation !== state.voiceCallGeneration) return;
    const reply = result.reply || "嗯？";
    addMessage("assistant", reply);
    appendVoiceCallTranscript("assistant", reply);
    const voiceText = String(result.voice_text || result.reply || "").trim();
    const voiceLanguage = String(result.voice_language || selectedLanguage || "zh");
    let playback = { started: false, completed: false };
    if (voiceText && ["zh", "ja", "en"].includes(voiceLanguage)) {
      // All calls use one complete GPT-SoVITS file. This keeps ordinary calls,
      // game calls, and companion lines on the same high-quality voice path.
      const rendered = await api("/api/voice/render", {
        method: "POST",
        body: JSON.stringify({
          text: voiceText,
          language: voiceLanguage,
          call_mode: true,
          quality: "complete",
        }),
        timeoutMs: 180_000,
      });
      const audioUrl = String(rendered.audio_url || "").trim();
      if (audioUrl) playback = await playVoiceCallReply(audioUrl, generation);
    }
    if (state.voiceCallActive && generation === state.voiceCallGeneration) {
      resumeVoiceCallListening(
        generation,
        playback.started ? "你说吧，我在听" : "语音播放失败，回复已经显示在对话里",
      );
    }
  } catch (error) {
    if (error.name === "AbortError" || !state.voiceCallActive || generation !== state.voiceCallGeneration) return;
    console.error("voice call turn failed", error);
    setVoiceCallPhase("error", error.message || "这次没听清");
    setOperation("idle", "", "通话仍在继续");
    toast(`通话暂时没接上：${error.message}`, "error");
    setTimeout(() => resumeVoiceCallListening(generation, "再说一次吧，我在听"), 1500);
  } finally {
    if (state.voiceCallAbortController === controller) state.voiceCallAbortController = null;
  }
}

async function playVoiceCallReply(source, generation = state.voiceCallGeneration, options = {}) {
  if (!state.voiceCallActive || generation !== state.voiceCallGeneration) return { started: false, completed: false };
  const audio = $("#voice-call-audio");
  setVoiceCallPhase("thinking", "声音正在生成，马上就好");
  setOperation("thinking", "正在生成声音", "通话语音即将播放");
  audio.pause();
  audio.src = source;
  audio.muted = state.voiceCallSpeakerMuted;
  audio.volume = 1;
  audio.currentTime = 0;
  return await new Promise((resolve) => {
    let settled = false;
    let started = false;
    const startTimeout = window.setTimeout(() => {
      if (started) return;
      console.warn("voice call audio did not start before timeout", source);
      finish(false);
    }, 18_000);
    const finish = (completed) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(startTimeout);
      audio.removeEventListener("playing", markStarted);
      audio.removeEventListener("ended", handleEnded);
      audio.removeEventListener("error", handleError);
      audio.removeEventListener("abort", handleAbort);
      resolve({ started, completed });
    };
    const markStarted = () => {
      started = true;
      setVoiceCallPhase("speaking", options.companion ? `${characterName()}正在和你一起玩` : `${characterName()}正在回答你`);
      setOperation("speaking", `${characterName()}正在说话`, options.companion ? "一起玩游戏中" : "语音通话中");
    };
    const handleEnded = () => finish(true);
    const handleError = () => {
      console.warn("voice call audio error", audio.error);
      finish(false);
    };
    const handleAbort = () => finish(false);
    audio.addEventListener("playing", markStarted, { once: true });
    audio.addEventListener("ended", handleEnded, { once: true });
    audio.addEventListener("error", handleError, { once: true });
    audio.addEventListener("abort", handleAbort, { once: true });
    audio.load();
    const play = audio.play();
    if (play?.catch) play.catch((error) => {
      console.warn("voice call playback failed", error);
      setVoiceCallPhase("error", "系统没有允许自动播放，这次回复已显示在对话里");
      finish(false);
    });
  });
}

async function primeVoiceCallAudio() {
  const audio = $("#voice-call-audio");
  const silentWav = "data:audio/wav;base64,UklGRrQBAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YZABAACAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA";
  try {
    audio.muted = true;
    audio.src = silentWav;
    await audio.play();
  } catch (error) {
    console.debug("voice call audio priming was not available", error);
  } finally {
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    audio.muted = false;
  }
}

function calculateVoiceCallRms(samples) {
  if (!samples?.length) return 0;
  let sum = 0;
  for (const sample of samples) sum += sample * sample;
  return Math.sqrt(sum / samples.length);
}

function handleVoiceCallMeterLevel(rms, generation = state.voiceCallGeneration) {
  if (!state.voiceCallActive || generation !== state.voiceCallGeneration) return;
  if (!Number.isFinite(rms)) return;
  const now = performance.now();
  const panel = $("#voice-call-panel");
  const visualLevel = Math.min(1, Math.max(0, (rms - state.voiceCallNoiseFloor) * 12));
  if (!state.voiceCallProcessing && !state.voiceCallMuted) panel?.style.setProperty("--call-level", visualLevel.toFixed(3));

  if (now < state.voiceCallCalibrationUntil) {
    state.voiceCallNoiseFloor = state.voiceCallNoiseFloor * 0.86 + rms * 0.14;
  } else if (!state.voiceCallProcessing && !state.voiceCallMuted && state.voiceCallRecorder?.state === "recording") {
    const threshold = Math.max(0.018, Math.min(0.09, state.voiceCallNoiseFloor * 2.6));
    const speech = rms > threshold;
    if (speech) {
      state.voiceCallVoiceFrames += 1;
      state.voiceCallSilenceStartedAt = 0;
      if (!state.voiceCallSpeechStartedAt && state.voiceCallVoiceFrames >= 3) {
        state.voiceCallSpeechStartedAt = now;
        setVoiceCallPhase("recording", "听到了，说完停一下就好");
      }
    } else if (state.voiceCallSpeechStartedAt) {
      if (!state.voiceCallSilenceStartedAt) state.voiceCallSilenceStartedAt = now;
      if (now - state.voiceCallSilenceStartedAt >= 800 && now - state.voiceCallSpeechStartedAt >= 350) stopVoiceCallSegment(false);
    } else {
      state.voiceCallVoiceFrames = 0;
      state.voiceCallNoiseFloor = state.voiceCallNoiseFloor * 0.995 + rms * 0.005;
      if (now - state.voiceCallRecordingStartedAt >= 2500) stopVoiceCallSegment(true);
    }
    if (state.voiceCallSpeechStartedAt && now - state.voiceCallSpeechStartedAt >= 18000) stopVoiceCallSegment(false);
  }
}

async function startVoiceCallMeter(context, source, generation) {
  const connectSilentSink = (node) => {
    const sink = context.createGain();
    sink.gain.value = 0;
    node.connect(sink);
    sink.connect(context.destination);
    state.voiceCallMeterSink = sink;
  };

  if (context.audioWorklet && typeof AudioWorkletNode !== "undefined") {
    const processorSource = `
      class XixiVoiceCallMeterProcessor extends AudioWorkletProcessor {
        constructor() {
          super();
          this.sumSquares = 0;
          this.sampleCount = 0;
          this.blocks = 0;
        }
        process(inputs) {
          const channel = inputs[0] && inputs[0][0];
          if (channel && channel.length) {
            for (let index = 0; index < channel.length; index += 1) {
              this.sumSquares += channel[index] * channel[index];
            }
            this.sampleCount += channel.length;
          }
          this.blocks += 1;
          if (this.blocks >= 4) {
            const rms = this.sampleCount ? Math.sqrt(this.sumSquares / this.sampleCount) : 0;
            this.port.postMessage(rms);
            this.sumSquares = 0;
            this.sampleCount = 0;
            this.blocks = 0;
          }
          return true;
        }
      }
      registerProcessor("xixi-voice-call-meter", XixiVoiceCallMeterProcessor);
    `;
    const moduleUrl = URL.createObjectURL(new Blob([processorSource], { type: "text/javascript" }));
    try {
      await context.audioWorklet.addModule(moduleUrl);
      if (!state.voiceCallActive || generation !== state.voiceCallGeneration) return;
      const node = new AudioWorkletNode(context, "xixi-voice-call-meter", {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        outputChannelCount: [1],
      });
      node.port.onmessage = (event) => handleVoiceCallMeterLevel(Number(event.data), generation);
      source.connect(node);
      connectSilentSink(node);
      state.voiceCallMeterNode = node;
      state.voiceCallMeterMode = "audio-worklet";
      return;
    } catch (error) {
      console.debug("audio worklet meter was not available", error);
    } finally {
      URL.revokeObjectURL(moduleUrl);
    }
  }

  if (typeof context.createScriptProcessor === "function") {
    const processor = context.createScriptProcessor(2048, 1, 1);
    processor.onaudioprocess = (event) => {
      if (!state.voiceCallActive || generation !== state.voiceCallGeneration) return;
      handleVoiceCallMeterLevel(calculateVoiceCallRms(event.inputBuffer.getChannelData(0)), generation);
    };
    source.connect(processor);
    connectSilentSink(processor);
    state.voiceCallMeterNode = processor;
    state.voiceCallMeterMode = "script-processor";
    return;
  }

  state.voiceCallMeterMode = "analyser-timer";
  state.voiceCallMeterInterval = window.setInterval(() => {
    const analyser = state.voiceCallAnalyser;
    const data = state.voiceCallMeterData;
    if (!analyser || !data) return;
    analyser.getFloatTimeDomainData(data);
    handleVoiceCallMeterLevel(calculateVoiceCallRms(data), generation);
  }, 50);
}

async function keepVoiceCallAudioAlive(generation = state.voiceCallGeneration) {
  if (!state.voiceCallActive || generation !== state.voiceCallGeneration) return;
  const context = state.voiceCallAudioContext;
  if (context?.state === "suspended") {
    try { await context.resume(); } catch (error) { console.debug("voice call audio resume failed", error); }
  }
  if (
    state.voiceCallActive
    && !state.voiceCallMuted
    && !state.voiceCallProcessing
    && state.voiceCallStream?.active
    && state.voiceCallRecorder?.state !== "recording"
  ) {
    startVoiceCallSegment(generation);
  }
}

async function startVoiceCall(options = {}) {
  if (state.voiceCallActive) {
    if (options.minimize) {
      state.voiceCallMinimized = true;
      $("#voice-call-layer").classList.add("is-minimized");
      const desktopApi = window.pywebview?.api;
      if (typeof desktopApi?.show_call_overlay === "function") {
        try { await desktopApi.show_call_overlay(); } catch (error) { console.debug("could not show call overlay", error); }
      }
      void syncNativeVoiceCallOverlay();
    } else {
      restoreVoiceCall();
    }
    return;
  }
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    toast("当前环境不支持麦克风通话", "error");
    return;
  }
  if (state.sending) {
    toast("等昔夕回复完这条消息再开始通话", "error");
    return;
  }
  if (state.voiceInputOpen) closeVoiceInput();
  const generation = ++state.voiceCallGeneration;
  state.voiceCallActive = true;
  state.voiceCallMinimized = false;
  state.voiceCallMuted = false;
  state.voiceCallSpeakerMuted = false;
  state.voiceCallCompanionPlaying = false;
  state.gameOwnedVoiceCall = Boolean(options.gameOwned);
  state.voiceCallProcessing = true;
  state.voiceCallStartedAt = Date.now();
  state.voiceCallNoiseFloor = 0.012;
  resetVoiceCallTranscript();
  const layer = $("#voice-call-layer");
  layer.hidden = false;
  layer.classList.remove("is-minimized");
  document.body.classList.add("voice-call-open");
  setVoiceCallEntryState(true);
  const microphoneButton = $("#toggle-call-microphone");
  microphoneButton.setAttribute("aria-pressed", "false");
  microphoneButton.setAttribute("aria-label", "关闭麦克风");
  microphoneButton.querySelector("small").textContent = "麦克风";
  microphoneButton.querySelector("span").innerHTML = '<i data-lucide="mic"></i>';
  const speakerButton = $("#toggle-call-speaker");
  speakerButton.setAttribute("aria-pressed", "false");
  speakerButton.setAttribute("aria-label", "关闭扬声器");
  speakerButton.querySelector("small").textContent = "扬声器";
  speakerButton.querySelector("span").innerHTML = '<i data-lucide="volume-2"></i>';
  iconRefresh();
  $("#voice-call-duration").textContent = "00:00";
  $("#voice-call-dock-status").dataset.phaseLabel = "正在连接";
  setVoiceCallPhase("connecting", "正在启用麦克风");
  updateVoiceCallTimer();
  state.voiceCallTimer = setInterval(updateVoiceCallTimer, 1000);
  const selectedLanguage = $('[data-setting="voice_language"]')?.value || "zh";
  void api("/api/voice/prewarm", {
    method: "POST",
    body: JSON.stringify({ language: selectedLanguage, call_mode: true }),
    timeoutMs: 15_000,
  }).catch((error) => console.debug("call voice prewarm was not available", error));
  try {
    await primeVoiceCallAudio();
    const stream = await requestMicrophoneStream();
    if (!state.voiceCallActive || generation !== state.voiceCallGeneration) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    state.voiceCallStream = stream;
    stream.getAudioTracks().forEach((track) => track.addEventListener("ended", () => {
      if (!state.voiceCallActive || generation !== state.voiceCallGeneration) return;
      endVoiceCall({ silent: true });
      toast("麦克风连接已断开，通话已结束", "error");
    }, { once: true }));
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    const context = new AudioContextClass();
    await context.resume();
    const source = context.createMediaStreamSource(stream);
    const analyser = context.createAnalyser();
    analyser.fftSize = 2048;
    analyser.smoothingTimeConstant = 0.28;
    source.connect(analyser);
    state.voiceCallAudioContext = context;
    state.voiceCallSource = source;
    state.voiceCallAnalyser = analyser;
    state.voiceCallMeterData = new Float32Array(analyser.fftSize);
    state.voiceCallCalibrationUntil = performance.now() + 700;
    state.voiceCallProcessing = false;
    setVoiceCallPhase("calibrating", "稍等一下，正在适应环境声音");
    startVoiceCallSegment(generation);
    await startVoiceCallMeter(context, source, generation);
    state.voiceCallAudioKeepaliveTimer = window.setInterval(() => {
      void keepVoiceCallAudioAlive(generation);
    }, 1000);
    if (options.minimize) minimizeVoiceCall({ restoreGameFocus: Boolean(state.game?.active) });
    setTimeout(() => {
      if (!state.voiceCallActive || generation !== state.voiceCallGeneration || state.voiceCallProcessing) return;
      setVoiceCallPhase("listening", "你说吧，我在听");
      setOperation("listening", "正在听你说话", "停顿后会自动发送");
    }, 720);
  } catch (error) {
    if (!state.voiceCallActive || generation !== state.voiceCallGeneration) return;
    toast(`无法开始通话：${error.message}`, "error");
    endVoiceCall({ silent: true });
  }
}

function toggleVoiceCallMicrophone() {
  if (!state.voiceCallActive) return;
  state.voiceCallMuted = !state.voiceCallMuted;
  state.voiceCallStream?.getAudioTracks().forEach((track) => { track.enabled = !state.voiceCallMuted; });
  const button = $("#toggle-call-microphone");
  button.setAttribute("aria-pressed", String(state.voiceCallMuted));
  button.setAttribute("aria-label", state.voiceCallMuted ? "打开麦克风" : "关闭麦克风");
  button.querySelector("small").textContent = state.voiceCallMuted ? "已静音" : "麦克风";
  button.querySelector("span").innerHTML = `<i data-lucide="${state.voiceCallMuted ? "mic-off" : "mic"}"></i>`;
  iconRefresh();
  if (state.voiceCallMuted) {
    if (!state.voiceCallProcessing) stopVoiceCallSegment(true);
    setVoiceCallPhase("muted", "麦克风已关闭");
    setOperation("idle", "", "通话麦克风已关闭");
  } else if (!state.voiceCallProcessing) {
    resumeVoiceCallListening();
  }
}

function toggleVoiceCallSpeaker() {
  if (!state.voiceCallActive) return;
  state.voiceCallSpeakerMuted = !state.voiceCallSpeakerMuted;
  const audio = $("#voice-call-audio");
  audio.muted = state.voiceCallSpeakerMuted;
  const button = $("#toggle-call-speaker");
  button.setAttribute("aria-pressed", String(state.voiceCallSpeakerMuted));
  button.setAttribute("aria-label", state.voiceCallSpeakerMuted ? "打开扬声器" : "关闭扬声器");
  button.querySelector("small").textContent = state.voiceCallSpeakerMuted ? "已静音" : "扬声器";
  button.querySelector("span").innerHTML = `<i data-lucide="${state.voiceCallSpeakerMuted ? "volume-x" : "volume-2"}"></i>`;
  iconRefresh();
}

function minimizeVoiceCall(options = {}) {
  if (!state.voiceCallActive) return;
  state.voiceCallMinimized = true;
  $("#voice-call-layer").classList.add("is-minimized");
  void syncNativeVoiceCallOverlay();
  requestAnimationFrame(restoreVoiceCallDockPosition);
  if (!options.restoreGameFocus) {
    $("#restore-voice-call").focus();
  }
}

function restoreVoiceCall() {
  if (!state.voiceCallActive) return;
  state.voiceCallMinimized = false;
  $("#voice-call-layer").classList.remove("is-minimized");
  void syncNativeVoiceCallOverlay();
  $("#end-voice-call").focus();
}

function endVoiceCall(options = {}) {
  if (!state.voiceCallActive) return;
  state.voiceCallActive = false;
  state.voiceCallMinimized = false;
  state.voiceCallGeneration += 1;
  state.voiceCallAbortController?.abort();
  state.voiceCallAbortController = null;
  if (state.voiceCallTimer) clearInterval(state.voiceCallTimer);
  state.voiceCallTimer = null;
  if (state.voiceCallMeterInterval) clearInterval(state.voiceCallMeterInterval);
  state.voiceCallMeterInterval = null;
  if (state.voiceCallAudioKeepaliveTimer) clearInterval(state.voiceCallAudioKeepaliveTimer);
  state.voiceCallAudioKeepaliveTimer = null;
  const recorder = state.voiceCallRecorder;
  state.voiceCallDiscardSegment = true;
  if (recorder?.state && recorder.state !== "inactive") {
    try { recorder.stop(); } catch {}
  }
  state.voiceCallRecorder = null;
  state.voiceCallChunks = [];
  state.voiceCallStream?.getTracks().forEach((track) => track.stop());
  state.voiceCallStream = null;
  try { state.voiceCallSource?.disconnect(); } catch {}
  state.voiceCallSource = null;
  if (state.voiceCallMeterNode) {
    if ("port" in state.voiceCallMeterNode) state.voiceCallMeterNode.port.onmessage = null;
    if ("onaudioprocess" in state.voiceCallMeterNode) state.voiceCallMeterNode.onaudioprocess = null;
    try { state.voiceCallMeterNode.disconnect(); } catch {}
  }
  state.voiceCallMeterNode = null;
  try { state.voiceCallMeterSink?.disconnect(); } catch {}
  state.voiceCallMeterSink = null;
  state.voiceCallMeterMode = "";
  state.voiceCallAnalyser = null;
  state.voiceCallMeterData = null;
  const context = state.voiceCallAudioContext;
  state.voiceCallAudioContext = null;
  if (context && context.state !== "closed") void context.close().catch(() => {});
  const audio = $("#voice-call-audio");
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  audio.muted = false;
  state.voiceCallProcessing = false;
  state.voiceCallMuted = false;
  state.voiceCallSpeakerMuted = false;
  state.voiceCallCompanionPlaying = false;
  state.gameOwnedVoiceCall = false;
  resetVoiceCallTranscript();
  $("#voice-call-layer").hidden = true;
  $("#voice-call-layer").classList.remove("is-minimized");
  setVoiceCallEntryState(false);
  document.body.classList.remove("voice-call-open");
  setOperation("idle", "", "语音通话已结束");
  if (!options.silent) toast("语音通话已结束");
  void api("/api/game/stop", {
    method: "POST",
    body: "{}",
    timeoutMs: 10000,
  }).then(renderGameStatus).catch((error) => {
    console.warn("挂断通话后关闭游戏陪伴失败", error);
  });
}

function memoryCategoryLabel(category) {
  const normalized = String(category || "general").trim().toLowerCase();
  return {
    relationship: "关系记忆",
    self_identity: "自我认知",
    identity: "身份认知",
    explicit: "明确记忆",
    plan: "计划与约定",
    preference: "偏好习惯",
    emotion: "情绪感受",
    knowledge: "知识见闻",
    web: "联网知识",
    profile: "人物档案",
    general: "一般记忆",
  }[normalized] || String(category || "一般记忆").replaceAll("_", " ");
}

function memoryCollectionFor(item) {
  if (String(item?.scope || "").toLowerCase() === "web") {
    return memoryCollectionCatalog.find((collection) => collection.id === "knowledge");
  }
  const category = String(item?.category || "").trim().toLowerCase();
  const direct = memoryCollectionCatalog.find((collection) => (
    collection.categoryTokens.some((token) => category === token || category.includes(token))
  ));
  if (direct) return direct;
  const content = String(item?.content || "");
  const inferredOrder = ["relationships", "identity", "preferences", "plans", "emotions", "experiences", "knowledge"];
  for (const id of inferredOrder) {
    const collection = memoryCollectionCatalog.find((entry) => entry.id === id);
    if (collection?.contentPattern?.test(content)) return collection;
  }
  return memoryCollectionCatalog.find((collection) => collection.id === "general");
}

function memoryGroups(items = []) {
  const groups = new Map(memoryCollectionCatalog.map((collection) => [collection.id, []]));
  items.forEach((item) => groups.get(memoryCollectionFor(item).id).push(item));
  return groups;
}

function memoryExcerpt(content, limit = 92) {
  const text = String(content || "").replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, limit)}……` : text;
}

function memoryCardText(content) {
  const text = String(content || "").replace(/\s+/g, " ").trim();
  const sentenceEnd = text.search(/[。！？!?；;]/u);
  const titleEnd = sentenceEnd >= 5 && sentenceEnd < 32 ? sentenceEnd + 1 : Math.min(26, text.length);
  const title = text.length > titleEnd ? `${text.slice(0, titleEnd)}……` : text;
  const remainder = text.slice(titleEnd).replace(/^[，。！？!?；;、\s]+/u, "").trim();
  return { title, excerpt: remainder ? memoryExcerpt(remainder, 96) : "" };
}

function memorySpineLabel(item) {
  const text = String(item?.content || "").replace(/\s+/g, " ").trim();
  const phrase = text.split(/[，,。！？!?；;：:]/u).find((part) => part.trim())?.trim() || memoryCategoryLabel(item?.category);
  return phrase.length > 10 ? phrase.slice(0, 10) : phrase;
}

function createMemoryBookSpine(item, collection, index) {
  const book = document.createElement("button");
  book.type = "button";
  book.className = `memory-book-spine memory-tone-${collection.id}`;
  book.dataset.memoryOpenId = item.id;
  book.dataset.memoryCollection = collection.id;
  book.style.setProperty("--book-height", `${126 + ((index * 17 + Number(item.importance || 0) * 5) % 42)}px`);
  book.style.setProperty("--book-width", `${48 + ((index * 11) % 18)}px`);
  book.classList.toggle("is-treasure", Number(item.importance) >= 10);
  book.title = String(item.content || "打开这条记忆");
  const title = document.createElement("span");
  title.className = "memory-book-spine-title";
  title.textContent = memorySpineLabel(item);
  const marker = document.createElement("span");
  marker.className = "memory-book-spine-marker";
  marker.innerHTML = Number(item.importance) >= 10
    ? '<i data-lucide="lock-keyhole"></i>'
    : `<strong>${Number(item.importance || 5)}</strong>`;
  book.append(title, marker);
  return book;
}

function createMemoryShelf(collection, items) {
  const shelf = document.createElement("section");
  shelf.className = `memory-shelf memory-tone-${collection.id}`;
  const heading = document.createElement("header");
  heading.innerHTML = `<span class="memory-shelf-icon"><i data-lucide="${collection.icon}"></i></span><div><strong></strong><p></p></div><button type="button" data-memory-collection="${collection.id}"><span></span><i data-lucide="chevron-right"></i></button>`;
  heading.querySelector("strong").textContent = collection.title;
  heading.querySelector("p").textContent = collection.description;
  heading.querySelector("button span").textContent = `${items.length} 本`;
  const books = document.createElement("div");
  books.className = "memory-shelf-books";
  items.slice(0, 6).forEach((item, index) => books.append(createMemoryBookSpine(item, collection, index)));
  if (items.length > 6) {
    const more = document.createElement("button");
    more.type = "button";
    more.className = "memory-shelf-more";
    more.dataset.memoryCollection = collection.id;
    more.innerHTML = `<strong>+${items.length - 6}</strong><span>继续翻阅</span>`;
    books.append(more);
  }
  const board = document.createElement("div");
  board.className = "memory-shelf-board";
  shelf.append(heading, books, board);
  return shelf;
}

function createMemoryBookCard(item, collection, index) {
  const card = document.createElement("article");
  card.className = `memory-book-card memory-tone-${collection.id}`;
  card.dataset.memoryRow = item.id;
  card.style.setProperty("--book-order", String(index % 4));
  card.classList.toggle("selected", String(item.id) === state.selectedMemoryId);
  const open = document.createElement("button");
  open.type = "button";
  open.className = "memory-book-open";
  open.dataset.memoryOpenId = item.id;
  open.dataset.memoryCollection = collection.id;
  const protectedMemory = Number(item.importance) >= 10;
  card.classList.toggle("is-treasure", protectedMemory);
  const cardText = memoryCardText(item.content);
  open.innerHTML = `<span class="memory-book-mark"><i data-lucide="${protectedMemory ? "lock-keyhole" : "bookmark"}"></i></span><span class="memory-book-category"></span><strong class="memory-book-title"></strong><span class="memory-book-excerpt"></span><span class="memory-book-meta"><span></span><time></time></span>`;
  open.querySelector(".memory-book-category").textContent = memoryCategoryLabel(item.category);
  open.querySelector(".memory-book-title").textContent = cardText.title;
  const excerpt = open.querySelector(".memory-book-excerpt");
  excerpt.textContent = cardText.excerpt;
  excerpt.hidden = !cardText.excerpt;
  open.querySelector(".memory-book-meta span").textContent = `重要度 ${Number(item.importance || 5)}/10`;
  open.querySelector("time").textContent = formatDate(item.updated_at);
  const actions = document.createElement("div");
  actions.className = "memory-book-actions";
  const edit = document.createElement("button");
  edit.type = "button";
  edit.className = "icon-button";
  edit.title = "修改记忆";
  edit.setAttribute("aria-label", "修改记忆");
  edit.dataset.memoryEditId = item.id;
  edit.innerHTML = '<i data-lucide="pencil"></i>';
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = `icon-button table-action-danger${protectedMemory ? " table-action-protected" : ""}`;
  remove.title = protectedMemory ? "重要度 10 · 不能直接删除" : "删除记忆";
  remove.setAttribute("aria-label", protectedMemory ? "重要记忆受到保护" : "删除记忆");
  remove.dataset.memoryDeleteId = item.id;
  remove.innerHTML = `<i data-lucide="${protectedMemory ? "lock-keyhole" : "trash-2"}"></i>`;
  actions.append(edit, remove);
  card.append(open, actions);
  return card;
}

function clearMemorySelection() {
  state.selectedMemoryId = "";
  $("#inspector-memory-title").textContent = "尚未选择";
  $("#inspector-memory-copy").textContent = "从书架中打开一条记忆";
  $("#inspector-memory-meta").replaceChildren();
  $("#inspector-edit-memory").disabled = true;
  $("#memory-reading-desk").hidden = true;
}

function renderMemoryCollectionView(collection, items, { search = false } = {}) {
  $("#memory-shelves").hidden = true;
  $("#memory-collection-view").hidden = false;
  $("#memory-library-back").hidden = false;
  $("#memory-library-title").textContent = "记忆馆藏";
  $("#memory-library-copy").textContent = search
    ? `找到 ${items.length} 条与“${$("#memory-query").value.trim()}”有关的记忆`
    : `正在翻阅「${collection.title}」书架`;
  $("#memory-collection-title").textContent = search ? "检索结果" : collection.title;
  $("#memory-collection-copy").textContent = search ? "结果来自所有书架，按重要度与更新时间排列" : collection.description;
  $("#memory-collection-count").textContent = `${items.length} 本`;
  $("#memory-collection-icon").innerHTML = `<i data-lucide="${search ? "search" : collection.icon}"></i>`;
  const grid = $("#memory-book-grid");
  grid.replaceChildren(...items.map((item, index) => createMemoryBookCard(item, search ? memoryCollectionFor(item) : collection, index)));
  $("#memory-empty").hidden = items.length > 0;
  if (!items.some((item) => String(item.id) === state.selectedMemoryId)) $("#memory-reading-desk").hidden = true;
}

function renderMemoryLibrary(items = []) {
  const groups = memoryGroups(items);
  const populated = memoryCollectionCatalog.filter((collection) => groups.get(collection.id).length);
  $("#memory-library-count").textContent = items.length.toLocaleString("zh-CN");
  $("#memory-library-collection-count").textContent = populated.length.toLocaleString("zh-CN");
  $("#memory-library-treasure-count").textContent = items.filter((item) => Number(item.importance) >= 10).length.toLocaleString("zh-CN");
  const query = $("#memory-query").value.trim();
  if (query) {
    renderMemoryCollectionView({ id: "search", title: "检索结果", icon: "search", description: "" }, items, { search: true });
    return;
  }
  const activeCollection = memoryCollectionCatalog.find((collection) => collection.id === state.memoryActiveCollection);
  if (activeCollection) {
    renderMemoryCollectionView(activeCollection, groups.get(activeCollection.id));
    return;
  }
  $("#memory-library-title").textContent = "记忆馆藏";
  $("#memory-library-copy").textContent = items.length ? `已整理为 ${populated.length} 个主题书架` : "这里还没有可以陈列的记忆";
  $("#memory-library-back").hidden = true;
  $("#memory-collection-view").hidden = true;
  $("#memory-reading-desk").hidden = true;
  const shelves = $("#memory-shelves");
  shelves.hidden = false;
  shelves.replaceChildren(...populated.map((collection) => createMemoryShelf(collection, groups.get(collection.id))));
  $("#memory-empty").hidden = items.length > 0;
}

async function loadMemories() {
  const query = encodeURIComponent($("#memory-query").value.trim());
  const scope = encodeURIComponent($("#memory-scope").value);
  const categorySelect = $("#memory-category-filter");
  const category = encodeURIComponent(categorySelect?.value || "");
  try {
    const result = await api(`/api/memories?query=${query}&scope=${scope}&category=${category}&limit=1000`);
    if (categorySelect) {
      const selectedCategory = categorySelect.value;
      categorySelect.replaceChildren(new Option("全部类别", ""), ...(result.categories || []).map((item) => new Option(`${item.name} (${item.count})`, item.name)));
      categorySelect.value = [...categorySelect.options].some((option) => option.value === selectedCategory) ? selectedCategory : "";
    }
    const items = result.items || [];
    state.memoryItems = new Map(items.map((item) => [String(item.id), item]));
    renderMemoryLibrary(items);
    if (state.selectedMemoryId && state.memoryItems.has(state.selectedMemoryId)) selectMemory(state.selectedMemoryId);
    else if (state.selectedMemoryId) clearMemorySelection();
    iconRefresh();
  } catch (error) { toast(error.message, "error"); }
}

function selectMemory(memoryId) {
  const item = state.memoryItems.get(String(memoryId));
  if (!item) return;
  state.selectedMemoryId = String(memoryId);
  $$('[data-memory-row]').forEach((row) => row.classList.toggle("selected", row.dataset.memoryRow === state.selectedMemoryId));
  const collection = memoryCollectionFor(item);
  const category = memoryCategoryLabel(item.category);
  $("#inspector-memory-title").textContent = category;
  $("#inspector-memory-copy").textContent = item.content;
  $("#inspector-memory-meta").innerHTML = `<span>书架</span><strong>${collection.title}</strong><span>重要度</span><strong>${item.importance ?? 5}/10</strong><span>更新</span><strong>${formatDate(item.updated_at)}</strong>`;
  $("#inspector-edit-memory").disabled = false;
  $("#memory-reader-shelf").textContent = collection.title;
  $("#memory-reader-title").textContent = category;
  $("#memory-reader-content").textContent = item.content;
  $("#memory-reader-scope").textContent = formatScope(item.scope);
  $("#memory-reader-importance").textContent = `${item.importance ?? 5}/10`;
  $("#memory-reader-updated").textContent = formatDate(item.updated_at);
  const deleteButton = $("#memory-reader-delete");
  const protectedMemory = Number(item.importance) >= 10;
  const readingDesk = $("#memory-reading-desk");
  readingDesk.className = `memory-reading-desk memory-tone-${collection.id}${protectedMemory ? " is-treasure" : ""}`;
  deleteButton.classList.toggle("table-action-protected", protectedMemory);
  deleteButton.title = protectedMemory ? "重要度 10 · 不能直接删除" : "删除记忆";
  deleteButton.setAttribute("aria-label", protectedMemory ? "重要记忆受到保护" : "删除记忆");
  deleteButton.innerHTML = `<i data-lucide="${protectedMemory ? "lock-keyhole" : "trash-2"}"></i>`;
  readingDesk.hidden = false;
  iconRefresh();
}

function renderChatContextMemories(items = []) {
  const host = $("#inspector-chat-memories");
  if (!items.length) {
    host.innerHTML = "<span>当前没有需要特别带入的记忆</span>";
    return;
  }
  host.replaceChildren(...items.slice(0, 4).map((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.chatMemoryId = item.id;
    button.dataset.chatMemoryContent = item.content;
    button.innerHTML = "<strong></strong><span></span>";
    button.querySelector("strong").textContent = item.category || "记忆";
    button.querySelector("span").textContent = item.content;
    return button;
  }));
}

async function loadChatContextMemories() {
  const latest = [...state.chatHistory].reverse().find((item) => item.role === "user")?.content || state.lastUserMessage || "";
  const query = latest.trim().slice(0, 80);
  try {
    let result = await api(`/api/memories?query=${encodeURIComponent(query)}&scope=&category=&limit=4`);
    if (query && !result.items?.length) result = await api("/api/memories?query=&scope=&category=&limit=4");
    renderChatContextMemories(result.items || []);
  } catch {
    renderChatContextMemories([]);
  }
}

function openMemoryDialog(memoryId) {
  const item = state.memoryItems.get(String(memoryId));
  if (!item) return;
  $("#memory-id").value = item.id;
  $("#memory-content").value = item.content;
  $("#memory-category").value = item.category || "general";
  $("#memory-importance").value = item.importance ?? 5;
  $("#memory-confidence").value = item.confidence ?? 0.7;
  const deleteButton = $("#delete-memory");
  const protectedMemory = Number(item.importance) >= 10;
  deleteButton.classList.toggle("protected-memory-button", protectedMemory);
  deleteButton.title = protectedMemory ? "重要度 10 · 请先降低重要度" : "删除记忆";
  deleteButton.innerHTML = protectedMemory
    ? '<i data-lucide="lock-keyhole"></i><span>重要记忆受保护</span>'
    : '<i data-lucide="archive-x"></i><span>停用记忆</span>';
  iconRefresh();
  $("#memory-dialog").showModal();
  setTimeout(() => $("#memory-content").focus(), 0);
}

async function saveMemory(event) {
  event.preventDefault();
  const id = $("#memory-id").value;
  try {
    await api(`/api/memories/${id}`, { method: "PUT", body: JSON.stringify({
      content: $("#memory-content").value,
      category: $("#memory-category").value,
      importance: Number($("#memory-importance").value),
      confidence: Number($("#memory-confidence").value),
    }) });
    $("#memory-dialog").close(); await loadMemories(); toast("记忆已修改");
  } catch (error) { toast(error.message, "error"); }
}

async function deleteMemoryById(id, { closeDialog = false, button = null } = {}) {
  if (!id) return false;
  const item = state.memoryItems.get(String(id));
  if (Number(item?.importance) >= 10) {
    await showProtectedMemoryNotice();
    return false;
  }
  const content = String(item?.content || $("#memory-content")?.value || "这条记忆").trim();
  const excerpt = content.length > 46 ? `${content.slice(0, 46)}……` : content;
  const confirmed = await confirmAction({
    kicker: "记忆管理",
    title: "删除这条记忆？",
    message: "删除后，昔夕不会再主动回忆或使用这条内容。",
    detail: `“${excerpt}”`,
    note: "记录会进入本地归档，不会被立即永久抹除。",
    confirmLabel: "删除记忆",
    icon: "trash-2",
    actionIcon: "trash-2",
  });
  if (!confirmed) return false;
  if (button) {
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
  }
  try {
    await api(`/api/memories/${id}`, { method: "DELETE" });
    if (closeDialog) $("#memory-dialog").close();
    await loadMemories();
    toast("这条记忆已删除");
    return true;
  } catch (error) {
    if (error.message === "此记忆很重要不能直接删除，一定要删除的话请手动降低重要度") {
      await showProtectedMemoryNotice();
      return false;
    }
    toast(error.message, "error");
    return false;
  } finally {
    if (button) {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }
  }
}

async function deleteMemory() {
  await deleteMemoryById($("#memory-id").value, {
    closeDialog: true,
    button: $("#delete-memory"),
  });
}

function diagnosticStateLabel(value) {
  return { ok: "正常", warning: "需留意", error: "异常", paused: "已暂停" }[value] || value;
}

function renderDiagnostics(result) {
  $("#diagnostic-ok").textContent = result.summary.ok;
  $("#diagnostic-attention").textContent = result.summary.attention;
  $("#diagnostic-paused").textContent = result.summary.paused;
  $("#diagnostic-time").textContent = `${formatDate(result.checked_at)} · 用时 ${result.duration_ms} ms`;
  $("#diagnostic-list").replaceChildren(...result.items.map((item) => {
    const row = document.createElement("article"); row.className = `diagnostic-item state-${item.state}`;
    const icon = document.createElement("span"); icon.className = "diagnostic-icon"; icon.innerHTML = `<i data-lucide="${item.state === "ok" ? "check" : item.state === "paused" ? "pause" : "triangle-alert"}"></i>`;
    const copy = document.createElement("div"); copy.innerHTML = `<strong></strong><p></p>`; copy.querySelector("strong").textContent = item.label; copy.querySelector("p").textContent = item.detail;
    const stateLabel = document.createElement("span"); stateLabel.className = "diagnostic-state"; stateLabel.textContent = diagnosticStateLabel(item.state);
    row.append(icon, copy, stateLabel);
    if (item.repair) { const repair = document.createElement("button"); repair.className = "secondary-button"; repair.dataset.repairService = item.repair; repair.innerHTML = '<i data-lucide="rotate-cw"></i><span>重启模块</span>'; row.append(repair); }
    return row;
  }));
  iconRefresh();
}

async function loadDiagnostics(run = false) {
  const button = $("#run-diagnostics");
  const buttonLabel = button?.querySelector("span");
  if (button) {
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
  }
  if (buttonLabel) buttonLabel.textContent = "检查中";
  try {
    let result = await api(run ? "/api/diagnostics/run" : "/api/diagnostics", run ? { method: "POST", body: "{}" } : {});
    if (!run && !result.items?.length) {
      result = await api("/api/diagnostics/run", { method: "POST", body: "{}" });
    }
    renderDiagnostics(result);
  }
  catch (error) { toast(error.message, "error"); }
  finally {
    if (button) {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }
    if (buttonLabel) buttonLabel.textContent = "检查全部";
  }
}

async function repairService(service) {
  try {
    await api("/api/diagnostics/repair", { method: "POST", body: JSON.stringify({ service }) });
    toast("模块已重新启动"); await loadDiagnostics(true); await loadStatus();
  } catch (error) { toast(error.message, "error"); }
}

function renderActivities(items) {
  const host = $("#activity-list");
  host.replaceChildren(...items.map((item) => {
    const row = document.createElement("article"); row.className = "activity-item";
    const marker = document.createElement("span"); marker.className = `activity-marker ${item.status}`;
    const copy = document.createElement("div");
    const head = document.createElement("div"); head.className = "activity-item-head";
    const title = document.createElement("strong"); title.textContent = item.title;
    const time = document.createElement("time"); time.textContent = formatDate(item.created_at);
    head.append(title, time);
    const detail = document.createElement("p"); detail.textContent = item.detail || "已完成";
    copy.append(head, detail);
    const tag = document.createElement("span"); tag.className = "activity-tag"; tag.textContent = { instruction: "指令", autonomy: "主动", learning: "学习", weather: "天气", game: "游戏", memory: "记忆", diagnostic: "诊断", backup: "备份", desktop: "桌面" }[item.category] || item.category;
    row.append(marker, copy, tag);
    if (item.metadata?.steps?.length || item.metadata?.output_plan?.length) {
      const details = document.createElement("details"); const summary = document.createElement("summary"); summary.textContent = `查看 ${item.metadata.steps?.length || 0} 个执行步骤`; const pre = document.createElement("pre"); pre.textContent = JSON.stringify(item.metadata, null, 2); details.append(summary, pre); copy.append(details);
    }
    return row;
  }));
  if (!items.length) host.innerHTML = '<div class="table-empty">还没有匹配的活动记录</div>';
}

async function loadActivities() {
  try { renderActivities((await api(`/api/activities?limit=120&category=${encodeURIComponent($("#activity-category").value)}`)).items); }
  catch (error) { toast(error.message, "error"); }
}

async function loadContexts() {
  try {
    const result = await api("/api/contexts?limit=180");
    const host = $("#context-board");
    host.replaceChildren(...result.items.map((context) => {
      const card = document.createElement("article"); card.className = "context-thread";
      const head = document.createElement("div"); head.className = "context-thread-head"; head.innerHTML = '<span><i data-lucide="messages-square"></i></span><div><strong></strong><small></small></div>'; head.querySelector("strong").textContent = context.session_id.replace("group:", "QQ群 "); head.querySelector("small").textContent = `${context.participants.join("、") || "成员未知"} · ${formatDate(context.updated_at)}`;
      const topic = document.createElement("p"); topic.className = "context-topic"; topic.textContent = context.topic_preview || "暂无可用话题摘要";
      const messages = document.createElement("div"); messages.className = "context-messages";
      context.messages.slice(-6).forEach((message) => { const line = document.createElement("p"); const speaker = document.createElement("strong"); speaker.textContent = message.speaker || (message.role === "assistant" ? characterName() : "成员"); line.append(speaker, document.createTextNode(` ${message.content}`)); messages.append(line); });
      card.append(head, topic, messages); return card;
    }));
    if (!result.items.length) host.innerHTML = '<div class="table-empty">还没有可展示的群聊上下文</div>';
    iconRefresh();
  } catch (error) { toast(error.message, "error"); }
}

function showActivityTab(tab) {
  state.activityTab = tab;
  $$('[data-activity-tab]').forEach((button) => button.classList.toggle("active", button.dataset.activityTab === tab));
  $("#activity-list").hidden = tab !== "timeline"; $("#activity-toolbar").hidden = tab !== "timeline"; $("#context-board").hidden = tab !== "contexts";
  if (tab === "timeline") loadActivities(); else loadContexts();
}

function loadActivityView() { showActivityTab(state.activityTab); }

const agentCapabilityLabels = {
  chat: "日常对话",
  research: "联网检索",
  memory: "记忆写入",
  qq_relay: "QQ 代发",
  game_control: "游戏观察",
  autonomy: "主动联系",
};

const agentPolicyModes = {
  auto: "自动允许",
  owner_only: "仅主人允许",
  manual_only: "仅手动允许",
  deny: "禁止",
};

function renderEmpty(host, text) {
  const empty = document.createElement("div");
  empty.className = "table-empty compact-empty";
  empty.textContent = text;
  host.replaceChildren(empty);
}

function createAgentAction(label, icon, dataset) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.innerHTML = `<i data-lucide="${icon}"></i><span>${label}</span>`;
  Object.assign(button.dataset, dataset);
  return button;
}

function renderAgentDashboard(payload = {}) {
  state.agentDashboard = payload;
  const summary = payload.summary || {};
  const summaryItems = [
    ["进行中目标", summary.active_goals || 0],
    ["正在执行", summary.running_tasks || 0],
    ["需要处理", summary.failed_tasks || 0],
    ["待跟进", summary.pending_threads || 0],
  ];
  $("#agent-summary-grid").replaceChildren(...summaryItems.map(([label, value]) => {
    const item = document.createElement("div");
    item.className = "agent-summary-card";
    const copy = document.createElement("span"); copy.textContent = label;
    const count = document.createElement("strong"); count.textContent = String(value);
    item.append(copy, count);
    return item;
  }));

  const goalHost = $("#agent-goal-list");
  const goals = Array.isArray(payload.goals) ? payload.goals : [];
  if (!goals.length) renderEmpty(goalHost, "还没有长期目标");
  else goalHost.replaceChildren(...goals.map((goal) => {
    const row = document.createElement("div"); row.className = "agent-item";
    const copy = document.createElement("div");
    const title = document.createElement("strong"); title.textContent = goal.title;
    const meta = document.createElement("span");
    meta.textContent = `${goal.status === "active" ? "进行中" : goal.status === "completed" ? "已完成" : "已取消"} · ${formatDate(goal.updated_at)}`;
    copy.append(title, meta);
    const actions = document.createElement("div"); actions.className = "agent-item-actions";
    if (goal.status === "active") actions.append(
      createAgentAction("完成", "check", { goalId: String(goal.id), goalStatus: "completed" }),
      createAgentAction("取消", "x", { goalId: String(goal.id), goalStatus: "cancelled" }),
    );
    else actions.append(createAgentAction("恢复", "rotate-ccw", { goalId: String(goal.id), goalStatus: "active" }));
    row.append(copy, actions);
    return row;
  }));

  const threadHost = $("#agent-thread-list");
  const threads = Array.isArray(payload.pending_threads) ? payload.pending_threads : [];
  if (!threads.length) renderEmpty(threadHost, "没有遗漏的待跟进话题");
  else threadHost.replaceChildren(...threads.map((thread) => {
    const row = document.createElement("div"); row.className = "agent-item";
    const copy = document.createElement("div");
    const title = document.createElement("strong"); title.textContent = thread.content;
    const meta = document.createElement("span"); meta.textContent = `${thread.session_id || "对话"} · ${formatDate(thread.updated_at)}`;
    copy.append(title, meta);
    const actions = document.createElement("div"); actions.className = "agent-item-actions";
    actions.append(
      createAgentAction("完成", "check", { threadId: String(thread.id), threadStatus: "completed" }),
      createAgentAction("忽略", "x", { threadId: String(thread.id), threadStatus: "cancelled" }),
    );
    row.append(copy, actions);
    return row;
  }));

  renderAgentPolicy(payload.policy || {});
  const runHost = $("#agent-run-list");
  const runs = Array.isArray(payload.runs) ? payload.runs : [];
  if (!runs.length) renderEmpty(runHost, "复杂任务的执行步骤会显示在这里");
  else runHost.replaceChildren(...runs.map((run) => {
    const details = document.createElement("details"); details.className = "agent-run";
    const summaryNode = document.createElement("summary");
    const copy = document.createElement("div"); copy.className = "agent-run-title";
    const title = document.createElement("strong"); title.textContent = run.request_text || "未命名任务";
    const meta = document.createElement("span"); meta.textContent = `${formatDate(run.created_at)} · ${run.model_name || "未记录模型"}`;
    copy.append(title, meta);
    const badge = document.createElement("span"); badge.className = `agent-status ${run.status || ""}`;
    badge.textContent = ({ completed: "已完成", partial: "部分完成", failed: "失败", running: "执行中" })[run.status] || run.status;
    summaryNode.append(copy, badge);
    const stepList = document.createElement("div"); stepList.className = "agent-step-list";
    const steps = Array.isArray(run.steps) ? run.steps : [];
    if (!steps.length) {
      const step = document.createElement("div"); step.className = "agent-step"; step.textContent = run.error || run.reply_excerpt || "没有单独步骤记录"; stepList.append(step);
    } else steps.forEach((item) => {
      const step = document.createElement("div"); step.className = "agent-step";
      const number = document.createElement("b"); number.textContent = String(item.step_index);
      const text = document.createElement("span"); text.textContent = `${item.instruction} · ${item.status}${item.result ? ` · ${item.result}` : ""}`;
      step.append(number, text); stepList.append(step);
    });
    details.append(summaryNode, stepList);
    return details;
  }));
  iconRefresh();
}

function renderAgentPolicy(policy = {}) {
  const rules = policy.capability_rules || {};
  const host = $("#agent-policy-grid");
  host.replaceChildren(...Object.entries(agentCapabilityLabels).map(([key, label]) => {
    const item = document.createElement("div"); item.className = "agent-policy-item";
    const name = document.createElement("label"); name.htmlFor = `policy-${key}`; name.textContent = label;
    const select = document.createElement("select"); select.id = `policy-${key}`; select.dataset.policyCapability = key;
    Object.entries(agentPolicyModes).forEach(([value, text]) => {
      const option = document.createElement("option"); option.value = value; option.textContent = text; select.append(option);
    });
    select.value = rules[key] || "deny";
    item.append(name, select); return item;
  }));
  $("#policy-quiet-start").value = String(policy.quiet_start_hour ?? 23);
  $("#policy-quiet-end").value = String(policy.quiet_end_hour ?? 8);
  $("#policy-daily-limit").value = String(policy.daily_action_limit ?? 12);
  $("#policy-daily-budget").value = String(policy.daily_budget_yuan ?? 2);
}

function renderContextUsage(context = {}) {
  const percent = Number(context.percent || 0);
  $("#agent-context-percent").textContent = `${percent}%`;
  $("#agent-context-meter").style.width = `${Math.max(0, Math.min(100, percent))}%`;
  $("#agent-context-detail").textContent = `${context.messages || 0}/${context.max_messages || 0} 条消息 · 约 ${context.used_chars || 0} 字符`;
  $("#agent-context-summary").textContent = context.has_summary
    ? `已压缩 ${context.compacted_messages || 0} 条较早消息，最近更新 ${formatDate(context.summary_updated_at)}`
    : "尚未需要压缩；接近上限后会自动保存较早对话摘要。";
}

async function loadAgentWorkspace() {
  try {
    const [dashboard, context] = await Promise.all([api("/api/agent/dashboard"), api("/api/context/usage")]);
    renderAgentDashboard(dashboard); renderContextUsage(context);
  } catch (error) { toast(error.message, "error"); }
}

async function createAgentGoal(event) {
  event.preventDefault();
  const input = $("#agent-goal-title");
  const title = input.value.trim();
  if (!title) return toast("先写下一个目标", "error");
  try {
    await api("/api/agent/goals", { method: "POST", body: JSON.stringify({ title }) });
    input.value = ""; await loadAgentWorkspace(); toast("长期目标已添加");
  } catch (error) { toast(error.message, "error"); }
}

async function updateAgentItem(button) {
  try {
    if (button.dataset.goalId) await api(`/api/agent/goals/${button.dataset.goalId}`, { method: "PUT", body: JSON.stringify({ status: button.dataset.goalStatus }) });
    if (button.dataset.threadId) await api(`/api/agent/threads/${button.dataset.threadId}`, { method: "PUT", body: JSON.stringify({ status: button.dataset.threadStatus }) });
    await loadAgentWorkspace();
  } catch (error) { toast(error.message, "error"); }
}

async function saveAgentPolicy() {
  const button = $("#save-agent-policy"); button.disabled = true;
  const capabilityRules = Object.fromEntries($$("[data-policy-capability]").map((select) => [select.dataset.policyCapability, select.value]));
  try {
    const policy = await api("/api/agent/policy", { method: "PUT", body: JSON.stringify({
      capability_rules: capabilityRules,
      quiet_start_hour: Number($("#policy-quiet-start").value),
      quiet_end_hour: Number($("#policy-quiet-end").value),
      daily_action_limit: Number($("#policy-daily-limit").value),
      daily_budget_yuan: Number($("#policy-daily-budget").value),
    }) });
    renderAgentPolicy(policy); toast("自主行为权限已保存");
  } catch (error) { toast(error.message, "error"); } finally { button.disabled = false; }
}

function localDateKey(value = new Date()) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseLocalDateKey(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ""));
  if (!match) return null;
  const result = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return localDateKey(result) === value ? result : null;
}

function reflectionMonthKey(value = new Date()) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}`;
}

function reflectionMonthDate(monthKey) {
  const match = /^(\d{4})-(\d{2})$/.exec(String(monthKey || ""));
  if (!match) return new Date(new Date().getFullYear(), new Date().getMonth(), 1);
  return new Date(Number(match[1]), Number(match[2]) - 1, 1);
}

function shiftedReflectionMonth(monthKey, offset) {
  const value = reflectionMonthDate(monthKey);
  value.setMonth(value.getMonth() + offset);
  return reflectionMonthKey(value);
}

function reflectionMonthRange(monthKey) {
  const startDate = reflectionMonthDate(monthKey);
  const endDate = new Date(startDate.getFullYear(), startDate.getMonth() + 1, 1);
  return { start: localDateKey(startDate), end: localDateKey(endDate) };
}

function reflectionMonthPath(monthKey) {
  const range = reflectionMonthRange(monthKey);
  return `/api/growth/reflections?start=${encodeURIComponent(range.start)}&end=${encodeURIComponent(range.end)}&limit=62`;
}

function createReflectionEntry(item) {
  const article = document.createElement("article"); article.className = "reflection-entry";
  const header = document.createElement("header");
  const title = document.createElement("strong"); title.textContent = item.title;
  const type = document.createElement("span"); type.textContent = "每日想法";
  header.append(title, type);
  const content = document.createElement("p"); content.textContent = item.content;
  const footer = document.createElement("footer"); footer.textContent = `${item.mood || "平静"} · ${formatDate(item.updated_at)}`;
  article.append(header, content, footer);
  return article;
}

function reflectionsForDate(dateKey) {
  return state.reflectionItems.filter((item) => item.period_key === dateKey);
}

function renderReflectionDay() {
  const selected = parseLocalDateKey(state.reflectionSelectedDate) || new Date();
  const dateKey = localDateKey(selected);
  const items = reflectionsForDate(dateKey);
  const weekday = selected.toLocaleDateString("zh-CN", { weekday: "long" });
  $("#reflection-selected-weekday").textContent = dateKey === localDateKey() ? `今天 · ${weekday}` : weekday;
  $("#reflection-selected-date").textContent = selected.toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric" });
  $("#reflection-day-count").textContent = `${items.length} 条记录`;
  const host = $("#reflection-list");
  if (!items.length) {
    renderEmpty(host, dateKey === localDateKey() ? "今天还没有留下想法" : "这一天没有成长记录");
    return;
  }
  host.replaceChildren(...items.map(createReflectionEntry));
}

function renderReflectionCalendar() {
  const monthKey = state.reflectionMonth || reflectionMonthKey();
  const monthDate = reflectionMonthDate(monthKey);
  const todayKey = localDateKey();
  const currentMonth = reflectionMonthKey();
  const picker = $("#reflection-month-picker");
  picker.value = monthKey;
  picker.max = currentMonth;
  picker.disabled = false;
  $("#reflection-previous-month").disabled = false;
  $("#reflection-next-month").disabled = monthKey >= currentMonth;
  $("#reflection-today").disabled = monthKey === currentMonth && state.reflectionSelectedDate === todayKey;

  const recordsByDate = new Map();
  state.reflectionItems.forEach((item) => {
    const records = recordsByDate.get(item.period_key) || [];
    records.push(item);
    recordsByDate.set(item.period_key, records);
  });
  const firstOffset = (monthDate.getDay() + 6) % 7;
  const gridStart = new Date(monthDate.getFullYear(), monthDate.getMonth(), 1 - firstOffset);
  const cells = [];
  for (let index = 0; index < 42; index += 1) {
    const date = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + index);
    const dateKey = localDateKey(date);
    const items = recordsByDate.get(dateKey) || [];
    const hasReflection = items.length > 0;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "reflection-calendar-day";
    button.dataset.reflectionDate = dateKey;
    button.setAttribute("role", "gridcell");
    button.setAttribute("aria-pressed", String(dateKey === state.reflectionSelectedDate));
    button.classList.toggle("outside", date.getMonth() !== monthDate.getMonth());
    button.classList.toggle("today", dateKey === todayKey);
    button.classList.toggle("selected", dateKey === state.reflectionSelectedDate);
    button.classList.toggle("has-record", hasReflection);
    button.disabled = dateKey > todayKey;
    button.setAttribute("aria-label", `${date.toLocaleDateString("zh-CN", { month: "long", day: "numeric", weekday: "long" })}，${hasReflection ? "有每日想法" : "没有记录"}`);
    const number = document.createElement("span"); number.textContent = String(date.getDate());
    const markers = document.createElement("span"); markers.className = "reflection-day-markers";
    if (hasReflection) { const marker = document.createElement("i"); markers.append(marker); }
    button.append(number, markers);
    cells.push(button);
  }
  const calendar = $("#reflection-calendar");
  calendar.replaceChildren(...cells);
  calendar.setAttribute("aria-busy", "false");
  renderReflectionDay();
}

function applyReflectionMonth(payload, monthKey, preferredDate = "") {
  state.reflectionMonth = monthKey;
  state.reflectionItems = Array.isArray(payload?.items)
    ? payload.items.filter((item) => item.period_type === "daily")
    : [];
  const reflectionDays = new Set(state.reflectionItems.map((item) => item.period_key)).size;
  $("#growth-reflection-count").textContent = state.reflectionItems.length.toLocaleString("zh-CN");
  $("#growth-reflection-label").textContent = monthKey === reflectionMonthKey()
    ? "本月想法"
    : `${Number(monthKey.slice(5, 7))}月想法`;
  $("#growth-reflection-summary").textContent = state.reflectionItems.length
    ? `${reflectionDays} 天 · ${state.reflectionItems.length} 条想法`
    : "这个月还没有想法";
  const prefix = `${monthKey}-`;
  const candidates = [...new Set(state.reflectionItems.map((item) => item.period_key).filter((key) => key.startsWith(prefix)))].sort().reverse();
  const preferred = preferredDate.startsWith(prefix)
    ? preferredDate
    : (state.reflectionSelectedDate.startsWith(prefix) ? state.reflectionSelectedDate : "");
  state.reflectionSelectedDate = preferred
    || (monthKey === reflectionMonthKey() ? localDateKey() : "")
    || candidates[0]
    || `${monthKey}-01`;
  renderReflectionCalendar();
}

function setReflectionCalendarBusy(busy) {
  $("#reflection-calendar").setAttribute("aria-busy", String(busy));
  $("#reflection-previous-month").disabled = busy;
  $("#reflection-next-month").disabled = busy || state.reflectionMonth >= reflectionMonthKey();
  $("#reflection-month-picker").disabled = busy;
  $("#reflection-today").disabled = busy || (
    state.reflectionMonth === reflectionMonthKey()
    && state.reflectionSelectedDate === localDateKey()
  );
}

async function loadReflectionMonth(monthKey, preferredDate = "") {
  const normalizedMonth = reflectionMonthKey(reflectionMonthDate(monthKey));
  const requestId = ++state.reflectionRequestId;
  setReflectionCalendarBusy(true);
  try {
    const payload = await api(reflectionMonthPath(normalizedMonth));
    if (requestId !== state.reflectionRequestId) return;
    applyReflectionMonth(payload, normalizedMonth, preferredDate);
  } catch (error) {
    if (requestId === state.reflectionRequestId) toast(error.message, "error");
  } finally {
    if (requestId === state.reflectionRequestId) setReflectionCalendarBusy(false);
  }
}

async function loadGrowthWorkspace() {
  const monthKey = state.reflectionMonth || reflectionMonthKey();
  setReflectionCalendarBusy(true);
  try {
    const [interests, reflections] = await Promise.all([api("/api/interests"), api(reflectionMonthPath(monthKey))]);
    renderInterests(interests);
    applyReflectionMonth(reflections, monthKey, state.reflectionSelectedDate);
  } catch (error) { toast(error.message, "error"); } finally { setReflectionCalendarBusy(false); }
}

function selectReflectionDate(dateKey) {
  if (!parseLocalDateKey(dateKey) || dateKey > localDateKey()) return;
  const monthKey = dateKey.slice(0, 7);
  if (monthKey !== state.reflectionMonth) {
    loadReflectionMonth(monthKey, dateKey);
    return;
  }
  state.reflectionSelectedDate = dateKey;
  renderReflectionCalendar();
}

function navigateReflectionMonth(offset) {
  const nextMonth = shiftedReflectionMonth(state.reflectionMonth || reflectionMonthKey(), offset);
  if (nextMonth > reflectionMonthKey()) return;
  loadReflectionMonth(nextMonth);
}

function showCurrentReflectionDate() {
  const todayKey = localDateKey();
  loadReflectionMonth(todayKey.slice(0, 7), todayKey);
}

async function generateReflection() {
  const button = $("#generate-daily-reflection");
  button.disabled = true;
  try {
    const result = await api("/api/growth/reflections/generate", { method: "POST", body: JSON.stringify({ period_type: "daily" }), timeoutMs: 90000 });
    const dateKey = parseLocalDateKey(result.period_key) ? result.period_key : localDateKey();
    await loadReflectionMonth(dateKey.slice(0, 7), dateKey);
    toast("今天的想法已更新");
  } catch (error) { toast(error.message, "error"); } finally { button.disabled = false; }
}

function renderModelUsage(payload = {}) {
  const summary = $("#model-usage-summary");
  const items = [
    ["请求", Number(payload.requests || 0).toLocaleString("zh-CN")],
    ["成功率", `${Number(payload.success_rate || 0).toFixed(1)}%`],
    ["平均延迟", `${Math.round(Number(payload.average_latency_ms || 0))} ms`],
    ["估算 Token", (Number(payload.input_tokens || 0) + Number(payload.output_tokens || 0)).toLocaleString("zh-CN")],
  ];
  summary.replaceChildren(...items.map(([label, value]) => {
    const item = document.createElement("div");
    const name = document.createElement("span"); name.textContent = label;
    const data = document.createElement("strong"); data.textContent = value;
    item.append(name, data); return item;
  }));
  const host = $("#model-usage-list");
  const models = Array.isArray(payload.models) ? payload.models : [];
  if (!models.length) renderEmpty(host, "新的模型调用会开始记录在这里");
  else host.replaceChildren(...models.map((model) => {
    const row = document.createElement("div"); row.className = "model-usage-row";
    const copy = document.createElement("div");
    const title = document.createElement("strong"); title.textContent = model.model_name || "未知模型";
    const meta = document.createElement("span"); meta.textContent = model.provider || "未记录服务地址";
    copy.append(title, meta);
    const stats = document.createElement("span");
    const requests = Number(model.requests || 0); const rate = requests ? Math.round(Number(model.successes || 0) / requests * 100) : 0;
    stats.textContent = `${requests} 次 · ${rate}% · ${Math.round(Number(model.average_latency_ms || 0))} ms`;
    row.append(copy, stats); return row;
  }));
}

function renderModelProfiles(payload = {}) {
  state.modelProfiles = Array.isArray(payload.items) ? payload.items : [];
  const host = $("#fallback-model-list");
  if (!state.modelProfiles.length) return renderEmpty(host, "主模型不可用时，目前没有备用连接可以接管");
  host.replaceChildren(...state.modelProfiles.map((profile) => {
    const row = document.createElement("div"); row.className = "fallback-model-row";
    const copy = document.createElement("div");
    const title = document.createElement("strong"); title.textContent = `${profile.name} · ${profile.capability === "vision" ? "视觉" : "语言"}`;
    const meta = document.createElement("span"); meta.textContent = `${profile.model_name} · 优先级 ${profile.priority} · ${profile.api_type}`;
    copy.append(title, meta);
    const actions = document.createElement("div"); actions.className = "fallback-model-actions";
    const toggle = document.createElement("label"); toggle.className = "switch"; toggle.title = profile.enabled ? "停用备用模型" : "启用备用模型";
    const checkbox = document.createElement("input"); checkbox.type = "checkbox"; checkbox.checked = Boolean(profile.enabled); checkbox.dataset.profileToggle = profile.id;
    const slider = document.createElement("span"); toggle.append(checkbox, slider);
    const remove = document.createElement("button"); remove.type = "button"; remove.className = "icon-button"; remove.title = "删除备用模型"; remove.setAttribute("aria-label", "删除备用模型"); remove.dataset.profileDelete = profile.id; remove.innerHTML = '<i data-lucide="trash-2"></i>';
    actions.append(toggle, remove); row.append(copy, actions); return row;
  }));
  iconRefresh();
}

async function loadModelWorkspace() {
  try {
    const [providers, profiles, usage] = await Promise.all([api("/api/model/providers"), api("/api/model/profiles"), api("/api/model/usage?days=30")]);
    renderModelProviders(providers); renderModelProfiles(profiles); renderModelUsage(usage);
  } catch (error) { toast(error.message, "error"); }
}

function modelCapabilityLabel(capabilities = []) {
  const values = Array.isArray(capabilities) ? capabilities : [capabilities];
  if (values.includes("language") && values.includes("vision")) return "语言 + 视觉";
  return values.includes("vision") ? "视觉模型" : "语言模型";
}

function modelPriceSummary(model) {
  const input = Number(model.input_price || 0);
  const output = Number(model.output_price || 0);
  const cache = Number(model.cache_price || 0);
  if (!input && !output && !cache) return "价格待配置";
  return `缓存 ${cache.toFixed(2)} · 输入 ${input.toFixed(2)} · 输出 ${output.toFixed(2)} ${model.currency || "CNY"}/1M Token`;
}

function renderModelProviders(payload = {}) {
  state.modelProviders = Array.isArray(payload.items) ? payload.items : [];
  const host = $("#model-provider-list");
  if (!state.modelProviders.length) return renderEmpty(host, "还没有供应商，点击右上角添加第一个接口");
  host.replaceChildren(...state.modelProviders.map((provider) => {
    const card = document.createElement("article"); card.className = "model-provider-card";
    const head = document.createElement("header"); head.className = "model-provider-card-head";
    const mark = document.createElement("span"); mark.className = "model-provider-mark"; mark.textContent = String(provider.name || "?").trim().slice(0, 1).toUpperCase();
    const copy = document.createElement("div"); copy.className = "model-provider-card-copy";
    const title = document.createElement("strong"); title.textContent = provider.name || "未命名供应商";
    const count = document.createElement("span"); count.textContent = `${provider.models?.length || 0} 个模型`;
    copy.append(title, count);
    const meta = document.createElement("small"); meta.textContent = `${provider.api_label || provider.api_type || "自动识别"} · ${provider.base_url || "未配置地址"}`;
    const removeProvider = document.createElement("button"); removeProvider.className = "icon-button model-provider-delete"; removeProvider.type = "button"; removeProvider.title = "删除供应商"; removeProvider.setAttribute("aria-label", "删除供应商"); removeProvider.dataset.providerDelete = provider.id; removeProvider.innerHTML = '<i data-lucide="trash-2"></i>';
    head.append(mark, copy, removeProvider);
    const details = document.createElement("div"); details.className = "model-provider-card-meta"; details.append(meta);
    const list = document.createElement("div"); list.className = "model-provider-model-list";
    const models = Array.isArray(provider.models) ? provider.models : [];
    if (!models.length) {
      const empty = document.createElement("span"); empty.className = "table-empty compact-empty"; empty.textContent = "这个供应商还没有模型"; list.append(empty);
    } else models.forEach((model) => {
      const row = document.createElement("div"); row.className = "model-provider-model";
      const modelCopy = document.createElement("div"); modelCopy.className = "model-provider-model-copy";
      const modelTitle = document.createElement("strong"); modelTitle.textContent = model.name || model.model_name;
      const modelMeta = document.createElement("span"); modelMeta.textContent = `${model.model_name} · ${modelCapabilityLabel(model.capabilities)} · ${modelPriceSummary(model)}`;
      modelCopy.append(modelTitle, modelMeta);
      const actions = document.createElement("div"); actions.className = "model-provider-model-actions";
      const test = document.createElement("button"); test.type = "button"; test.className = "icon-button model-provider-test"; test.title = "检测模型接口"; test.setAttribute("aria-label", "检测模型接口"); test.dataset.modelTest = model.id; test.innerHTML = '<i data-lucide="scan-search"></i>';
      actions.append(test);
      (model.capabilities || []).forEach((capability) => {
        const activate = document.createElement("button"); activate.type = "button"; activate.className = `text-command model-activate-button${(model.active_for || []).includes(capability) ? " active" : ""}`; activate.textContent = (model.active_for || []).includes(capability) ? `${capability === "language" ? "语言" : "视觉"} · 使用中` : `用于${capability === "language" ? "语言" : "视觉"}`; activate.dataset.modelActivate = model.id; activate.dataset.modelCapability = capability; actions.append(activate);
      });
      const remove = document.createElement("button"); remove.type = "button"; remove.className = "icon-button"; remove.title = "删除模型"; remove.setAttribute("aria-label", "删除模型"); remove.dataset.modelDelete = model.id; remove.innerHTML = '<i data-lucide="trash-2"></i>';
      actions.append(remove); row.append(modelCopy, actions); list.append(row);
    });
    const footer = document.createElement("footer");
    const keyState = document.createElement("span"); keyState.textContent = provider.api_key_configured ? "密钥已安全保存" : "无密钥 / 本地接口";
    const addModel = document.createElement("button"); addModel.type = "button"; addModel.className = "secondary-button"; addModel.dataset.providerAddModel = provider.id; addModel.innerHTML = '<i data-lucide="plus"></i><span>添加模型</span>';
    footer.append(keyState, addModel); card.append(head, details, list, footer); return card;
  }));
  iconRefresh();
}

function openModelProviderDialog(provider = null) {
  const dialog = $("#model-provider-dialog");
  const isModel = Boolean(provider);
  dialog.dataset.providerId = provider?.id || "";
  $("#model-provider-dialog-title").textContent = isModel ? "添加模型" : "新增供应商";
  $("#model-provider-dialog-copy").textContent = isModel ? `继续添加到 ${provider.name}，留空密钥则使用该供应商已保存的密钥` : "填写一次接口信息，之后可以在同一供应商下管理多个模型";
  $("#model-provider-name").value = provider?.name || "";
  $("#model-provider-base-url").value = provider?.base_url || "";
  $("#model-provider-api-key").value = "";
  $("#model-provider-api-key").placeholder = provider ? (provider.api_key_configured ? "已配置，留空则继续使用" : "无鉴权接口可以留空") : "sk-...";
  $("#model-provider-model-name").value = "";
  $("#model-provider-model-display-name").value = "";
  $("#model-provider-capabilities").value = "language";
  $("#model-provider-input-price").value = "0";
  $("#model-provider-output-price").value = "0";
  state.discoveredProviderModels = [];
  $("#model-provider-model-options").replaceChildren();
  $("#model-provider-compatibility-label").textContent = provider ? (provider.api_label || "自动识别供应商接口") : "OpenAI 兼容 / New API 中转站";
  $("#model-provider-cache-price").value = "0";
  $("#model-provider-name").disabled = isModel;
  $("#model-provider-base-url").disabled = isModel;
  dialog.showModal();
}

function updateModelProviderCompatibilityHint() {
  const value = $("#model-provider-base-url").value.toLowerCase();
  let label = "OpenAI 兼容 / New API 中转站";
  if (value.includes("anthropic")) label = "Anthropic Messages 接口";
  else if (value.includes("googleapis.com") || value.includes("generativelanguage")) label = "Google Gemini 接口";
  else if (value.includes("11434") || value.includes("ollama")) label = "Ollama 本地接口";
  $("#model-provider-compatibility-label").textContent = label;
}

async function fetchModelProviderModels() {
  const button = $("#fetch-model-provider-models");
  const providerId = $("#model-provider-dialog").dataset.providerId || "";
  const baseUrl = $("#model-provider-base-url").value.trim();
  const apiKey = $("#model-provider-api-key").value.trim();
  if (!providerId && !baseUrl) return toast("请先填写 API 地址", "error");
  button.disabled = true;
  button.classList.add("loading");
  try {
    const result = await api("/api/model/providers/discover", { method: "POST", body: JSON.stringify({ provider_id: providerId, base_url: baseUrl, api_key: apiKey }), timeoutMs: 30000 });
    state.discoveredProviderModels = Array.isArray(result.models) ? result.models : [];
    if (result.base_url) {
      $("#model-provider-base-url").value = result.base_url;
      updateModelProviderCompatibilityHint();
    }
    const options = state.discoveredProviderModels.map((model) => {
      const option = document.createElement("option"); option.value = model.id; option.label = model.name && model.name !== model.id ? model.name : model.id; return option;
    });
    $("#model-provider-model-options").replaceChildren(...options);
    $("#model-provider-compatibility-label").textContent = `${result.api_label || "已识别接口"} · ${result.count || 0} 个模型`;
    if (state.discoveredProviderModels.length === 1) $("#model-provider-model-name").value = state.discoveredProviderModels[0].id;
    toast(state.discoveredProviderModels.length ? `已获取 ${state.discoveredProviderModels.length} 个模型` : "供应商没有返回模型目录，可手动填写模型 ID");
  } catch (error) { $("#model-provider-compatibility-label").textContent = "模型列表获取失败，可手动填写模型 ID"; toast(error.message, "error"); } finally { button.disabled = false; button.classList.remove("loading"); }
}

async function saveModelProvider(event) {
  event.preventDefault();
  const button = $("#model-provider-save");
  const providerId = $("#model-provider-dialog").dataset.providerId || "";
  const capabilityValue = $("#model-provider-capabilities").value;
  const payload = {
    name: $("#model-provider-name").value.trim(),
    base_url: $("#model-provider-base-url").value.trim(),
    api_key: $("#model-provider-api-key").value.trim(),
    model_name: $("#model-provider-model-name").value.trim(),
    model_display_name: $("#model-provider-model-display-name").value.trim(),
    capabilities: capabilityValue === "both" ? ["language", "vision"] : [capabilityValue],
    input_price: Number($("#model-provider-input-price").value || 0),
    output_price: Number($("#model-provider-output-price").value || 0),
    cache_price: Number($("#model-provider-cache-price").value || 0),
  };
  if (!payload.base_url || !payload.model_name || (!providerId && !payload.name)) return toast("请填写供应商地址、名称和模型名称", "error");
  button.disabled = true;
  try {
    const result = await api(providerId ? `/api/model/providers/${providerId}/models` : "/api/model/providers", { method: "POST", body: JSON.stringify(payload), timeoutMs: 60000 });
    renderModelProviders(result); $("#model-provider-dialog").close(); toast(providerId ? "模型已检测并添加" : "供应商已检测并添加");
  } catch (error) { toast(error.message, "error"); } finally { button.disabled = false; }
}

async function handleModelProviderAction(target) {
  if (target.dataset.providerAddModel) {
    const provider = state.modelProviders.find((item) => item.id === target.dataset.providerAddModel); if (provider) openModelProviderDialog(provider); return;
  }
  if (target.dataset.providerDelete) {
    const provider = state.modelProviders.find((item) => item.id === target.dataset.providerDelete); if (!provider || !window.confirm(`删除供应商“${provider.name}”及其模型？`)) return;
    try { const result = await api(`/api/model/providers/${provider.id}`, { method: "DELETE" }); renderModelProviders(result); toast("供应商已删除"); } catch (error) { toast(error.message, "error"); } return;
  }
  if (target.dataset.modelDelete) {
    if (!window.confirm("删除这个模型？")) return;
    const owner = state.modelProviders.find((provider) => (provider.models || []).some((model) => model.id === target.dataset.modelDelete));
    if (!owner) return;
    try { const result = await api(`/api/model/providers/${owner.id}/models/${target.dataset.modelDelete}`, { method: "DELETE" }); renderModelProviders(result); toast("模型已删除"); } catch (error) { toast(error.message, "error"); } return;
  }
  if (target.dataset.modelTest) {
    target.disabled = true; target.classList.add("loading");
    try {
      const result = await api("/api/model/providers/test", { method: "POST", body: JSON.stringify({ model_id: target.dataset.modelTest }), timeoutMs: 60000 });
      const details = Object.values(result.tests || {}).map((item) => `${item.capability === "vision" ? "视觉" : "语言"} ${item.latency_ms} ms`).join(" · ");
      toast(`${result.model} 检测通过${details ? ` · ${details}` : ""}`);
    } catch (error) { toast(error.message, "error"); } finally { target.disabled = false; target.classList.remove("loading"); }
    return;
  }
  if (target.dataset.modelActivate) {
    target.disabled = true;
    try { const result = await api("/api/model/providers/activate", { method: "POST", body: JSON.stringify({ model_id: target.dataset.modelActivate, capability: target.dataset.modelCapability }), timeoutMs: 60000 }); renderModelProviders(result); renderStatus(result.status); toast(`已切换${target.dataset.modelCapability === "language" ? "语言" : "视觉"}模型`); } catch (error) { toast(error.message, "error"); } finally { target.disabled = false; }
  }
}

async function addFallbackModel(event) {
  event.preventDefault();
  const button = $("#add-fallback-model");
  const usePrimaryKey = $("#fallback-use-primary-key").checked;
  const capability = $("#fallback-model-capability").value;
  const payload = {
    name: $("#fallback-model-name").value.trim(), capability,
    base_url: $("#fallback-model-base-url").value.trim(),
    model_name: $("#fallback-model-id").value.trim(),
    priority: Number($("#fallback-model-priority").value || 100),
    use_primary_key: usePrimaryKey, enabled: true,
    api_key: usePrimaryKey ? "" : $("#fallback-model-api-key").value.trim(),
  };
  if (!payload.base_url || !payload.model_name) return toast("请填写备用模型的 API 地址和模型名称", "error");
  if (!usePrimaryKey && !payload.api_key) return toast("独立密钥模式下需要填写 API 密钥", "error");
  button.disabled = true;
  try {
    const detected = await api("/api/model/connection/test", { method: "POST", body: JSON.stringify({ target: capability, connection: { base_url: payload.base_url, api_key: payload.api_key, model: payload.model_name } }), timeoutMs: 30000 });
    payload.base_url = detected.base_url; payload.api_type = detected.api_type;
    await api("/api/model/profiles", { method: "POST", body: JSON.stringify(payload) });
    $("#fallback-model-form").reset(); $("#fallback-use-primary-key").checked = true; $("#fallback-model-priority").value = "100"; syncFallbackKeyMode();
    await loadModelWorkspace(); toast(`备用模型已添加，接口识别为 ${detected.api_label}`);
  } catch (error) { toast(error.message, "error"); } finally { button.disabled = false; }
}

function syncFallbackKeyMode() {
  const usePrimary = $("#fallback-use-primary-key").checked;
  $("#fallback-model-api-key").disabled = usePrimary;
  $(".fallback-key-field").classList.toggle("disabled", usePrimary);
}

async function handleFallbackModelAction(target) {
  const profileId = target.dataset.profileToggle || target.dataset.profileDelete;
  const profile = state.modelProfiles.find((item) => item.id === profileId);
  if (!profile) return;
  try {
    if (target.dataset.profileDelete) {
      if (!window.confirm(`删除备用模型“${profile.name}”？`)) return;
      await api(`/api/model/profiles/${profile.id}`, { method: "DELETE" });
    } else {
      await api("/api/model/profiles", { method: "POST", body: JSON.stringify({ ...profile, enabled: target.checked }) });
    }
    await loadModelWorkspace();
  } catch (error) { toast(error.message, "error"); await loadModelWorkspace(); }
}

function renderDependencies(payload = {}) {
  state.dependencies = payload;
  $("#dependency-summary").textContent = payload.ready ? "全部就绪" : "存在缺失组件";
  $("#dependency-python").textContent = payload.python || "未知";
  const host = $("#dependency-list");
  const items = Array.isArray(payload.items) ? payload.items : [];
  if (!items.length) return renderEmpty(host, "没有读取到依赖信息");
  host.replaceChildren(...items.map((item) => {
    const row = document.createElement("div"); row.className = "dependency-row";
    const copy = document.createElement("div");
    const title = document.createElement("strong"); title.textContent = item.label;
    const detail = document.createElement("span"); detail.textContent = item.detail;
    copy.append(title, detail);
    if (item.repairable) {
      const repair = createAgentAction("修复", "wrench", { dependencyRepair: item.key }); row.append(copy, repair);
    } else {
      const status = document.createElement("span"); status.className = `dependency-state ${item.state}`;
      status.textContent = ({ ok: "正常", optional: "可选", installing: "安装中", completed: "已完成", missing: "缺失", failed: "失败" })[item.state] || item.state;
      row.append(copy, status);
    }
    return row;
  }));
  iconRefresh();
}

function environmentStateLabel(stateName, action = "install") {
  return ({
    ok: "已就绪",
    optional: action === "configure" ? "待配置" : "可稍后配置",
    installing: "安装中",
    queued: "等待安装",
    paused: "已暂停",
    cancelling: "正在取消",
    cancelled: "已取消",
    missing: "未安装",
    failed: action === "configure" ? "连接异常" : "安装失败",
  })[stateName] || "待检查";
}

function formatEnvironmentBytes(value) {
  const bytes = Math.max(0, Number(value) || 0);
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  const amount = bytes / (1024 ** index);
  return `${amount >= 100 || index === 0 ? amount.toFixed(0) : amount.toFixed(1)} ${units[index]}`;
}

function formatEnvironmentElapsed(value) {
  const seconds = Math.max(0, Math.floor(Number(value) || 0));
  if (!seconds) return "";
  if (seconds < 60) return `${seconds} 秒`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return remainder ? `${minutes} 分 ${remainder} 秒` : `${minutes} 分钟`;
}

function environmentJobActive(job = {}) {
  return ["queued", "installing", "paused", "cancelling"].includes(job.state);
}

function resolveEnvironmentFeature(feature, environmentMap, jobsMap) {
  const item = environmentMap.get(feature.key) || {};
  const serverJob = jobsMap.get(feature.key) || item.job || {};
  const queuedLocally = state.environmentInstallQueuedKeys.has(feature.key) && !environmentJobActive(serverJob);
  const job = queuedLocally
    ? { key: feature.key, state: "queued", phase: "preparing", detail: "已加入安装队列，正在等待空闲任务位" }
    : serverJob;
  const active = environmentJobActive(job);
  const stateName = active ? job.state : (item.state || "missing");
  const installKeys = item.repairable && !active && item.action === "install" && stateName !== "ok" ? [feature.key] : [];
  return {
    ...feature,
    action: item.action || "none",
    repairable: Boolean(item.repairable),
    state: stateName,
    statusLabel: active ? environmentStateLabel(stateName, item.action) : (item.status_label || environmentStateLabel(stateName, item.action)),
    detail: active ? (job.detail || item.detail || "正在安装") : (item.detail || "尚未读取到状态"),
    installKeys,
    job,
    missingCount: Math.max(0, Number(item.missing_count) || 0),
    totalCount: Math.max(0, Number(item.total_count) || 0),
  };
}

function createEnvironmentProgress(job = {}) {
  if (!environmentJobActive(job)) return null;
  const hasProgress = job.progress !== null
    && job.progress !== undefined
    && job.progress !== ""
    && Number.isFinite(Number(job.progress));
  const progress = hasProgress ? Math.max(0, Math.min(100, Number(job.progress))) : null;
  const downloaded = Number(job.downloaded_bytes) || 0;
  const total = Number(job.total_bytes) || 0;
  const speed = Number(job.speed_bps) || 0;
  const elapsed = formatEnvironmentElapsed(job.elapsed_seconds);
  const phaseLabel = ({ preparing: job.state === "queued" ? "等待中" : "准备中", downloading: "下载中", installing: "安装中" })[job.phase]
    || (job.state === "paused" ? "已暂停" : "处理中");

  const host = document.createElement("div");
  host.className = `environment-progress ${job.state}`;
  const summary = document.createElement("div");
  summary.className = "environment-progress-summary";
  const label = document.createElement("strong");
  label.textContent = job.state === "paused" ? "已暂停" : (job.state === "cancelling" ? "正在取消" : phaseLabel);
  const metrics = document.createElement("span");
  if (job.phase === "downloading" && total > 0) {
    metrics.textContent = `${formatEnvironmentBytes(downloaded)} / ${formatEnvironmentBytes(total)}${speed ? ` · ${formatEnvironmentBytes(speed)}/s` : ""}${progress !== null ? ` · ${Math.round(progress)}%` : ""}`;
  } else if (job.phase === "downloading" && (downloaded > 0 || speed > 0)) {
    metrics.textContent = `${formatEnvironmentBytes(downloaded)}${speed ? ` · ${formatEnvironmentBytes(speed)}/s` : ""} · 正在计算总大小`;
  } else {
    const detail = job.detail || (job.phase === "downloading" ? "正在连接下载源" : "正在执行安装步骤");
    metrics.textContent = `${detail}${elapsed ? ` · 已进行 ${elapsed}` : ""}`;
  }
  summary.append(label, metrics);

  const track = document.createElement("div");
  track.className = `environment-progress-track${progress === null && job.state !== "paused" ? " indeterminate" : ""}`;
  track.setAttribute("role", "progressbar");
  track.setAttribute("aria-label", `${phaseLabel}进度`);
  if (progress !== null) {
    track.setAttribute("aria-valuenow", String(Math.round(progress)));
    track.setAttribute("aria-valuemin", "0");
    track.setAttribute("aria-valuemax", "100");
  } else {
    track.setAttribute("aria-valuetext", "正在计算下载总大小");
  }
  const fill = document.createElement("span");
  if (progress !== null) fill.style.width = `${progress}%`;
  track.append(fill);

  const controls = document.createElement("div");
  controls.className = "environment-progress-controls";
  const appendControl = (action, icon, title, danger = false) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `icon-button environment-job-control${danger ? " danger" : ""}`;
    button.dataset.environmentJobAction = action;
    button.dataset.environmentJobKey = job.key;
    button.title = title;
    button.setAttribute("aria-label", title);
    button.innerHTML = `<i data-lucide="${icon}"></i>`;
    controls.append(button);
  };
  if (job.can_pause) appendControl("pause", "pause", "暂停下载");
  if (job.can_resume) appendControl("resume", "play", "继续下载");
  if (job.can_cancel) appendControl("cancel", "x", "取消下载", true);

  host.append(summary, track);
  if (controls.childElementCount) host.append(controls);
  return host;
}

function createEnvironmentCard(feature) {
  const card = document.createElement("article");
  card.className = `environment-card ${feature.state}`;
  card.dataset.environmentFeature = feature.key;

  const icon = document.createElement("span");
  icon.className = "environment-card-icon";
  icon.innerHTML = `<i data-lucide="${feature.icon}"></i>`;

  const body = document.createElement("div");
  body.className = "environment-card-body";
  const heading = document.createElement("div");
  heading.className = "environment-card-heading";
  const title = document.createElement("h3"); title.textContent = assistantText(feature.title);
  const badge = document.createElement("span"); badge.className = `environment-badge ${feature.state}`; badge.textContent = feature.statusLabel;
  heading.append(title, badge);
  const description = document.createElement("p"); description.textContent = assistantText(feature.description);
  const detail = document.createElement("span"); detail.className = "environment-card-detail"; detail.textContent = feature.detail;
  const instruction = document.createElement("span"); instruction.className = "environment-card-instruction"; instruction.textContent = assistantText(feature.instruction);
  const size = document.createElement("small"); size.textContent = `体积：${feature.size}`;
  body.append(heading, description, detail, instruction, size);
  const progress = createEnvironmentProgress(feature.job);
  if (progress) body.append(progress);

  const actions = document.createElement("div");
  actions.className = "environment-card-actions";
  if (feature.installKeys.length) {
    const button = document.createElement("button");
    button.className = "primary-button";
    button.type = "button";
    button.dataset.environmentInstall = feature.installKeys.join(",");
    button.disabled = environmentJobActive(feature.job);
    const partialRepair = feature.missingCount > 0 && feature.totalCount > 0 && feature.missingCount < feature.totalCount;
    const installLabel = feature.state === "failed"
      ? "重试修复"
      : (feature.state === "installing" ? "处理中" : (partialRepair ? "补齐缺失项" : "一键安装"));
    button.innerHTML = `<i data-lucide="${feature.state === "installing" ? "loader-circle" : (partialRepair ? "wrench" : "package-plus")}"></i><span>${installLabel}</span>`;
    actions.append(button);
  } else if (feature.panel) {
    const button = document.createElement("button");
    button.className = "secondary-button";
    button.type = "button";
    button.dataset.environmentPanel = feature.panel;
    if (feature.capability) button.dataset.environmentCapability = feature.capability;
    button.innerHTML = `<i data-lucide="settings-2"></i><span>${feature.actionLabel || "去配置"}</span>`;
    actions.append(button);
  } else if (feature.systemPanel) {
    const button = document.createElement("button");
    button.className = "secondary-button";
    button.type = "button";
    button.dataset.environmentSystem = feature.systemPanel;
    button.innerHTML = `<i data-lucide="stethoscope"></i><span>${feature.actionLabel || "查看诊断"}</span>`;
    actions.append(button);
  }
  if (!actions.childElementCount) actions.hidden = true;

  card.append(icon, body, actions);
  return card;
}

function renderEnvironmentInstallMenu(features, maxConcurrent) {
  const host = $("#environment-install-options");
  const installableFeatures = features.filter((feature) => feature.action === "install");
  const availableKeys = new Set(
    installableFeatures
      .filter((feature) => feature.installKeys.length > 0)
      .map((feature) => feature.key),
  );
  for (const key of [...state.environmentInstallSelection]) {
    if (!availableKeys.has(key)) state.environmentInstallSelection.delete(key);
  }
  if (!state.environmentInstallSelectionReady) {
    availableKeys.forEach((key) => state.environmentInstallSelection.add(key));
    state.environmentInstallSelectionReady = true;
  }

  host.replaceChildren(...installableFeatures.map((feature) => {
    const available = availableKeys.has(feature.key);
    const row = document.createElement("label");
    row.className = `environment-install-option${available ? "" : " disabled"}`;
    const input = document.createElement("input");
    input.type = "checkbox";
    input.dataset.environmentSelect = feature.key;
    input.checked = available && state.environmentInstallSelection.has(feature.key);
    input.disabled = !available;
    const icon = document.createElement("span");
    icon.className = "environment-install-option-icon";
    icon.innerHTML = `<i data-lucide="${feature.icon}"></i>`;
    const copy = document.createElement("span");
    copy.className = "environment-install-option-copy";
    const title = document.createElement("strong");
    title.textContent = assistantText(feature.title);
    const detail = document.createElement("small");
    detail.textContent = environmentJobActive(feature.job)
      ? (feature.job.detail || "正在处理")
      : (feature.state === "ok" ? "已经安装" : `${feature.statusLabel} · ${feature.size}`);
    copy.append(title, detail);
    const status = document.createElement("em");
    status.textContent = environmentJobActive(feature.job)
      ? environmentStateLabel(feature.job.state)
      : (available ? "可安装" : (feature.state === "ok" ? "已就绪" : feature.statusLabel));
    row.append(input, icon, copy, status);
    return row;
  }));

  const selected = [...state.environmentInstallSelection].filter((key) => availableKeys.has(key));
  const activeCount = features.filter((feature) => environmentJobActive(feature.job)).length;
  const toggle = $("#environment-install-menu-toggle");
  toggle.disabled = installableFeatures.length === 0;
  toggle.querySelector("span").textContent = selected.length ? `已选 ${selected.length} 项` : "选择安装项";
  toggle.title = `查看全部可安装组件；最多同时处理 ${maxConcurrent} 项`;

  const install = $("#install-missing-environment");
  install.disabled = selected.length === 0;
  install.dataset.environmentInstall = selected.join(",");
  install.classList.toggle("is-installing", activeCount > 0);
  install.classList.toggle("is-complete", activeCount === 0 && availableKeys.size === 0);
  install.innerHTML = selected.length
    ? `<i data-lucide="package-plus"></i><span>${activeCount ? "加入下载队列" : "安装所选"}（${selected.length}）</span>`
    : activeCount
      ? `<i data-lucide="loader-circle"></i><span>正在处理 ${activeCount} 项</span>`
      : '<i data-lucide="check"></i><span>可安装项已就绪</span>';
}

function renderEnvironment(environment = {}) {
  state.environment = environment;
  if (state.status?.qq) renderQqSettings(state.status.qq);
  const environmentMap = new Map((environment.items || []).map((item) => [item.key, item]));
  const jobsMap = new Map(Object.entries(environment.jobs || {}));
  const features = environmentFeatureCatalog.map((feature) => resolveEnvironmentFeature(feature, environmentMap, jobsMap));
  const backendBusy = features.some((feature) => environmentJobActive(feature.job));
  const ready = features.filter((feature) => feature.state === "ok").length;
  const deferred = features.filter((feature) => feature.state === "optional").length;
  const abnormal = features.length - ready - deferred - features.filter((feature) => environmentJobActive(feature.job)).length;
  const maxConcurrent = Math.max(1, Number(environment.max_concurrent_jobs) || 3);
  $("#environment-ready-count").textContent = `${ready} 已就绪${deferred ? ` · ${deferred} 可稍后` : ""}${abnormal > 0 ? ` · ${abnormal} 异常` : ""} / ${features.length} 项`;
  $("#environment-updated").textContent = environment.updated_at ? `检查于 ${formatDate(environment.updated_at)}` : "刚刚检查";
  $("#environment-python").textContent = `Python 环境：${environment.python || `当前${characterName()}运行环境`} · 下载：${environment.download_transport || "后台命令行"} · ${environment.download_source || "魔搭优先 · 多源断点续传"}`;
  renderEnvironmentInstallMenu(features, maxConcurrent);
  $("#environment-list").replaceChildren(...features.map(createEnvironmentCard));
  if (state.environmentPollTimer) clearTimeout(state.environmentPollTimer);
  state.environmentPollTimer = null;
  if (backendBusy && !state.environmentInstallBusy) {
    state.environmentPollTimer = setTimeout(() => {
      state.environmentPollTimer = null;
      loadEnvironment();
    }, 800);
  }
  iconRefresh();
}

async function loadEnvironment() {
  const refresh = $("#refresh-environment");
  refresh.disabled = true;
  refresh.classList.add("loading");
  try {
    const environment = await api("/api/environment", { timeoutMs: 35000 });
    renderEnvironment(environment);
  } catch (error) {
    toast(`环境检查失败：${error.message}`, "error");
  } finally {
    refresh.disabled = false;
    refresh.classList.remove("loading");
  }
}

async function waitForEnvironmentInstall(key) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < 6 * 60 * 60 * 1000) {
    await new Promise((resolve) => setTimeout(resolve, 500));
    const snapshot = await api("/api/environment/jobs", { timeoutMs: 10000 });
    const environment = { ...(state.environment || {}), jobs: snapshot.jobs || {}, updated_at: snapshot.updated_at || state.environment?.updated_at };
    renderEnvironment(environment);
    const current = snapshot.jobs?.[key];
    if (!current || !environmentJobActive(current)) return current;
  }
  throw new Error("安装等待超时，请检查网络后重试");
}

function environmentInstallLimit() {
  return Math.max(1, Number(state.environment?.max_concurrent_jobs) || 3);
}

function environmentExternalActiveCount() {
  const jobs = Object.values(state.environment?.jobs || {});
  return jobs.filter((job) => environmentJobActive(job) && !state.environmentInstallQueuedKeys.has(job.key)).length;
}

async function runEnvironmentInstall(key) {
  const feature = environmentFeatureCatalog.find((candidate) => candidate.key === key);
  const title = assistantText(feature?.title || key);
  try {
    const environment = await api("/api/environment", { timeoutMs: 35000 });
    state.environment = environment;
    const current = (environment.items || []).find((item) => item.key === key);
    if (!current?.repairable || current.action !== "install" || current.state === "ok") return;
    toast(`开始安装：${title}`);
    const started = await api("/api/environment/install", {
      method: "POST",
      body: JSON.stringify({ key }),
      timeoutMs: 15000,
    });
    renderEnvironment({
      ...(state.environment || environment),
      jobs: { ...(state.environment?.jobs || environment.jobs || {}), [key]: started },
      updated_at: new Date().toISOString(),
    });
    const completed = await waitForEnvironmentInstall(key);
    if (completed?.state === "cancelled") {
      toast(`${title}下载已取消`);
      return;
    }
    if (!completed || completed.state !== "completed") {
      throw new Error(completed?.detail || `${title}安装失败`);
    }
    toast(`${title}安装完成`);
  } catch (error) {
    toast(`${title}安装失败：${error.message}`, "error");
  } finally {
    state.environmentInstallWorkers = Math.max(0, state.environmentInstallWorkers - 1);
    state.environmentInstallQueuedKeys.delete(key);
    state.environmentInstallBusy = state.environmentInstallWorkers > 0 || state.environmentInstallQueue.length > 0;
    await loadEnvironment();
    pumpEnvironmentInstallQueue();
  }
}

function pumpEnvironmentInstallQueue() {
  const limit = environmentInstallLimit();
  const externalActive = environmentExternalActiveCount();
  while (
    state.environmentInstallQueue.length
    && state.environmentInstallWorkers + externalActive < limit
  ) {
    const key = state.environmentInstallQueue.shift();
    state.environmentInstallWorkers += 1;
    void runEnvironmentInstall(key);
  }
  state.environmentInstallBusy = state.environmentInstallWorkers > 0 || state.environmentInstallQueue.length > 0;
  if (state.environment) renderEnvironment(state.environment);
}

function installEnvironmentDependencies(keys) {
  const requested = [...new Set((keys || []).map((key) => String(key || "").trim()).filter(Boolean))];
  const serverJobs = state.environment?.jobs || {};
  const queued = requested.filter((key) => {
    if (state.environmentInstallQueuedKeys.has(key)) return false;
    if (environmentJobActive(serverJobs[key] || {})) return false;
    const item = (state.environment?.items || []).find((candidate) => candidate.key === key);
    return Boolean(item?.repairable && item.action === "install" && item.state !== "ok");
  });
  if (!queued.length) return;
  queued.forEach((key) => {
    state.environmentInstallSelection.delete(key);
    state.environmentInstallQueuedKeys.add(key);
    state.environmentInstallQueue.push(key);
  });
  toast(`已加入 ${queued.length} 项安装任务，最多同时处理 ${environmentInstallLimit()} 项`);
  pumpEnvironmentInstallQueue();
}

async function controlEnvironmentJob(key, action, button) {
  if (!key || !["pause", "resume", "cancel"].includes(action)) return;
  if (button) button.disabled = true;
  try {
    const job = await api(`/api/environment/${action}`, {
      method: "POST",
      body: JSON.stringify({ key }),
      timeoutMs: 20000,
    });
    const environment = {
      ...(state.environment || {}),
      jobs: { ...(state.environment?.jobs || {}), [key]: job },
      updated_at: new Date().toISOString(),
    };
    renderEnvironment(environment);
    if (action === "pause") toast("下载已暂停");
    if (action === "resume") toast("正在继续下载");
    if (action === "cancel") toast("正在取消下载");
  } catch (error) {
    toast(error.message, "error");
    if (button) button.disabled = false;
  }
}

function setEnvironmentInstallMenuOpen(open) {
  const menu = $("#environment-install-menu");
  const toggle = $("#environment-install-menu-toggle");
  menu.hidden = !open;
  toggle.setAttribute("aria-expanded", String(open));
  toggle.classList.toggle("active", open);
}

function handleEnvironmentInstallSelection(event) {
  const input = event.target.closest("[data-environment-select]");
  if (!input) return;
  if (input.checked) state.environmentInstallSelection.add(input.dataset.environmentSelect);
  else state.environmentInstallSelection.delete(input.dataset.environmentSelect);
  if (state.environment) renderEnvironment(state.environment);
}

function handleEnvironmentAction(event) {
  const jobControl = event.target.closest("[data-environment-job-action]");
  if (jobControl) {
    controlEnvironmentJob(jobControl.dataset.environmentJobKey, jobControl.dataset.environmentJobAction, jobControl);
    return;
  }
  const install = event.target.closest("[data-environment-install]");
  if (install) {
    installEnvironmentDependencies(String(install.dataset.environmentInstall || "").split(","));
    return;
  }
  const settings = event.target.closest("[data-environment-panel]");
  if (settings) {
    showTuningPanel(settings.dataset.environmentPanel);
    if (settings.dataset.environmentCapability) {
      setTimeout(() => focusModelCapability(settings.dataset.environmentCapability), 40);
    }
    return;
  }
  const system = event.target.closest("[data-environment-system]");
  if (system) {
    setView("system");
    showSystemTab(system.dataset.environmentSystem || "overview");
  }
}

function renderMigrations(payload = {}) {
  $("#migration-summary").textContent = payload.up_to_date ? `已是最新版 v${payload.current_version}` : `需要升级到 v${payload.target_version}`;
  const host = $("#migration-list");
  const items = Array.isArray(payload.applied) ? payload.applied : [];
  if (!items.length) return renderEmpty(host, "尚未记录数据迁移");
  host.replaceChildren(...items.map((item) => {
    const row = document.createElement("div"); row.className = "migration-row";
    const copy = document.createElement("div");
    const title = document.createElement("strong"); title.textContent = `工作区结构 v${item.version}`;
    const date = document.createElement("span"); date.textContent = formatDate(item.applied_at);
    copy.append(title, date);
    const stateLabel = document.createElement("span"); stateLabel.className = "dependency-state"; stateLabel.textContent = "已应用";
    row.append(copy, stateLabel); return row;
  }));
}

function renderPrivacy(payload = {}) {
  const paused = Boolean(payload.paused);
  const control = $("#privacy-control"); control.classList.toggle("paused", paused);
  $("#privacy-title").textContent = paused ? "敏感能力已暂停" : "敏感能力正常运行";
  $("#privacy-copy").textContent = paused ? "联网、主动消息和游戏观察暂时不会运行" : "联网、主动消息和游戏观察按权限策略运行";
  const button = $("#toggle-privacy"); button.dataset.paused = String(paused);
  button.className = paused ? "primary-button" : "danger-button";
  button.innerHTML = paused ? '<i data-lucide="play"></i><span>恢复敏感能力</span>' : '<i data-lucide="pause"></i><span>暂停敏感能力</span>';
  iconRefresh();
}

async function loadDeployment() {
  try {
    const [dependencies, migrations, privacy] = await Promise.all([api("/api/dependencies"), api("/api/migrations/status"), api("/api/privacy")]);
    renderDependencies(dependencies); renderMigrations(migrations); renderPrivacy(privacy);
  } catch (error) { toast(error.message, "error"); }
}

async function repairDependency(key) {
  try {
    await api("/api/dependencies/repair", { method: "POST", body: JSON.stringify({ key }) });
    toast("依赖修复已在后台开始");
    const poll = async () => {
      const result = await api("/api/dependencies"); renderDependencies(result);
      const current = result.items.find((item) => item.key === key);
      if (current?.state === "installing") setTimeout(() => poll().catch((error) => toast(error.message, "error")), 1500);
    };
    setTimeout(() => poll().catch((error) => toast(error.message, "error")), 800);
  } catch (error) { toast(error.message, "error"); }
}

async function togglePrivacy() {
  const button = $("#toggle-privacy"); button.disabled = true;
  try {
    const result = await api("/api/privacy", { method: "POST", body: JSON.stringify({ paused: button.dataset.paused !== "true" }) });
    renderPrivacy(result); await loadAgentWorkspace();
  } catch (error) { toast(error.message, "error"); } finally { button.disabled = false; }
}

async function loadBackups() {
  try {
    const result = await api("/api/backups"); const host = $("#backup-list");
    host.replaceChildren(...result.items.map((item) => { const row = document.createElement("div"); row.className = "backup-row"; const copy = document.createElement("div"); copy.innerHTML = '<strong></strong><span></span>'; copy.querySelector("strong").textContent = item.name; copy.querySelector("span").textContent = `${formatDate(item.created_at)} · ${(item.size / 1024 / 1024).toFixed(1)} MB`; const button = document.createElement("button"); button.className = "secondary-button"; button.dataset.restoreBackup = item.name; button.innerHTML = '<i data-lucide="history"></i><span>恢复</span>'; row.append(copy, button); return row; }));
    if (!result.items.length) host.innerHTML = '<div class="table-empty compact-empty">还没有本地备份</div>'; iconRefresh();
  } catch (error) { toast(error.message, "error"); }
}

async function importBackup(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".zip")) return toast("请选择 ZIP 备份文件", "error");
  const button = $("#import-backup"); button.disabled = true;
  try {
    const data = await fileToDataUrl(file);
    const result = await api("/api/backups/import", { method: "POST", body: JSON.stringify({ filename: file.name, data }), timeoutMs: 60000 });
    toast(`备份已导入：${result.name}`); await loadBackups();
  } catch (error) { toast(error.message, "error"); } finally { button.disabled = false; $("#backup-import-input").value = ""; }
}

async function createBackup() {
  const button = $("#create-backup"); button.disabled = true;
  try { const result = await api("/api/backups/create", { method: "POST", body: "{}" }); toast(`备份已创建：${result.name}`); await loadBackups(); }
  catch (error) { toast(error.message, "error"); } finally { button.disabled = false; }
}

async function restoreBackup(name) {
  if (!window.confirm(`恢复 ${name}？恢复前会自动保存当前状态。`)) return;
  try { await api("/api/backups/restore", { method: "POST", body: JSON.stringify({ name }) }); toast("备份已恢复，设置和人格已重新载入"); await loadBootstrap(); }
  catch (error) { toast(error.message, "error"); }
}

function scheduleGameCompanionDrain(delay = 500) {
  if (state.gameCompanionRetryTimer) return;
  state.gameCompanionRetryTimer = setTimeout(() => {
    state.gameCompanionRetryTimer = null;
    void drainGameCompanionQueue();
  }, delay);
}

function gameCompanionEventTime(event) {
  const epoch = Number(event?.created_at_epoch || 0);
  if (Number.isFinite(epoch) && epoch > 0) return epoch * 1000;
  const parsed = Date.parse(String(event?.created_at || ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

function isGameCompanionEventFresh(event) {
  if (!event || !state.game?.active) return false;
  const currentGeneration = Number(state.game?.session_generation);
  const eventGeneration = Number(event?.session_generation);
  if (
    Number.isFinite(currentGeneration)
    && Number.isFinite(eventGeneration)
    && currentGeneration !== eventGeneration
  ) return false;
  const now = Date.now();
  const expiresAt = Number(event?.expires_at_epoch || 0) * 1000;
  if (Number.isFinite(expiresAt) && expiresAt > 0 && now >= expiresAt) return false;
  const createdAt = gameCompanionEventTime(event);
  return !createdAt || now - createdAt <= 32_000;
}

function removeGameCompanionEvent(id) {
  state.gameCompanionQueue = state.gameCompanionQueue.filter((item) => item.id !== id);
}

function resetGameCompanionQueue({ resetSeen = false } = {}) {
  state.gameCompanionQueue = [];
  state.gameCompanionRenderController?.abort();
  state.gameCompanionRenderController = null;
  if (state.gameCompanionRetryTimer) clearTimeout(state.gameCompanionRetryTimer);
  state.gameCompanionRetryTimer = null;
  if (resetSeen) state.gameCompanionSeenIds.clear();
}

function queueGameCompanionEvents(events) {
  const candidates = [];
  (Array.isArray(events) ? events : []).forEach((event) => {
    const id = String(event?.id || "");
    const text = String(event?.text || "").trim();
    const internalMarker = /skip|wait|hold_ms|delay_ms|actions|keys|json|输入状态|画面状态|确认当前画面|分析过程|内部指令|系统提示|白名单|再决定动不动/i;
    if (
      !id
      || text.length < 4
      || text.length > 50
      || internalMarker.test(text)
      || /[A-Za-z_]/.test(text)
      || state.gameCompanionSeenIds.has(id)
      || !isGameCompanionEventFresh(event)
    ) return;
    state.gameCompanionSeenIds.add(id);
    candidates.push({ ...event, id, text, audioUrl: "" });
  });
  if (state.gameCompanionSeenIds.size > 200) {
    state.gameCompanionSeenIds = new Set([...state.gameCompanionSeenIds].slice(-120));
  }
  state.gameCompanionQueue = state.gameCompanionQueue.filter(isGameCompanionEventFresh);
  const newest = candidates.sort((left, right) => gameCompanionEventTime(right) - gameCompanionEventTime(left))[0];
  if (newest) {
    const queued = state.gameCompanionQueue[0];
    if (!queued || gameCompanionEventTime(newest) >= gameCompanionEventTime(queued)) {
      state.gameCompanionQueue = [newest];
      if (state.gameCompanionRenderingId && state.gameCompanionRenderingId !== newest.id) {
        state.gameCompanionRenderController?.abort();
      }
    }
  }
  void drainGameCompanionQueue();
}

async function drainGameCompanionQueue() {
  if (state.gameCompanionRendering || state.voiceCallCompanionPlaying) return;
  state.gameCompanionQueue = state.gameCompanionQueue.filter(isGameCompanionEventFresh).slice(-1);
  if (!state.game?.active || !state.voiceCallActive || !state.gameCompanionQueue.length) return;
  const userHasPriority = () => Boolean(
    state.voiceCallProcessing
    || state.voiceCallSpeechStartedAt
    || state.voiceCallVoiceFrames >= 3
  );
  if (userHasPriority()) {
    scheduleGameCompanionDrain(450);
    return;
  }
  const item = state.gameCompanionQueue[0];
  if (!item.audioUrl) {
    state.gameCompanionRendering = true;
    state.gameCompanionRenderingId = item.id;
    const controller = new AbortController();
    state.gameCompanionRenderController = controller;
    let renderedUrl = "";
    try {
      const rendered = await api("/api/voice/render", {
        method: "POST",
        body: JSON.stringify({
          text: item.text,
          language: item.language || "zh",
          call_mode: true,
          quality: "complete",
        }),
        timeoutMs: 180_000,
        signal: controller.signal,
      });
      renderedUrl = String(rendered.audio_url || "");
    } catch (error) {
      if (error.name !== "AbortError") console.warn("game companion voice was not available", error);
    } finally {
      if (state.gameCompanionRenderingId === item.id) {
        state.gameCompanionRendering = false;
        state.gameCompanionRenderingId = "";
        state.gameCompanionRenderController = null;
      }
    }
    const stillLatest = state.gameCompanionQueue[0]?.id === item.id;
    if (!renderedUrl || !stillLatest || !isGameCompanionEventFresh(item)) {
      removeGameCompanionEvent(item.id);
      return void drainGameCompanionQueue();
    }
    item.audioUrl = renderedUrl;
  }
  if (userHasPriority()) {
    scheduleGameCompanionDrain(450);
    return;
  }
  if (!state.game?.active || !state.voiceCallActive || !isGameCompanionEventFresh(item)) {
    removeGameCompanionEvent(item.id);
    return void drainGameCompanionQueue();
  }
  removeGameCompanionEvent(item.id);
  state.voiceCallCompanionPlaying = true;
  state.voiceCallProcessing = true;
  stopVoiceCallSegment(true);
  const generation = state.voiceCallGeneration;
  try {
    addMessage("assistant", item.text);
    appendVoiceCallTranscript("assistant", item.text);
    await playVoiceCallReply(item.audioUrl, generation, { companion: true });
  } finally {
    state.voiceCallCompanionPlaying = false;
    if (state.voiceCallActive && generation === state.voiceCallGeneration) {
      resumeVoiceCallListening(generation, "你说吧，我在听");
    }
    if (state.gameCompanionQueue.length) scheduleGameCompanionDrain(700);
  }
}

function gameVisualEventLabel(kind) {
  return ({
    initial: "初始画面",
    layout: "画面布局变化",
    scene: "场景变化",
    activity: "局面变化",
  })[String(kind || "")] || "等待事件";
}

function renderGameStatus(game) {
  game = { ...game, mode: "observe" };
  const previousGeneration = Number(state.game?.session_generation);
  const nextGeneration = Number(game.session_generation);
  state.game = game;
  const perception = game.perception || {};
  const adapter = game.adapter || perception.adapter || {};
  const active = Boolean(game.active);
  const captureWarning = String(perception.capture_warning || game.window_warning || "").trim();
  if (
    game.active
    && Number.isFinite(previousGeneration)
    && Number.isFinite(nextGeneration)
    && previousGeneration !== nextGeneration
  ) resetGameCompanionQueue({ resetSeen: true });
  if ($("#settings-game-interval")) $("#settings-game-interval").value = String(game.observation_interval_s || 6);
  if ($("#settings-game-change-threshold")) $("#settings-game-change-threshold").value = String(Number(game.change_threshold || 0.015) * 100);
  if ($("#settings-game-idle-cycles")) $("#settings-game-idle-cycles").value = String(game.max_idle_cycles || 2);
  if ($("#settings-game-companion-interval")) $("#settings-game-companion-interval").value = String(game.companion_interval_s || 12);
  if ($("#settings-game-companion")) $("#settings-game-companion").checked = game.companion_enabled !== false;
  if ($("#settings-game-auto-call")) $("#settings-game-auto-call").checked = game.auto_voice_call !== false;
  if ($("#game-interval")) $("#game-interval").value = String(game.observation_interval_s || 6);
  updateGamePreferenceLabels();
  updateGameModeControls();
  if ($("#game-screen-source")) $("#game-screen-source").textContent = game.screen_name || "整个屏幕";
  if ($("#game-screen-copy")) {
    const size = game.window_width && game.window_height ? ` · ${game.window_width}×${game.window_height}` : "";
    $("#game-screen-copy").textContent = game.window_ready === false
      ? (captureWarning || "屏幕当前不可用")
      : `自动共享主显示器画面${size}，不需要选择游戏窗口。`;
  }
  const toggle = $("#toggle-game-session");
  toggle.dataset.action = active ? "stop" : "start";
  toggle.innerHTML = active
    ? '<i data-lucide="square"></i><span>结束观察</span>'
    : '<i data-lucide="play"></i><span>开始观察</span>';
  $("#game-status-copy").textContent = captureWarning || (active
    ? `${game.screen_name || "整个屏幕"} · 观察中`
    : (game.window_ready === false ? "屏幕当前不可用" : "整个屏幕已就绪"));
  $("#inspector-game-title").textContent = active ? "屏幕观察进行中" : "整个屏幕已就绪";
  $("#inspector-game-copy").textContent = game.latest?.analysis || (active ? `${characterName()}正在看你玩游戏` : "开始观察后显示实时状态");
  $("#inspector-game-meta").innerHTML = `<span>工作方式</span><strong>事件驱动</strong><span>会话</span><strong>${active ? "运行中" : "未开始"}</strong>`;
  $("#game-loop-status").textContent = active ? "事件感知运行中" : "观察未运行";
  $("#game-adapter-name").textContent = adapter.name || (active ? "通用游戏" : "等待识别");
  $("#game-perception-fps").textContent = Number(perception.fps) > 0 ? `${Number(perception.fps).toFixed(1)} FPS` : "-- FPS";
  $("#game-capture-latency").textContent = Number.isFinite(Number(perception.capture_ms)) ? `${Number(perception.capture_ms).toFixed(1)} ms` : "-- ms";
  $("#game-action-state").textContent = !active
    ? "未运行"
    : perception.analysis_in_progress
      ? "正在分析"
      : gameVisualEventLabel(perception.event_kind);
  const hasFrames = Number(perception.captured_frames || 0) > 0;
  const validPixels = Number(perception.non_black_ratio || 0);
  $("#game-local-vision-state").textContent = hasFrames
    ? `已接收${validPixels ? ` · ${(validPixels * 100).toFixed(0)}%有效` : ""}`
    : "等待画面";
  $("#game-analyzed-frames").textContent = perception.analysis_in_progress
    ? "分析中"
    : `${Number(perception.analyzed_frames || 0)} 帧`;
  $("#game-change-ratio").textContent = Number.isFinite(Number(game.latest?.change_ratio)) ? `${(Number(game.latest.change_ratio) * 100).toFixed(1)}%` : "--";
  if (captureWarning) $("#game-analysis-copy").textContent = captureWarning;
  else if (game.latest?.analysis) $("#game-analysis-copy").textContent = game.latest.analysis;
  else if (game.latest?.error) $("#game-analysis-copy").textContent = `本轮观察失败：${game.latest.error}`;
  else if (active && perception.analysis_in_progress) $("#game-analysis-copy").textContent = `画面正在实时显示，${characterName()}正在理解当前内容。`;
  const preview = $("#game-preview");
  const previewUrl = perception.preview_url || game.latest?.capture_url || "";
  const previewVersion = perception.preview_frame_id || game.latest?.updated_at || "latest";
  if (game.window_ready === false) {
    preview.replaceChildren();
    const icon = document.createElement("i");
    icon.dataset.lucide = "scan-off";
    const copy = document.createElement("span");
    copy.textContent = captureWarning || "当前没有可共享的屏幕画面";
    preview.append(icon, copy);
  } else if (previewUrl) {
    let image = preview.querySelector("img");
    if (!image) {
      preview.replaceChildren();
      image = document.createElement("img");
      image.alt = "当前共享屏幕";
      preview.append(image);
    }
    const nextSource = `${previewUrl}?frame=${encodeURIComponent(previewVersion)}`;
    if (image.getAttribute("src") !== nextSource) image.src = nextSource;
  } else if (!active) {
    preview.replaceChildren();
    const icon = document.createElement("i");
    icon.dataset.lucide = "monitor-up";
    const copy = document.createElement("span");
    copy.textContent = "开始观察后共享整个屏幕";
    preview.append(icon, copy);
  }
  queueGameCompanionEvents(game.companion_events);
  if (!active) {
    resetGameCompanionQueue({ resetSeen: true });
  }
  if (state.gameTimer) { clearTimeout(state.gameTimer); state.gameTimer = null; }
  if (active) state.gameTimer = setTimeout(async () => {
    try { renderGameStatus(await api("/api/game/status")); } catch (error) { toast(error.message, "error"); }
  }, 650);
  iconRefresh();
}

function updateGamePreferenceLabels() {
  if ($("#settings-game-interval-value")) $("#settings-game-interval-value").textContent = `${Number($("#settings-game-interval").value || 6)} 秒`;
  if ($("#settings-game-change-value")) $("#settings-game-change-value").textContent = `${Number($("#settings-game-change-threshold").value || 1.5).toFixed(1)}%`;
  if ($("#settings-game-idle-value")) $("#settings-game-idle-value").textContent = `${Number($("#settings-game-idle-cycles").value || 2)} 轮`;
  if ($("#settings-game-companion-interval-value")) $("#settings-game-companion-interval-value").textContent = `${Number($("#settings-game-companion-interval").value || 12)} 秒`;
}

function updateGameModeControls() {
  $("#game-interval-section").hidden = false;
  $("#game-interval-value").textContent = `${Number($("#game-interval").value || 6)} 秒`;
  $("#game-loop-status").textContent = state.game?.active ? "事件感知运行中" : "观察未运行";
}

async function loadGame() {
  try { renderGameStatus(await api("/api/game/status")); }
  catch (error) { toast(error.message, "error"); }
}

async function loadGamePreferences() {
  try { renderGameStatus(await api("/api/game/status")); }
  catch (error) { toast(error.message, "error"); }
}

async function saveGamePreferences() {
  const button = $("#save-game-preferences");
  button.disabled = true;
  try {
    const game = await api("/api/game/configure", {
      method: "POST",
      body: JSON.stringify({
        mode: "observe",
        observation_interval_s: Number($("#settings-game-interval").value || 6),
        change_threshold: Number($("#settings-game-change-threshold").value || 1.5) / 100,
        max_idle_cycles: Number($("#settings-game-idle-cycles").value || 2),
        companion_interval_s: Number($("#settings-game-companion-interval").value || 12),
        companion_enabled: $("#settings-game-companion").checked,
        auto_voice_call: $("#settings-game-auto-call").checked,
      }),
    });
    renderGameStatus(game);
    toast("事件驱动观察设置已保存");
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.disabled = false;
  }
}

async function saveGameSettings() {
  try { renderGameStatus(await api("/api/game/configure", { method: "POST", body: JSON.stringify({ mode: "observe", observation_interval_s: Number($("#game-interval").value || 6) }) })); toast("事件驱动观察设置已保存"); }
  catch (error) { toast(error.message, "error"); }
}

async function toggleGameSession() {
  const action = $("#toggle-game-session").dataset.action;
  try {
    const game = await api(`/api/game/${action}`, { method: "POST", body: "{}" });
    renderGameStatus(game);
    if (action === "start" && game.auto_voice_call && !state.voiceCallActive) {
      await startVoiceCall({ minimize: true, gameOwned: true });
    } else if (action === "stop" && state.gameOwnedVoiceCall) {
      endVoiceCall({ silent: true });
    }
    toast(action === "start" ? "游戏会话已开始" : "游戏会话已结束");
  }
  catch (error) { toast(error.message, "error"); }
}

async function analyzeGame() {
  const button = $("#analyze-game"); button.disabled = true;
  try { const result = await api("/api/game/analyze", { method: "POST", body: "{}" }); $("#game-preview").innerHTML = `<img src="${result.capture.url}?t=${Date.now()}" alt="当前游戏画面">`; $("#game-analysis-copy").textContent = result.analysis; }
  catch (error) { toast(error.message, "error"); } finally { button.disabled = false; }
}

function formatScope(scope) {
  if (scope === "global") return "全局";
  if (scope === "web") return "联网";
  if (scope.startsWith("user:")) return "人物";
  if (scope.startsWith("group:")) return "群聊";
  return scope;
}

function renderImportance(value) {
  const wrap = document.createElement("span"); wrap.className = "importance";
  const score = document.createElement("strong"); score.textContent = String(Math.max(1, Math.min(10, Number(value) || 1)));
  const total = document.createElement("small"); total.textContent = "/10";
  wrap.append(score, total);
  return wrap;
}

function formatDate(value) {
  if (!value) return "--";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value.slice(0, 16) : date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

async function savePersona() {
  const button = $("#save-persona");
  const content = currentPersonaContent();
  const addressInput = $("#owner-addresses");
  const addresses = parseOwnerAddresses(addressInput?.value);
  if (!content.trim()) {
    toast("人格角色卡不能为空", "error");
    return;
  }
  if (content.length > 80_000) {
    toast("人格角色卡不能超过 80000 字", "error");
    return;
  }
  if (!addresses.length) {
    toast("请至少保留一个昔夕对你的称呼", "error");
    addressInput?.focus();
    return;
  }
  if (addressInput) addressInput.value = addresses.join("、");
  renderOwnerAddressList(addresses.join("、"));
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  try {
    const [persona, applied] = await Promise.all([
      api("/api/persona", { method: "PUT", body: JSON.stringify({ content }) }),
      api("/api/settings", {
        method: "PUT",
        body: JSON.stringify(collectSettings($("#tuning-persona"))),
      }),
    ]);
    state.bootstrap.persona = persona;
    Object.assign(state.bootstrap.settings, applied);
    applyAssistantIdentity(state.bootstrap.settings);
    const localSettings = persistLocalSettings();
    fillLocalSettings(localSettings);
    loadPersonaDraft(persona.content);
    updateOwnerChanceLabel();
    toast("人格设置已保存");
  } catch (error) { toast(error.message, "error"); }
  finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}

async function saveInterests() {
  try {
    await api("/api/interests", { method: "PUT", body: JSON.stringify(state.interests) });
    toast("兴趣档案已更新"); renderInterests(state.interests);
  } catch (error) { toast(error.message, "error"); }
}

function collectSettings(panel) {
  const values = {};
  $$('[data-setting]', panel).forEach((input) => {
    values[input.dataset.setting] = input.type === "checkbox" ? input.checked : input.value;
  });
  return values;
}

async function saveSettings(panel) {
  const values = collectSettings(panel);
  if (!Object.keys(values).length) return;
  try {
    const applied = await api("/api/settings", { method: "PUT", body: JSON.stringify(values) });
    Object.assign(state.bootstrap.settings, applied);
    applyAssistantIdentity(state.bootstrap.settings);
    applyOwnerProfile(state.bootstrap.settings);
    toast("设置已保存并应用"); await loadStatus();
  } catch (error) { toast(error.message, "error"); }
}

async function loadLogs() {
  try {
    const result = await api("/api/logs?lines=240");
    const viewer = $("#log-viewer"); viewer.textContent = result.lines.join("\n"); viewer.scrollTop = viewer.scrollHeight;
  } catch (error) { toast(error.message, "error"); }
}

async function refreshCurrentView() {
  if (state.currentView === "home") {
    await loadBootstrap();
  } else if (state.currentView === "memory") {
    await loadMemories();
  } else if (state.currentView === "growth") {
    await loadGrowthWorkspace();
  } else if (state.currentView === "tuning") {
    await loadBootstrap();
    if (state.currentTuning === "data") await loadBackups();
    if (state.currentTuning === "model") await loadModelWorkspace();
    if (state.currentTuning === "environment") await loadEnvironment();
    if (state.currentTuning === "advanced") await loadAdvancedSettings();
  } else if (state.currentView === "system") {
    if (state.systemTab === "overview") { await loadStatus(); await loadDiagnostics(true); }
    if (state.systemTab === "tasks") await loadAgentWorkspace();
    if (state.systemTab === "activity") loadActivityView();
    if (state.systemTab === "deployment") await loadDeployment();
    if (state.systemTab === "logs") await loadLogs();
  } else if (state.currentView === "game") {
    await loadGame();
  } else {
    await loadStatus();
  }
}

function updateOwnerChanceLabel() {
  const input = $('[data-setting="owner_address_chance"]');
  $("#owner-chance-label").textContent = `${Math.round(Number(input.value || 0) * 100)}%`;
}

function bindEvents() {
  $("#retry-bootstrap").addEventListener("click", () => void retryBootstrap());
  $$('[data-view]').forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
  $$('[data-view-target]').forEach((button) => button.addEventListener("click", () => setView(button.dataset.viewTarget)));
  $$('[data-system-tab-target]').forEach((button) => button.addEventListener("click", () => showSystemTab(button.dataset.systemTabTarget)));
  $$('[data-system-tab]').forEach((button) => button.addEventListener("click", () => showSystemTab(button.dataset.systemTab)));
  $$(".tuning-tab").forEach((button) => button.addEventListener("click", () => showTuningPanel(button.dataset.tuning)));
  $("#settings-back-button").addEventListener("click", () => setView(viewMeta[state.settingsReturnView] ? state.settingsReturnView : "home"));
  $("#toggle-navigation").addEventListener("click", () => setNavigation(!document.body.classList.contains("navigation-open")));
  $("#close-navigation").addEventListener("click", closeNavigation);
  $("#toggle-inspector").addEventListener("click", () => setInspector(!document.body.classList.contains("inspector-open")));
  $("#expand-inspector").addEventListener("click", () => setInspector(true));
  $("#inspector-mood-button").addEventListener("click", () => setInspector(true));
  $("#inspector-rail").addEventListener("click", (event) => {
    const service = event.target.closest("[data-rail-service]");
    if (service) toggleQuickService(service);
  });
  $$('[data-inspector-section]').forEach((button) => button.addEventListener("click", () => {
    setView("system");
    showSystemTab("overview");
    setInspector(true);
    setTimeout(() => $("#inspector-connection-card").scrollIntoView({ behavior: "smooth", block: "center" }), 40);
  }));
  $("#close-inspector").addEventListener("click", () => setInspector(false));
  $("#inspector-status-list").addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-quick-service]");
    if (toggle) { toggleQuickService(toggle); return; }
    const settings = event.target.closest("[data-quick-panel]");
    if (settings) openQuickServiceSettings(settings);
  });
  $("#startup-service-list").addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-quick-service]");
    if (toggle) { toggleQuickService(toggle); return; }
    const settings = event.target.closest("[data-quick-panel]");
    if (settings) openQuickServiceSettings(settings);
  });
  $("#drawer-backdrop").addEventListener("click", () => { closeNavigation(); setInspector(false); setNotificationPanel(false); });
  $("#attach-image").addEventListener("click", () => $("#image-input").click());
  $("#image-input").addEventListener("change", async (event) => {
    const files = [...event.target.files].slice(0, 4 - state.images.length);
    state.images.push(...await Promise.all(files.map(fileToDataUrl)));
    event.target.value = ""; renderImageStrip();
  });
  $("#send-message").addEventListener("click", sendMessage);
  $("#stop-message").addEventListener("click", stopWaiting);
  $("#clear-chat-history").addEventListener("click", clearChatHistory);
  $("#cancel-reply").addEventListener("click", clearReply);
  $("#message-stream").addEventListener("click", handleMessageAction);
  $("#chat-input").addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendMessage(); } });
  $("#record-voice").addEventListener("click", openVoiceInput);
  $("#voice-record-control").addEventListener("click", toggleVoiceRecording);
  $("#close-voice-input").addEventListener("click", closeVoiceInput);
  $("#start-voice-call").addEventListener("click", () => startVoiceCall());
  $("#game-voice-call").addEventListener("click", () => startVoiceCall({ minimize: true }));
  $("#toggle-call-microphone").addEventListener("click", toggleVoiceCallMicrophone);
  $("#toggle-call-speaker").addEventListener("click", toggleVoiceCallSpeaker);
  $("#end-voice-call").addEventListener("click", endVoiceCall);
  $("#end-voice-call-dock").addEventListener("click", endVoiceCall);
  $("#minimize-voice-call").addEventListener("click", minimizeVoiceCall);
  const voiceCallDockHandle = $("#restore-voice-call");
  voiceCallDockHandle.addEventListener("pointerdown", beginVoiceCallDockDrag);
  voiceCallDockHandle.addEventListener("pointermove", moveVoiceCallDock);
  voiceCallDockHandle.addEventListener("pointerup", endVoiceCallDockDrag);
  voiceCallDockHandle.addEventListener("pointercancel", endVoiceCallDockDrag);
  voiceCallDockHandle.addEventListener("click", (event) => {
    if (state.voiceCallDockSuppressClick) {
      event.preventDefault();
      state.voiceCallDockSuppressClick = false;
      return;
    }
    restoreVoiceCall();
  });
  $("#close-voice-call").addEventListener("click", endVoiceCall);
  $("#inspector-clear-reply").addEventListener("click", clearReply);
  $("#memory-query").addEventListener("input", debounce(loadMemories, 280));
  $("#memory-scope").addEventListener("change", loadMemories);
  $("#memory-category-filter").addEventListener("change", loadMemories);
  $("#memory-library-back").addEventListener("click", () => {
    $("#memory-query").value = "";
    state.memoryActiveCollection = "";
    clearMemorySelection();
    void loadMemories();
  });
  $("#memory-library-content").addEventListener("click", (event) => {
    const deleteTarget = event.target.closest("[data-memory-delete-id]");
    if (deleteTarget) {
      event.preventDefault();
      event.stopPropagation();
      void deleteMemoryById(deleteTarget.dataset.memoryDeleteId, { button: deleteTarget });
      return;
    }
    const editTarget = event.target.closest("[data-memory-edit-id]");
    if (editTarget) {
      event.preventDefault();
      event.stopPropagation();
      selectMemory(editTarget.dataset.memoryEditId);
      openMemoryDialog(editTarget.dataset.memoryEditId);
      return;
    }
    const book = event.target.closest("[data-memory-open-id]");
    if (book) {
      if (!state.memoryActiveCollection && !$("#memory-query").value.trim()) {
        state.memoryActiveCollection = book.dataset.memoryCollection || memoryCollectionFor(state.memoryItems.get(String(book.dataset.memoryOpenId))).id;
        renderMemoryLibrary([...state.memoryItems.values()]);
      }
      selectMemory(book.dataset.memoryOpenId);
      return;
    }
    const shelf = event.target.closest("[data-memory-collection]");
    if (shelf) {
      state.memoryActiveCollection = shelf.dataset.memoryCollection;
      clearMemorySelection();
      renderMemoryLibrary([...state.memoryItems.values()]);
      iconRefresh();
    }
  });
  $("#memory-reader-edit").addEventListener("click", () => openMemoryDialog(state.selectedMemoryId));
  $("#memory-reader-delete").addEventListener("click", (event) => void deleteMemoryById(state.selectedMemoryId, { button: event.currentTarget }));
  $("#memory-reader-close").addEventListener("click", clearMemorySelection);
  $("#inspector-edit-memory").addEventListener("click", () => openMemoryDialog(state.selectedMemoryId));
  $("#inspector-chat-memories").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-chat-memory-id]");
    if (!button) return;
    $("#memory-query").value = button.dataset.chatMemoryContent || "";
    setView("memory");
    await loadMemories();
    selectMemory(button.dataset.chatMemoryId);
  });
  $("#memory-form").addEventListener("submit", saveMemory);
  $("#memory-cancel").addEventListener("click", () => $("#memory-dialog").close());
  $("#delete-memory").addEventListener("click", deleteMemory);
  $("#confirm-dialog-cancel").addEventListener("click", () => settleConfirmation(false));
  $("#confirm-dialog-accept").addEventListener("click", () => settleConfirmation(true));
  $("#confirm-dialog").addEventListener("cancel", (event) => { event.preventDefault(); settleConfirmation(false); });
  $("#confirm-dialog").addEventListener("click", (event) => { if (event.target === event.currentTarget) settleConfirmation(false); });
  $$('[data-persona-tab]').forEach((button) => {
    button.addEventListener("click", () => activatePersonaTab(button.dataset.personaTab));
  });
  $("#persona-editor").addEventListener("input", () => {
    state.personaDraft = parsePersonaContent($("#persona-editor").value);
    updatePersonaCharacterCount();
  });
  $("#export-persona").addEventListener("click", exportPersonaCard);
  $("#import-persona").addEventListener("click", () => $("#persona-import-input").click());
  $("#persona-import-input").addEventListener("change", async (event) => {
    const [file] = event.target.files;
    event.target.value = "";
    await importPersonaFile(file);
  });
  $("#change-xixi-avatar").addEventListener("click", () => $("#xixi-avatar-input").click());
  $("#xixi-avatar-input").addEventListener("change", async (event) => {
    const [file] = event.target.files;
    event.target.value = "";
    if (file) await updateXixiAvatar(file);
  });
  $("#reset-xixi-avatar").addEventListener("click", resetXixiAvatar);
  $("#owner-addresses").addEventListener("input", (event) => renderOwnerAddressList(event.target.value));
  $("#save-persona").addEventListener("click", savePersona);
  $("#save-interests").addEventListener("click", saveInterests);
  $$('[data-interest-filter]').forEach((button) => {
    button.addEventListener("click", () => {
      state.interestFilter = button.dataset.interestFilter || "all";
      renderInterests(state.interests || { interests: [] });
    });
  });
  $("#generate-daily-reflection").addEventListener("click", generateReflection);
  $("#reflection-previous-month").addEventListener("click", () => navigateReflectionMonth(-1));
  $("#reflection-next-month").addEventListener("click", () => navigateReflectionMonth(1));
  $("#reflection-today").addEventListener("click", showCurrentReflectionDate);
  $("#reflection-month-picker").addEventListener("change", (event) => {
    const monthKey = event.target.value;
    if (/^\d{4}-\d{2}$/.test(monthKey) && monthKey <= reflectionMonthKey()) loadReflectionMonth(monthKey);
    else event.target.value = state.reflectionMonth || reflectionMonthKey();
  });
  $("#reflection-calendar").addEventListener("click", (event) => {
    const day = event.target.closest("[data-reflection-date]");
    if (day) selectReflectionDate(day.dataset.reflectionDate);
  });
  $("#save-interface").addEventListener("click", saveInterfaceSettings);
  $("#reset-custom-theme").addEventListener("click", resetCustomTheme);
  $("#theme-card-list").addEventListener("click", (event) => {
    const card = event.target.closest("[data-theme-choice]");
    if (card) chooseTheme(card.dataset.themeChoice);
  });
  $("#custom-theme-editor").addEventListener("input", handleCustomThemeInput);
  $("#tuning-interface").addEventListener("change", (event) => {
    if (event.target.matches("[data-local-setting]")) previewInterfaceSettings();
  });
  $("#change-user-avatar").addEventListener("click", () => $("#user-avatar-input").click());
  $("#change-chat-background").addEventListener("click", () => $("#chat-background-input").click());
  $("#user-avatar-input").addEventListener("change", async (event) => {
    const [file] = event.target.files;
    event.target.value = "";
    if (file) await updateAppearanceImage("avatar", file);
  });
  $("#chat-background-input").addEventListener("change", async (event) => {
    const [file] = event.target.files;
    event.target.value = "";
    if (file) await updateAppearanceImage("background", file);
  });
  $("#reset-user-avatar").addEventListener("click", () => resetAppearanceImage("avatar"));
  $("#reset-chat-background").addEventListener("click", () => resetAppearanceImage("background"));
  $("#save-desktop").addEventListener("click", saveDesktopSettings);
  $("#microphone-permission-toggle").addEventListener("change", (event) => void toggleMicrophonePermission(event));
  $("#request-microphone-permission").addEventListener("click", () => void verifyMicrophonePermission());
  $("#open-microphone-settings").addEventListener("click", () => void openWindowsMicrophoneSettings());
  $("#microphone-permission-system").addEventListener("click", () => void openWindowsMicrophoneSettings());
  $("#microphone-permission-deny").addEventListener("click", () => void settleMicrophonePermissionDialog(false));
  $("#microphone-permission-allow").addEventListener("click", () => void settleMicrophonePermissionDialog(true));
  $("#microphone-permission-dialog").addEventListener("cancel", (event) => {
    event.preventDefault();
    void settleMicrophonePermissionDialog(false);
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
  $("#add-model-provider").addEventListener("click", () => openModelProviderDialog());
  $("#fetch-model-provider-models").addEventListener("click", fetchModelProviderModels);
  $("#model-provider-base-url").addEventListener("input", updateModelProviderCompatibilityHint);
  $("#model-provider-form").addEventListener("submit", saveModelProvider);
  $("#model-provider-cancel").addEventListener("click", () => $("#model-provider-dialog").close());
  $("#model-provider-list").addEventListener("click", (event) => {
    const target = event.target.closest("[data-provider-add-model], [data-provider-delete], [data-model-delete], [data-model-test], [data-model-activate]");
    if (target) void handleModelProviderAction(target);
  });
  $("#fallback-model-form").addEventListener("submit", addFallbackModel);
  $("#fallback-use-primary-key").addEventListener("change", syncFallbackKeyMode);
  $("#fallback-model-list").addEventListener("change", (event) => { const target = event.target.closest("[data-profile-toggle]"); if (target) handleFallbackModelAction(target); });
  $("#fallback-model-list").addEventListener("click", (event) => { const target = event.target.closest("[data-profile-delete]"); if (target) handleFallbackModelAction(target); });
  $("#save-qq-identity").addEventListener("click", () => updateQqIdentity(false));
  $("#switch-qq-account").addEventListener("click", () => updateQqIdentity(true));
  for (const input of [$("#bot-qq-id"), $("#owner-qq-id")]) {
    input.addEventListener("input", () => {
      state.qqIdentityDirty = true;
      updateQqSetupGuide(state.status?.qq || {});
      iconRefresh();
    });
  }
  $("#qq-guide-primary").addEventListener("click", runQqSetupGuide);
  $("#qq-login-qr").addEventListener("click", loginQqWithQr);
  $("#qq-qr-close").addEventListener("click", closeQqQrDialog);
  $("#qq-qr-refresh").addEventListener("click", restartQqQrLogin);
  $("#qq-qr-dialog").addEventListener("close", closeQqQrDialog);
  $("#qq-start-channel").addEventListener("click", () => controlQqAction("online"));
  $("#qq-stop-channel").addEventListener("click", () => controlQqAction("offline"));
  $("#qq-restart-channel").addEventListener("click", restartQqChannel);
  $("#open-qq-install-guide").addEventListener("click", openNapcatInstallGuide);
  $$(".save-settings-panel").forEach((button) => button.addEventListener("click", () => saveSettings($("#tuning-" + button.dataset.panel))));
  $("#settings-search-input").addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.currentTarget.value = "";
      searchSettings("");
      return;
    }
    if (event.key === "Enter") { event.preventDefault(); searchSettings(event.currentTarget.value); }
  });
  $("#settings-search-input").addEventListener("input", debounce((event) => {
    searchSettings(event.target.value);
  }, 140));
  $("#settings-search-input").addEventListener("search", (event) => searchSettings(event.currentTarget.value));
  $('[data-setting="owner_address_chance"]').addEventListener("input", updateOwnerChanceLabel);
  $("#refresh-logs").addEventListener("click", loadLogs);
  $("#refresh-agent-dashboard").addEventListener("click", loadAgentWorkspace);
  $("#agent-goal-form").addEventListener("submit", createAgentGoal);
  $("#agent-goal-list").addEventListener("click", (event) => { const button = event.target.closest("[data-goal-id]"); if (button) updateAgentItem(button); });
  $("#agent-thread-list").addEventListener("click", (event) => { const button = event.target.closest("[data-thread-id]"); if (button) updateAgentItem(button); });
  $("#save-agent-policy").addEventListener("click", saveAgentPolicy);
  $("#refresh-deployment").addEventListener("click", loadDeployment);
  $("#refresh-environment").addEventListener("click", loadEnvironment);
  $("#install-missing-environment").addEventListener("click", (event) => {
    installEnvironmentDependencies(String(event.currentTarget.dataset.environmentInstall || "").split(","));
    setEnvironmentInstallMenuOpen(false);
  });
  $("#environment-install-menu-toggle").addEventListener("click", (event) => {
    event.stopPropagation();
    setEnvironmentInstallMenuOpen($("#environment-install-menu").hidden);
  });
  $("#environment-install-menu-close").addEventListener("click", () => setEnvironmentInstallMenuOpen(false));
  $("#environment-install-menu").addEventListener("click", (event) => event.stopPropagation());
  $("#environment-install-options").addEventListener("change", handleEnvironmentInstallSelection);
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".environment-install-picker")) setEnvironmentInstallMenuOpen(false);
  });
  $("#environment-list").addEventListener("click", handleEnvironmentAction);
  $("#refresh-advanced").addEventListener("click", loadAdvancedSettings);
  $("#advanced-path-list").addEventListener("click", (event) => {
    const button = event.target.closest("[data-copy-path]");
    if (button) copyAdvancedPath(button.dataset.copyPath);
  });
  $("#toggle-privacy").addEventListener("click", togglePrivacy);
  $("#dependency-list").addEventListener("click", (event) => { const button = event.target.closest("[data-dependency-repair]"); if (button) repairDependency(button.dataset.dependencyRepair); });
  $("#run-diagnostics").addEventListener("click", () => loadDiagnostics(true));
  $("#diagnostic-list").addEventListener("click", (event) => { const button = event.target.closest("[data-repair-service]"); if (button) repairService(button.dataset.repairService); });
  $$('[data-activity-tab]').forEach((button) => button.addEventListener("click", () => showActivityTab(button.dataset.activityTab)));
  $("#activity-category").addEventListener("change", loadActivities);
  $("#refresh-activity").addEventListener("click", loadActivityView);
  $("#create-backup").addEventListener("click", createBackup);
  $("#import-backup").addEventListener("click", () => $("#backup-import-input").click());
  $("#backup-import-input").addEventListener("change", (event) => importBackup(event.target.files?.[0]));
  $("#backup-list").addEventListener("click", (event) => { const button = event.target.closest("[data-restore-backup]"); if (button) restoreBackup(button.dataset.restoreBackup); });
  $("#game-interval").addEventListener("input", () => updateGameModeControls());
  $("#settings-game-interval").addEventListener("input", updateGamePreferenceLabels);
  $("#settings-game-change-threshold").addEventListener("input", updateGamePreferenceLabels);
  $("#settings-game-idle-cycles").addEventListener("input", updateGamePreferenceLabels);
  $("#settings-game-companion-interval").addEventListener("input", updateGamePreferenceLabels);
  $("#save-game-preferences").addEventListener("click", saveGamePreferences);
  $("#save-game-settings").addEventListener("click", saveGameSettings);
  $("#toggle-game-session").addEventListener("click", toggleGameSession);
  $("#analyze-game").addEventListener("click", analyzeGame);
  $("#weather-city-form").addEventListener("submit", saveWeatherCity);
  $("#weather-city-cancel").addEventListener("click", () => $("#weather-city-dialog").close());
  $("#weather-city-setting").addEventListener("input", syncWeatherCityPreset);
  $("#weather-city-preset").addEventListener("change", chooseWeatherCityPreset);
  $("#status-grid").addEventListener("click", (event) => {
    const button = event.target.closest(".service-card-control");
    if (button) handleServiceControl(button);
  });
  $("#refresh-view").addEventListener("click", refreshCurrentView);
  $("#open-command-palette").addEventListener("click", openCommandPalette);
  $("#command-input").addEventListener("input", (event) => renderCommands(event.target.value));
  $("#command-input").addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); moveCommandSelection(event.key === "ArrowDown" ? 1 : -1); }
    if (event.key === "Enter") { event.preventDefault(); const selected = $(".command-item.selected", $("#command-list")) || $(".command-item", $("#command-list")); if (selected) runCommand(selected.dataset.commandId); }
  });
  $("#command-list").addEventListener("click", (event) => { const item = event.target.closest("[data-command-id]"); if (item) runCommand(item.dataset.commandId); });
  $("#open-notifications").addEventListener("click", () => setNotificationPanel(!$("#notification-panel").classList.contains("open")));
  $("#close-notifications").addEventListener("click", () => setNotificationPanel(false));
  $("#mark-notifications-read").addEventListener("click", markNotificationsRead);
  $("#notification-list").addEventListener("click", (event) => {
    const item = event.target.closest("[data-notification-id]");
    if (!item) return;
    const read = readNotificationIds(); read.add(item.dataset.notificationId);
    localStorage.setItem(notificationReadKey, JSON.stringify([...read].slice(-200)));
    renderNotifications();
  });
  document.addEventListener("keydown", (event) => {
    if (state.voiceCallActive && event.key === "Escape") {
      event.preventDefault();
      if (!state.voiceCallMinimized) minimizeVoiceCall();
      return;
    }
    if (state.voiceInputOpen && event.code === "Space" && !event.repeat) {
      event.preventDefault();
      state.voiceSpaceHeld = true;
      startVoiceRecording();
      return;
    }
    if (state.voiceInputOpen && event.key === "Escape") {
      event.preventDefault();
      closeVoiceInput();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); openCommandPalette(); }
    if (event.key === "Escape") setNotificationPanel(false);
  });
  document.addEventListener("keyup", (event) => {
    if (!state.voiceInputOpen || event.code !== "Space" || !state.voiceSpaceHeld) return;
    event.preventDefault();
    state.voiceSpaceHeld = false;
    stopVoiceRecording();
  });
}

function debounce(fn, wait) {
  let timeout;
  return (...args) => { clearTimeout(timeout); timeout = setTimeout(() => fn(...args), wait); };
}

function tickClock() {
  const now = new Date();
  $("#current-time").textContent = now.toLocaleString("zh-CN", { month: "long", day: "numeric", weekday: "short", hour: "2-digit", minute: "2-digit" });
  $("#home-date").textContent = now.toLocaleDateString("zh-CN", { month: "long", day: "numeric", weekday: "long" });
  const hour = now.getHours();
  const greeting = hour < 6 ? "夜深了" : hour < 11 ? "早上好" : hour < 14 ? "中午好" : hour < 18 ? "下午好" : "晚上好";
  $("#home-greeting").textContent = `${greeting}，${ownerProfile().name}`;
}

async function init() {
  const localSettings = loadLocalSettings();
  applyAppearance(localSettings);
  renderInspectorContext("home");
  bindEvents(); syncFallbackKeyMode(); iconRefresh(); tickClock(); setInterval(tickClock, 30_000);
  const bootstrap = await loadBootstrap({ critical: true });
  if (!bootstrap) return;
  await finishStartup(localSettings);
}

let startupFinished = false;

async function finishStartup(localSettings = loadLocalSettings()) {
  if (startupFinished) return;
  await Promise.all([loadChatHistory(), loadNotifications()]);
  await loadDesktopPreferences();
  state.notificationTimer = setInterval(loadNotifications, 60_000);
  scheduleStatusRefresh(localSettings.status_refresh_seconds);
  setInspector(localSettings.inspector_open && window.innerWidth > 680);
  if (localSettings.default_view !== "home") setView(localSettings.default_view);
  startupFinished = true;
}

async function retryBootstrap() {
  const button = $("#retry-bootstrap");
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  $("#boot-error-message").textContent = "正在重新连接本地服务，请稍候。";
  try {
    const bootstrap = await loadBootstrap({ critical: true });
    if (bootstrap) await finishStartup();
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}

window.addEventListener("pywebviewready", () => {
  void loadDesktopPreferences();
  void syncNativeVoiceCallOverlay();
}, { once: true });
const systemThemeQuery = window.matchMedia?.("(prefers-color-scheme: dark)");
systemThemeQuery?.addEventListener("change", () => {
  if (loadLocalSettings().theme === "system") void syncNativeVoiceCallOverlay();
});
document.addEventListener("visibilitychange", () => {
  if (state.voiceCallActive) void keepVoiceCallAudioAlive();
});
window.addEventListener("resize", keepVoiceCallDockInView);
window.addEventListener("beforeunload", () => endVoiceCall({ silent: true }));
init();
