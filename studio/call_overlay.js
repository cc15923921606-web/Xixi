function refreshIcons() {
  if (window.lucide) window.lucide.createIcons({ attrs: { "stroke-width": 1.8 } });
}

let overlayCollapsed = false;
let overlayTransitionTarget = null;
let overlayTransitionTimer = 0;
let opacitySyncFrame = 0;
let currentAssistantName = "昔夕";
const overlayTransitionDuration = 300;
const overlayThemeKeys = new Set([
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
]);

function applyOverlayTheme(theme = {}) {
  const root = document.documentElement;
  overlayThemeKeys.forEach((key) => root.style.removeProperty(`--${key}`));
  Object.entries(theme).forEach(([key, value]) => {
    const color = String(value || "").trim();
    if (!overlayThemeKeys.has(key) || !color || !CSS.supports("color", color)) return;
    root.style.setProperty(`--${key}`, color);
  });
  root.style.colorScheme = theme.colorScheme === "dark" ? "dark" : "light";
}

function renderOverlayOpacity(value) {
  const opacity = Math.max(0.45, Math.min(1, Number(value) || 1));
  const percent = Math.round(opacity * 100);
  const slider = document.querySelector("#overlay-opacity");
  const output = document.querySelector("#overlay-opacity-value");
  if (slider && Number(slider.value) !== percent) slider.value = String(percent);
  if (output) output.textContent = `${percent}%`;
}

function setOverlaySettingsOpen(open) {
  const panel = document.querySelector("#overlay-settings");
  const trigger = document.querySelector("#overlay-settings-trigger");
  const visible = Boolean(open) && !overlayCollapsed;
  panel.hidden = !visible;
  trigger.setAttribute("aria-expanded", String(visible));
}

function finishOverlayTransition(collapsed) {
  window.clearTimeout(overlayTransitionTimer);
  overlayTransitionTimer = 0;
  overlayCollapsed = Boolean(collapsed);
  overlayTransitionTarget = null;
  document.body.classList.remove(
    "overlay-transitioning",
    "overlay-transition-active",
    "overlay-collapsing",
    "overlay-expanding",
  );
  document.body.classList.toggle("overlay-collapsed", overlayCollapsed);
  const avatar = document.querySelector("#overlay-avatar");
  const label = overlayCollapsed ? "展开通话小窗" : `返回${currentAssistantName}应用`;
  avatar.title = label;
  avatar.setAttribute("aria-label", label);
}

function animateOverlayTransition(collapsed) {
  if (overlayTransitionTarget === Boolean(collapsed)) return;
  window.clearTimeout(overlayTransitionTimer);
  overlayTransitionTarget = Boolean(collapsed);
  document.body.classList.remove(
    "overlay-transition-active",
    "overlay-collapsing",
    "overlay-expanding",
  );
  document.body.classList.add(
    "overlay-transitioning",
    collapsed ? "overlay-collapsing" : "overlay-expanding",
  );
  if (!collapsed) document.body.classList.remove("overlay-collapsed");
  requestAnimationFrame(() => requestAnimationFrame(() => {
    document.body.classList.add("overlay-transition-active");
  }));
  overlayTransitionTimer = window.setTimeout(
    () => finishOverlayTransition(collapsed),
    overlayTransitionDuration,
  );
}

window.setCallOverlayCollapsed = function setCallOverlayCollapsed(collapsed) {
  if (overlayTransitionTarget !== null) return;
  overlayCollapsed = Boolean(collapsed);
  document.body.classList.toggle("overlay-collapsed", overlayCollapsed);
  const avatar = document.querySelector("#overlay-avatar");
  const label = overlayCollapsed ? "展开通话小窗" : `返回${currentAssistantName}应用`;
  avatar.title = label;
  avatar.setAttribute("aria-label", label);
};

window.expandCallOverlayFromNative = function expandCallOverlayFromNative() {
  animateOverlayTransition(false);
};

function renderTranscript(entries) {
  const host = document.querySelector("#overlay-transcript");
  host.replaceChildren();
  const items = Array.isArray(entries) ? entries.slice(-6) : [];
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "call-overlay-empty";
    empty.textContent = "等待你开口";
    host.append(empty);
    return;
  }
  items.forEach((item) => {
    const role = item?.role === "user" ? "user" : "assistant";
    const line = document.createElement("div");
    line.className = `call-overlay-line ${role}`;
    const speaker = document.createElement("span");
    speaker.textContent = role === "user" ? "你" : currentAssistantName;
    const content = document.createElement("p");
    content.textContent = String(item?.text || "").slice(0, 240);
    line.append(speaker, content);
    host.append(line);
  });
  host.scrollTop = host.scrollHeight;
}

window.updateCallOverlay = function updateCallOverlay(payload = {}) {
  currentAssistantName = String(payload.assistant_name || "昔夕").replace(/\s+/g, " ").trim() || "昔夕";
  const status = String(payload.status || "通话中");
  const duration = String(payload.duration || "00:00");
  applyOverlayTheme(payload.theme);
  renderOverlayOpacity(payload.opacity);
  document.title = `${currentAssistantName}通话`;
  document.querySelector("#overlay-name").textContent = currentAssistantName;
  document.querySelector("#overlay-status").textContent = `${status} · ${duration}`;
  renderTranscript(payload.entries);
  window.setCallOverlayCollapsed(payload.collapsed);
};

async function invokeNative(action, ...args) {
  const api = window.pywebview?.api;
  if (typeof api?.[action] !== "function") return null;
  try { return await api[action](...args); } catch (error) { console.error(`call overlay ${action} failed`, error); return null; }
}

const overlayAvatar = document.querySelector("#overlay-avatar");
overlayAvatar.addEventListener("click", () => {
  if (overlayCollapsed) {
    animateOverlayTransition(false);
    invokeNative("expand");
  } else {
    invokeNative("restore");
  }
});
document.querySelector("#overlay-hide").addEventListener("click", () => {
  animateOverlayTransition(true);
  invokeNative("collapse");
});
document.querySelector("#overlay-hangup").addEventListener("click", () => invokeNative("hangup"));
const settingsTrigger = document.querySelector("#overlay-settings-trigger");
const settingsPanel = document.querySelector("#overlay-settings");
const opacitySlider = document.querySelector("#overlay-opacity");
settingsTrigger.addEventListener("click", (event) => {
  event.stopPropagation();
  setOverlaySettingsOpen(settingsPanel.hidden);
});
settingsPanel.addEventListener("click", (event) => event.stopPropagation());
opacitySlider.addEventListener("input", () => {
  const opacity = Number(opacitySlider.value) / 100;
  renderOverlayOpacity(opacity);
  cancelAnimationFrame(opacitySyncFrame);
  opacitySyncFrame = requestAnimationFrame(() => invokeNative("set_opacity", opacity));
});
document.addEventListener("click", () => setOverlaySettingsOpen(false));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") setOverlaySettingsOpen(false);
});
document.querySelectorAll("[data-resize-edge]").forEach((handle) => {
  handle.addEventListener("mousedown", (event) => {
    if (event.button !== 0 || overlayCollapsed) return;
    event.preventDefault();
    setOverlaySettingsOpen(false);
    invokeNative("resize", handle.dataset.resizeEdge);
  });
});
window.addEventListener("pywebviewready", async () => {
  try {
    const state = await window.pywebview.api.get_state();
    window.updateCallOverlay(state);
  } catch (error) {
    console.error("could not load call overlay state", error);
  }
}, { once: true });
refreshIcons();
