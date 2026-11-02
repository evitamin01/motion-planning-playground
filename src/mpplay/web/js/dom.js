// Tiny DOM helpers and an inline SVG icon set (no external assets, works offline).

const ICONS = {
  play: '<path d="M7 4.8v14.4L19 12z" fill="currentColor" stroke="none"/>',
  pause: '<rect x="6.5" y="5" width="3.6" height="14" rx="1" fill="currentColor" stroke="none"/><rect x="13.9" y="5" width="3.6" height="14" rx="1" fill="currentColor" stroke="none"/>',
  "step-forward": '<path d="M6 5.5v13l9-6.5z" fill="currentColor"/><path d="M18 5.5v13"/>',
  "step-back": '<path d="M18 5.5v13l-9-6.5z" fill="currentColor"/><path d="M6 5.5v13"/>',
  skip: '<path d="M4 6v12l7.5-6zM12.5 6v12L20 12z" fill="currentColor"/>',
  restart: '<path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1L3.5 8.5"/><path d="M3.5 3.5v5h5"/>',
  dice: '<rect x="3.5" y="3.5" width="17" height="17" rx="4"/><circle cx="8.5" cy="8.5" r="1.3" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.3" fill="currentColor" stroke="none"/><circle cx="15.5" cy="15.5" r="1.3" fill="currentColor" stroke="none"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
  redo: '<path d="m15 14 5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/>',
  upload: '<path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/><path d="M12 15V4M7.5 8.5 12 4l4.5 4.5"/>',
  download: '<path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/><path d="M12 4v11M7.5 10.5 12 15l4.5-4.5"/>',
  image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.6 9.4a2.5 2.5 0 1 1 3.4 2.4c-.6.3-1 .9-1 1.6v.5"/><circle cx="12" cy="17" r=".8" fill="currentColor" stroke="none"/>',
  contrast: '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17a8.5 8.5 0 0 0 0-17z" fill="currentColor"/>',
  github: '<path d="m8 7-5 5 5 5M16 7l5 5-5 5M13.5 4.5l-3 15"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
  copy: '<rect x="8.5" y="8.5" width="11.5" height="11.5" rx="2"/><path d="M15.5 8.5V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7.5a2 2 0 0 0 2 2h2.5"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
  fit: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
  gauge: '<path d="M4.5 17a8 8 0 1 1 15 0"/><path d="m12 15 3.5-4.5"/>',
  cursor: '<path d="m5.5 3.5 13 6.6-5.8 1.9-2 5.9z" fill="currentColor" fill-opacity=".15"/>',
  rect: '<rect x="4" y="6" width="16" height="12" rx="1.5" fill="currentColor" fill-opacity=".15"/>',
  circle: '<circle cx="12" cy="12" r="8" fill="currentColor" fill-opacity=".15"/>',
  polygon: '<path d="m12 3.5 8 6-3 10H7l-3-10z" fill="currentColor" fill-opacity=".15"/>',
  eraser: '<path d="M20 20H9l-4.6-4.6a2 2 0 0 1 0-2.8L13.2 3.8a2 2 0 0 1 2.8 0l4.2 4.2a2 2 0 0 1 0 2.8L11 20"/><path d="m8 10 6.5 6.5"/>',
  start: '<circle cx="12" cy="12" r="7.5"/><circle cx="12" cy="12" r="3" fill="currentColor" stroke="none"/>',
  goal: '<path d="M5.5 21V4M5.5 4.5h12l-2.5 4 2.5 4h-12" fill="currentColor" fill-opacity=".15"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  chevron: '<path d="m9 6 6 6-6 6"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><circle cx="12" cy="7.8" r=".8" fill="currentColor" stroke="none"/>',
};

export function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = ICONS[name] || "";
  return svg;
}

/** Replace the contents of every `[data-icon]` placeholder with its SVG icon. */
export function hydrateIcons(root = document) {
  for (const el of root.querySelectorAll("[data-icon]")) {
    if (el.querySelector("svg.icon")) continue;
    el.prepend(icon(el.dataset.icon));
  }
}

export function setIcon(el, name) {
  el.dataset.icon = name;
  el.querySelector("svg.icon")?.remove();
  el.prepend(icon(name));
}

/** Hyperscript: h("div", {class: "x", onclick: fn}, child, "text", ...) */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith("on") && typeof value === "function") {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === "class") {
      el.className = value;
    } else if (key === "style" && typeof value === "object") {
      Object.assign(el.style, value);
    } else if (key === "dataset") {
      Object.assign(el.dataset, value);
    } else if (key in el && typeof value !== "string") {
      el[key] = value;
    } else {
      el.setAttribute(key, value === true ? "" : value);
    }
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

export function toast(message, kind = "info", timeout = 3500) {
  const stack = document.getElementById("toasts");
  const el = h("div", { class: `toast ${kind}`, role: kind === "error" ? "alert" : "status" }, message);
  stack.append(el);
  setTimeout(() => el.remove(), timeout);
}

export function downloadText(filename, text, type = "application/json") {
  downloadBlob(filename, new Blob([text], { type }));
}

export function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const a = h("a", { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Format a number compactly for tables. */
export function fmt(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  if (typeof value !== "number") return String(value);
  if (Number.isInteger(value) && Math.abs(value) >= 1000) return value.toLocaleString("en-US");
  if (Number.isInteger(value)) return String(value);
  const abs = Math.abs(value);
  if (abs >= 1000) return Math.round(value).toLocaleString("en-US");
  if (abs >= 100) return value.toFixed(Math.min(digits, 1));
  return value.toFixed(digits);
}

/** True if a keyboard event originates from a text-entry element. */
export function isTyping(event) {
  const t = event.target;
  if (!(t instanceof HTMLElement)) return false;
  if (t.isContentEditable) return true;
  if (t.tagName === "TEXTAREA" || t.tagName === "SELECT") return true;
  if (t.tagName === "INPUT") {
    return !["checkbox", "radio", "range", "button"].includes(t.type);
  }
  return false;
}

export function debounce(fn, ms) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}
