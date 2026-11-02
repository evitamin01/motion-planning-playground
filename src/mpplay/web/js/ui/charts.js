// Minimal dependency-free SVG charts.

import { fmt, h } from "../dom.js";

const NS = "http://www.w3.org/2000/svg";

function s(tag, attrs = {}, ...children) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v !== undefined && v !== null) el.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

function niceMax(v) {
  if (!(v > 0)) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

function ellipsize(text, max) {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/**
 * Horizontal bar chart.
 * rows: [{label, color, value (number|null), error?, note?}]
 */
export function barChart({ title, unit = "", rows, lowerIsBetter = true }) {
  const W = 340;
  const rowH = 22;
  const labelW = 112;
  const valueW = 64;
  const H = rows.length * rowH + 6;
  const valid = rows.filter((r) => r.value !== null && r.value !== undefined);
  const values = valid.map((r) => r.value);
  const max = niceMax(Math.max(...valid.map((r) => r.value + (r.error || 0)), 0));
  const best = values.length ? (lowerIsBetter ? Math.min(...values) : Math.max(...values)) : null;
  const plotW = W - labelW - valueW;
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": title });
  rows.forEach((r, i) => {
    const y = i * rowH + 3;
    svg.append(
      s("text", { x: 0, y: y + rowH / 2 + 1, "dominant-baseline": "middle" }, ellipsize(r.label, 17)),
    );
    if (r.value === null || r.value === undefined) {
      svg.append(
        s(
          "text",
          { x: labelW, y: y + rowH / 2 + 1, "dominant-baseline": "middle", "font-style": "italic" },
          r.note || "failed",
        ),
      );
      return;
    }
    const w = Math.max((r.value / max) * plotW, 1.5);
    svg.append(s("rect", { x: labelW, y: y + 3, width: w, height: rowH - 8, rx: 3, fill: r.color, opacity: 0.85 }));
    if (r.error) {
      const x0 = labelW + (Math.max(r.value - r.error, 0) / max) * plotW;
      const x1 = labelW + ((r.value + r.error) / max) * plotW;
      const cy = y + rowH / 2 - 1;
      svg.append(
        s("path", {
          d: `M${x0},${cy}H${x1}M${x0},${cy - 4}V${cy + 4}M${x1},${cy - 4}V${cy + 4}`,
          stroke: "currentColor",
          "stroke-width": 1.2,
          class: "axis",
          fill: "none",
        }),
      );
    }
    const isBest = values.length > 1 && r.value === best;
    svg.append(
      s(
        "text",
        {
          x: W,
          y: y + rowH / 2 + 1,
          "text-anchor": "end",
          "dominant-baseline": "middle",
          "font-weight": isBest ? 700 : 400,
        },
        fmt(r.value),
      ),
    );
  });
  return h("div", { class: "chart" }, h("h4", {}, title, h("span", {}, unit)), svg);
}

/**
 * Line chart for convergence curves (step interpolation).
 * series: [{label, color, points: [[x, y], ...]}]; refs: [{label, color, value}]
 */
export function lineChart({ title, series, refs = [], xLabel = "", yLabel = "" }) {
  const W = 340;
  const H = 190;
  const m = { l: 44, r: 10, t: 8, b: 30 };
  const xs = series.flatMap((sr) => sr.points.map((p) => p[0]));
  const ys = [...series.flatMap((sr) => sr.points.map((p) => p[1])), ...refs.map((r) => r.value)];
  const xmax = Math.max(...xs, 1);
  let ymin = Math.min(...ys);
  let ymax = Math.max(...ys);
  const pad = (ymax - ymin) * 0.08 || ymax * 0.05 || 1;
  ymin = Math.max(0, ymin - pad);
  ymax += pad;
  const X = (x) => m.l + (x / xmax) * (W - m.l - m.r);
  const Y = (y) => H - m.b - ((y - ymin) / (ymax - ymin)) * (H - m.t - m.b);
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": title });

  for (let k = 0; k <= 4; k++) {
    const yv = ymin + ((ymax - ymin) * k) / 4;
    svg.append(s("line", { x1: m.l, x2: W - m.r, y1: Y(yv), y2: Y(yv), class: "gridline" }));
    svg.append(s("text", { x: m.l - 6, y: Y(yv), "text-anchor": "end", "dominant-baseline": "middle" }, fmt(yv, 1)));
  }
  for (let k = 0; k <= 4; k++) {
    const xv = (xmax * k) / 4;
    svg.append(s("text", { x: X(xv), y: H - m.b + 14, "text-anchor": "middle" }, fmt(Math.round(xv))));
  }
  svg.append(s("text", { x: (m.l + W - m.r) / 2, y: H - 2, "text-anchor": "middle" }, xLabel));
  svg.append(
    s("text", { x: 10, y: (m.t + H - m.b) / 2, transform: `rotate(-90 10 ${(m.t + H - m.b) / 2})`, "text-anchor": "middle" }, yLabel),
  );

  for (const ref of refs) {
    svg.append(
      s("line", {
        x1: m.l,
        x2: W - m.r,
        y1: Y(ref.value),
        y2: Y(ref.value),
        stroke: ref.color,
        "stroke-dasharray": "4 4",
        "stroke-width": 1.2,
      }),
    );
    svg.append(s("text", { x: W - m.r - 2, y: Y(ref.value) - 4, "text-anchor": "end" }, ref.label));
  }
  for (const sr of series) {
    if (!sr.points.length) continue;
    let d = `M${X(sr.points[0][0])},${Y(sr.points[0][1])}`;
    for (let i = 1; i < sr.points.length; i++) {
      d += `H${X(sr.points[i][0])}V${Y(sr.points[i][1])}`;
    }
    svg.append(s("path", { d, fill: "none", stroke: sr.color, "stroke-width": 2, "stroke-linejoin": "round" }));
    svg.append(s("circle", { cx: X(sr.points[0][0]), cy: Y(sr.points[0][1]), r: 3, fill: sr.color }));
  }
  const legend = h(
    "div",
    { class: "note" },
    series.map((sr) => h("span", { class: "tag", style: { borderLeft: `3px solid ${sr.color}` } }, sr.label)),
  );
  return h("div", { class: "chart" }, h("h4", {}, title), svg, legend);
}
