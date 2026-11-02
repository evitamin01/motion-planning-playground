// Forms generated from parameter schemas served by the API (see mpplay/params.py).

import { h } from "../dom.js";

let uid = 0;

function useLogScale(spec) {
  return spec.min > 0 && spec.max / spec.min >= 100;
}

function toSlider(spec, value) {
  if (!useLogScale(spec)) return value;
  const lo = Math.log(spec.min);
  const hi = Math.log(spec.max);
  return ((Math.log(Math.max(value, spec.min)) - lo) / (hi - lo)) * 1000;
}

function fromSlider(spec, pos) {
  if (!useLogScale(spec)) return Number(pos);
  const lo = Math.log(spec.min);
  const hi = Math.log(spec.max);
  return Math.exp(lo + (Number(pos) / 1000) * (hi - lo));
}

function niceRound(spec, value) {
  if (spec.type === "int") return Math.round(value);
  const step = spec.step || 0.01;
  const decimals = Math.max(0, -Math.floor(Math.log10(step)));
  return Number(value.toFixed(decimals));
}

/**
 * One labelled control for a parameter spec.
 * `onChange(value, {transient})` fires on every edit; transient is true while a slider is dragged.
 */
export function paramField(spec, value, onChange) {
  const id = `param-${++uid}`;
  const label = h("label", { for: id, title: spec.help || spec.label }, spec.label);
  let control;

  if (spec.type === "bool") {
    const input = h("input", { type: "checkbox", id, checked: !!value });
    input.addEventListener("change", () => onChange(input.checked, { transient: false }));
    control = h("label", { class: "switch", title: spec.help }, input, h("span", { class: "switch-track" }));
  } else if (spec.type === "choice") {
    control = h(
      "select",
      { id, title: spec.help },
      spec.choices.map((c) => h("option", { value: c, selected: c === String(value) }, c)),
    );
    control.addEventListener("change", () => onChange(control.value, { transient: false }));
  } else {
    const number = h("input", {
      type: "number",
      id,
      value,
      step: spec.step ?? (spec.type === "int" ? 1 : "any"),
      min: spec.min,
      max: spec.max,
      title: spec.help,
    });
    let slider = null;
    const commit = (raw, transient) => {
      let v = Number(raw);
      if (!Number.isFinite(v)) v = spec.default;
      if (spec.min !== undefined) v = Math.max(spec.min, v);
      if (spec.max !== undefined) v = Math.min(spec.max, v);
      v = niceRound(spec, v);
      number.value = v;
      if (slider) slider.value = toSlider(spec, v);
      onChange(v, { transient });
    };
    if (spec.min !== undefined && spec.max !== undefined) {
      const log = useLogScale(spec);
      slider = h("input", {
        type: "range",
        min: log ? 0 : spec.min,
        max: log ? 1000 : spec.max,
        step: log ? 1 : spec.step ?? (spec.type === "int" ? 1 : (spec.max - spec.min) / 100),
        value: toSlider(spec, value),
        "aria-label": spec.label,
      });
      slider.addEventListener("input", () => commit(fromSlider(spec, slider.value), true));
      slider.addEventListener("change", () => commit(fromSlider(spec, slider.value), false));
    }
    number.addEventListener("change", () => commit(number.value, false));
    control = h("div", { class: "param-control" }, slider, number);
  }
  return [label, control];
}

/** Grid of fields; advanced parameters go into a collapsible section. */
export function paramForm(schema, values, onChange) {
  const basic = h("div", { class: "form-grid" });
  const advancedGrid = h("div", { class: "form-grid" });
  for (const spec of schema) {
    const value = values[spec.name] ?? spec.default;
    const fields = paramField(spec, value, (v, opts) => onChange(spec.name, v, opts));
    (spec.advanced ? advancedGrid : basic).append(...fields);
  }
  const out = [basic];
  if (advancedGrid.childElementCount) {
    out.push(h("details", { class: "run-advanced" }, h("summary", {}, "Advanced"), advancedGrid));
  }
  return out;
}

/** Plain numeric input bound to a value. */
export function numberInput(value, onCommit, attrs = {}) {
  const input = h("input", { type: "number", value, step: "any", ...attrs });
  input.addEventListener("change", () => {
    const v = Number(input.value);
    if (Number.isFinite(v)) onCommit(v);
  });
  return input;
}
