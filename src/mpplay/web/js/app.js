// Application controller: owns the state and coordinates the UI modules.

import { api } from "./api.js";
import { Camera } from "./camera.js";
import { debounce, downloadBlob, downloadText, h, hydrateIcons, isTyping, toast } from "./dom.js";
import { Editor, TOOLS } from "./editor.js";
import { roundShape, translate } from "./geometry.js";
import { Playbar, Player } from "./playback.js";
import { themeColors } from "./renderer.js";
import { TraceState } from "./trace.js";
import { BenchmarkPanel } from "./ui/benchmark.js";
import { GenerateDialog, HelpDialog } from "./ui/dialogs.js";
import { EnvPanel } from "./ui/envpanel.js";
import { LearnPanel } from "./ui/learn.js";
import { ChartsPanel, MetricsPanel } from "./ui/results.js";
import { RunsPanel } from "./ui/runs.js";
import { Views } from "./views.js";

const STORAGE_KEY = "mpplay:state:v1";
const THEME_KEY = "mpplay:theme";
const MAX_UNDO = 100;

// Run colors for light and dark themes (distinct from the green start / red goal markers).
const PALETTE = {
  light: ["#2563eb", "#ea580c", "#7c3aed", "#0d9488", "#db2777", "#ca8a04", "#0891b2", "#4d7c0f"],
  dark: ["#60a5fa", "#fb923c", "#a78bfa", "#2dd4bf", "#f472b6", "#facc15", "#22d3ee", "#a3e635"],
};

const DEFAULT_RUNS = ["astar", "dijkstra", "rrt_star", "prm"];
const PREFERRED_ORDER = ["astar", "rrt_star", "dijkstra", "rrt_connect", "prm", "theta_star", "rrt", "informed_rrt_star", "greedy", "bfs", "potential_field"];

export const LAYERS = [
  ["exploration", "Search progress", "Explored cells, trees, roadmaps and samples"],
  ["occupancy", "Grid discretization", "Cells blocked for grid planners (conservative)"],
  ["gridLines", "Grid lines", "Cell boundaries when zoomed in"],
  ["cspace", "Configuration space", "Obstacles grown by the robot radius"],
  ["heatmap", "Potential field", "Heatmap of the potential (Potential Field planner)"],
  ["rawPath", "Unsmoothed path", "Path before shortcut smoothing"],
];

const DEFAULT_LAYERS = { exploration: true, occupancy: false, gridLines: false, cspace: true, heatmap: true, rawPath: true };

function clone(v) {
  return JSON.parse(JSON.stringify(v));
}

function validateEnv(env) {
  const pt = (p) => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite);
  if (!env || !Array.isArray(env.bounds) || env.bounds.length !== 4 || !env.bounds.every(Number.isFinite)) {
    throw new Error("environment needs numeric 'bounds' [xmin, ymin, xmax, ymax]");
  }
  if (!pt(env.start) || !pt(env.goal)) throw new Error("environment needs 'start' and 'goal' points");
  if (!Array.isArray(env.obstacles || [])) throw new Error("'obstacles' must be a list");
  return {
    version: 1,
    name: "Untitled",
    description: "",
    robot_radius: 0,
    resolution: 1,
    obstacles: [],
    ...env,
  };
}

export class App {
  constructor() {
    this.bus = new EventTarget();
    this.catalog = { planners: [], scenarios: [], generators: [], metrics: [], version: "" };
    this.env = null;
    this.scenario = null;
    this.runs = [];
    this.nextRunId = 1;
    this.results = new Map();
    this.states = new Map();
    this.pending = new Set();
    this.seed = 1;
    this.live = false;
    this.tool = "select";
    this.selection = null;
    this.viewMode = "split";
    this.focus = null;
    this.layers = { ...DEFAULT_LAYERS };
    this.tab = "metrics";
    this.undoStack = [];
    this.redoStack = [];
    this.editSnapshot = null;
    this.camera = new Camera();
    this.editor = new Editor(this);
    this.player = new Player(this);
    this.planSeq = 0;
    this.liveBusy = false;
    this.liveAgain = false;
    this.frameRequested = false;
    this.persist = debounce(() => this.save(), 300);
  }

  on(type, fn) {
    this.bus.addEventListener(type, fn);
  }

  emit(type, detail = {}) {
    this.bus.dispatchEvent(new CustomEvent(type, { detail }));
  }

  // ------------------------------------------------------------------ startup

  async init() {
    hydrateIcons();
    try {
      const [info, planners, scenarios, generators] = await Promise.all([
        api.info(),
        api.planners(),
        api.scenarios(),
        api.generators(),
      ]);
      Object.assign(this.catalog, { planners, scenarios, generators, metrics: info.metrics, version: info.version });
    } catch (err) {
      const views = document.getElementById("views");
      views.append(h("div", { class: "empty" }, h("strong", {}, "Cannot connect to the planning server"), err.message));
      return;
    }
    document.getElementById("version").textContent = `v${this.catalog.version}`;
    const firstVisit = !this.restore();
    const urlOptions = this.applyUrlParams();

    this.views = new Views(this, document.getElementById("views"));
    this.playbar = new Playbar(this, this.player);
    this.envPanel = new EnvPanel(this);
    this.runsPanel = new RunsPanel(this);
    this.metricsPanel = new MetricsPanel(this);
    this.chartsPanel = new ChartsPanel(this);
    this.benchmarkPanel = new BenchmarkPanel(this);
    this.learnPanel = new LearnPanel(this);
    this.generateDialog = new GenerateDialog(this);
    this.helpDialog = new HelpDialog(this);
    this.bindChrome();

    this.envPanel.render();
    this.runsPanel.render();
    this.metricsPanel.render();
    this.chartsPanel.render();
    this.benchmarkPanel.render();
    this.learnPanel.render();
    this.views.layout();
    this.updateChrome();
    if (urlOptions?.plan) {
      await this.planAll({ animate: urlOptions.at === null });
      if (urlOptions.at !== null) {
        this.player.pause();
        this.player.seek(Math.round(urlOptions.at * this.player.total));
      }
    } else if (firstVisit) {
      toast("Welcome! Press Plan (or Enter) to watch the planners search. Press ? for help.", "info", 6000);
    }
    if (this.live) this.scheduleLive();
  }

  /**
   * Optional URL parameters (handy for demos, docs and links):
   * ?scenario=maze&planners=astar,rrt_star&mode=overlay&seed=3&theme=dark&tab=charts&plan&at=0.5
   * `plan` runs the planners on load; `at` (0..1) pauses the animation at that fraction.
   */
  applyUrlParams() {
    const q = new URLSearchParams(window.location.search);
    if (![...q.keys()].length) return null;
    const scenario = this.catalog.scenarios.find((s) => s.name === q.get("scenario"));
    if (scenario) {
      this.env = clone(scenario.environment);
      this.scenario = scenario.name;
    }
    const planners = (q.get("planners") || "").split(",").filter((p) => this.plannerInfo(p));
    if (planners.length) {
      this.runs = [];
      for (const name of planners) this.addRun(name, { silent: true });
    }
    if (["split", "overlay"].includes(q.get("mode"))) this.viewMode = q.get("mode");
    if (["light", "dark"].includes(q.get("theme"))) document.documentElement.dataset.theme = q.get("theme");
    if (["metrics", "charts", "benchmark", "learn"].includes(q.get("tab"))) this.tab = q.get("tab");
    const seed = Number(q.get("seed"));
    if (q.has("seed") && Number.isInteger(seed) && seed >= 0) this.seed = seed;
    const at = Number(q.get("at"));
    return { plan: q.has("plan"), at: q.has("at") && Number.isFinite(at) ? Math.min(Math.max(at, 0), 1) : null };
  }

  defaultState() {
    const scenario = this.catalog.scenarios[0];
    this.env = clone(scenario.environment);
    this.scenario = scenario.name;
    this.runs = [];
    for (const name of DEFAULT_RUNS) if (this.plannerInfo(name)) this.addRun(name, { silent: true });
  }

  restore() {
    let data = null;
    try {
      data = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    } catch {
      data = null;
    }
    if (!data) {
      this.defaultState();
      return false;
    }
    try {
      this.env = validateEnv(data.env);
      this.scenario = data.scenario ?? null;
      this.runs = (data.runs || [])
        .filter((r) => this.plannerInfo(r.planner))
        .map((r) => ({ planner: r.planner, params: r.params || {}, smoothing: !!r.smoothing, enabled: r.enabled !== false, colorIndex: r.colorIndex ?? 0, id: this.nextRunId++ }));
      this.seed = Number.isFinite(data.seed) ? data.seed : 1;
      this.live = !!data.live;
      this.viewMode = data.viewMode === "overlay" ? "overlay" : "split";
      this.layers = { ...DEFAULT_LAYERS, ...(data.layers || {}) };
      this.tab = data.tab || "metrics";
      if (data.speed) this.player.speed = data.speed;
      if (data.sync) this.player.sync = data.sync;
    } catch {
      this.defaultState();
      return false;
    }
    return true;
  }

  save() {
    const data = {
      env: this.env,
      scenario: this.scenario,
      runs: this.runs.map(({ planner, params, smoothing, enabled, colorIndex }) => ({ planner, params, smoothing, enabled, colorIndex })),
      seed: this.seed,
      live: this.live,
      viewMode: this.viewMode,
      layers: this.layers,
      tab: this.tab,
      speed: this.player.speed,
      sync: this.player.sync,
    };
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch {
      /* storage unavailable (private mode); state simply is not remembered */
    }
  }

  // ------------------------------------------------------------------ catalog helpers

  plannerInfo(name) {
    return this.catalog.planners.find((p) => p.name === name) || null;
  }

  runById(id) {
    return this.runs.find((r) => r.id === id) || null;
  }

  runTitle(run) {
    const info = this.plannerInfo(run.planner);
    const label = info ? info.label : run.planner;
    const same = this.runs.filter((r) => r.planner === run.planner);
    return same.length > 1 ? `${label} #${same.indexOf(run) + 1}` : label;
  }

  isDark() {
    const t = document.documentElement.dataset.theme;
    if (t === "dark") return true;
    if (t === "light") return false;
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  colorOf(run, variant = 0) {
    const palette = this.isDark() ? PALETTE.dark : PALETTE.light;
    return palette[(run.colorIndex + variant * 3) % palette.length];
  }

  focusRunId() {
    const withResult = this.runs.filter((r) => r.enabled && this.results.has(r.id));
    if (withResult.some((r) => r.id === this.focus)) return this.focus;
    return (withResult[0] || this.runs.find((r) => r.enabled))?.id ?? null;
  }

  setFocus(id) {
    this.focus = id;
    this.views.updateLabels();
    this.requestRender();
  }

  // ------------------------------------------------------------------ rendering

  requestRender() {
    if (this.frameRequested || !this.views) return;
    this.frameRequested = true;
    requestAnimationFrame((ts) => this.frame(ts));
  }

  frame(ts) {
    this.frameRequested = false;
    this.player.tick(ts);
    this.views.render();
    this.playbar.update();
    if (this.player.playing) this.requestRender();
  }

  // ------------------------------------------------------------------ environment editing

  setEnv(env, { scenario = null, record = true } = {}) {
    let next;
    try {
      next = validateEnv(clone(env));
    } catch (err) {
      toast(`Invalid environment: ${err.message}`, "error");
      return;
    }
    if (record) this.pushUndo();
    const boundsChanged = !this.env || JSON.stringify(this.env.bounds) !== JSON.stringify(next.bounds);
    this.env = next;
    this.scenario = scenario;
    this.selection = null;
    this.editor.cancel();
    if (boundsChanged) this.camera.fit();
    this.envChanged(false);
    this.emit("selection");
  }

  patchEnv(patch) {
    const env = { ...this.env, ...patch };
    const [xmin, ymin, xmax, ymax] = env.bounds;
    const clampPt = (p) => [Math.min(Math.max(p[0], xmin), xmax), Math.min(Math.max(p[1], ymin), ymax)];
    env.start = clampPt(env.start);
    env.goal = clampPt(env.goal);
    this.setEnv(env, { scenario: null });
  }

  pushUndo(snapshot = JSON.stringify(this.env)) {
    if (!this.env) return;
    this.undoStack.push(snapshot);
    if (this.undoStack.length > MAX_UNDO) this.undoStack.shift();
    this.redoStack = [];
  }

  beginEdit() {
    if (this.editSnapshot === null) this.editSnapshot = JSON.stringify(this.env);
  }

  previewEnv(env) {
    this.env = env;
    this.envChanged(true);
  }

  commitEdit() {
    const snapshot = this.editSnapshot;
    this.editSnapshot = null;
    if (snapshot !== null && snapshot !== JSON.stringify(this.env)) {
      this.pushUndo(snapshot);
      this.scenario = null;
    }
    this.envChanged(false);
  }

  cancelEdit() {
    if (this.editSnapshot !== null) this.env = JSON.parse(this.editSnapshot);
    this.editSnapshot = null;
    this.envChanged(false);
  }

  envChanged(transient) {
    if (this.live) this.scheduleLive();
    else if (this.results.size || this.pending.size) this.clearResults();
    this.emit("env", { transient });
    if (!transient) {
      this.persist();
      this.updateChrome();
      this.views?.arrange();
    }
    this.requestRender();
  }

  undo() {
    if (!this.undoStack.length) return;
    this.redoStack.push(JSON.stringify(this.env));
    this.restoreSnapshot(this.undoStack.pop());
  }

  redo() {
    if (!this.redoStack.length) return;
    this.undoStack.push(JSON.stringify(this.env));
    this.restoreSnapshot(this.redoStack.pop());
  }

  restoreSnapshot(snapshot) {
    const env = JSON.parse(snapshot);
    if (JSON.stringify(env.bounds) !== JSON.stringify(this.env.bounds)) this.camera.fit();
    this.env = env;
    this.scenario = null;
    this.selection = null;
    this.envChanged(false);
    this.emit("selection");
  }

  updateObstacle(index, shape) {
    this.beginEdit();
    const obstacles = this.env.obstacles.slice();
    obstacles[index] = roundShape(shape);
    this.previewEnv({ ...this.env, obstacles });
    this.commitEdit();
  }

  select(index) {
    if (this.selection === index) return;
    this.selection = index;
    this.emit("selection");
    this.requestRender();
  }

  deleteSelection() {
    if (this.selection === null) return;
    const obstacles = this.env.obstacles.filter((_, i) => i !== this.selection);
    this.beginEdit();
    this.selection = null;
    this.previewEnv({ ...this.env, obstacles });
    this.commitEdit();
    this.emit("selection");
  }

  duplicateSelection() {
    if (this.selection === null) return;
    const copy = roundShape(translate(this.env.obstacles[this.selection], 2, -2));
    this.beginEdit();
    this.previewEnv({ ...this.env, obstacles: [...this.env.obstacles, copy] });
    this.commitEdit();
    this.select(this.env.obstacles.length - 1);
  }

  clearObstacles() {
    this.setEnv({ ...this.env, obstacles: [] });
  }

  setTool(id) {
    this.editor.cancel();
    this.tool = id;
    this.emit("tool");
    this.requestRender();
  }

  // ------------------------------------------------------------------ runs

  addRun(planner = null, { silent = false, params = {}, smoothing = false } = {}) {
    if (!planner) {
      const used = new Set(this.runs.map((r) => r.planner));
      planner = PREFERRED_ORDER.find((p) => !used.has(p) && this.plannerInfo(p)) || this.catalog.planners[0].name;
    }
    const usedColors = new Set(this.runs.map((r) => r.colorIndex));
    let colorIndex = 0;
    while (usedColors.has(colorIndex) && colorIndex < PALETTE.light.length) colorIndex++;
    if (colorIndex >= PALETTE.light.length) colorIndex = this.runs.length % PALETTE.light.length;
    const run = { id: this.nextRunId++, planner, params: { ...params }, smoothing, enabled: true, colorIndex };
    this.runs.push(run);
    if (!silent) this.runsChanged();
    return run;
  }

  duplicateRun(id) {
    const run = this.runById(id);
    if (!run) return;
    const copy = this.addRun(run.planner, { silent: true, params: clone(run.params), smoothing: run.smoothing });
    this.runs.splice(this.runs.indexOf(copy), 1);
    this.runs.splice(this.runs.indexOf(run) + 1, 0, copy);
    this.runsChanged();
  }

  removeRun(id) {
    this.runs = this.runs.filter((r) => r.id !== id);
    this.invalidateRun(id);
    this.runsChanged();
  }

  updateRun(id, patch, { rerender = true } = {}) {
    const run = this.runById(id);
    if (!run) return;
    Object.assign(run, patch);
    this.invalidateRun(id);
    if (rerender) this.runsChanged();
    else {
      this.persist();
      this.emit("results");
      this.views.updateLabels();
    }
    if (this.live) this.scheduleLive();
  }

  setRunParam(id, name, value, { transient = false } = {}) {
    const run = this.runById(id);
    const spec = this.plannerInfo(run?.planner)?.params.find((p) => p.name === name);
    if (!run || !spec) return;
    if (value === spec.default) delete run.params[name];
    else run.params[name] = value;
    this.invalidateRun(id);
    this.emit("results");
    this.views.updateLabels();
    if (!transient) this.persist();
    if (this.live) this.scheduleLive();
    this.requestRender();
  }

  runsChanged() {
    this.persist();
    this.emit("runs");
    this.views?.layout();
    this.requestRender();
  }

  invalidateRun(id) {
    this.results.delete(id);
    this.states.delete(id);
    this.player.total = Math.max(0, ...[...this.states.values()].map((s) => s.numSteps));
    this.player.t = Math.min(this.player.t, this.player.total);
  }

  clearResults() {
    this.planSeq++;
    this.results.clear();
    this.states.clear();
    this.pending.clear();
    this.player.reset(false);
    this.emit("results");
    this.views?.updateLabels();
  }

  // ------------------------------------------------------------------ planning

  async planAll({ animate = true } = {}) {
    const runs = this.runs.filter((r) => r.enabled);
    if (!runs.length) {
      toast("Add or enable at least one planner first.", "error");
      return;
    }
    const seq = ++this.planSeq;
    const env = this.env;
    const button = document.getElementById("btn-plan");
    if (animate) button.classList.add("busy");
    for (const r of runs) this.pending.add(r.id);
    this.views.updateLabels();
    this.emit("results");
    const errors = [];
    await Promise.all(
      runs.map(async (run) => {
        try {
          const result = await api.plan({
            environment: env,
            planner: run.planner,
            params: run.params,
            seed: this.seed,
            smoothing: run.smoothing,
            trace: true,
          });
          if (seq !== this.planSeq) return;
          this.results.set(run.id, result);
          this.states.set(run.id, new TraceState(result));
        } catch (err) {
          if (seq !== this.planSeq) return;
          errors.push(`${this.runTitle(run)}: ${err.message}`);
          this.results.set(run.id, { success: false, message: err.message, metrics: {}, stats: {}, series: {} });
          this.states.delete(run.id);
        }
      }),
    );
    if (seq !== this.planSeq) return;
    button.classList.remove("busy");
    for (const r of runs) this.pending.delete(r.id);
    if (errors.length) toast(errors[0], "error", 6000);
    this.player.reset(animate);
    this.emit("results");
    this.views.updateLabels();
    this.requestRender();
  }

  scheduleLive() {
    if (!this.live) return;
    if (this.liveBusy) {
      this.liveAgain = true;
      return;
    }
    this.liveBusy = true;
    this.planAll({ animate: false }).finally(() => {
      this.liveBusy = false;
      if (this.liveAgain) {
        this.liveAgain = false;
        this.scheduleLive();
      }
    });
  }

  setLive(on) {
    this.live = on;
    document.getElementById("live").checked = on;
    this.persist();
    if (on) this.scheduleLive();
  }

  // ------------------------------------------------------------------ import / export

  importData(data) {
    if (data && data.environment && data.result) {
      // Output of `mpplay plan --output`: show the environment and the recorded result.
      this.setEnv(data.environment, { scenario: null });
      const res = data.result;
      if (!this.plannerInfo(res.planner)) throw new Error(`unknown planner ${res.planner}`);
      const run = this.addRun(res.planner, { silent: true, params: res.params || {}, smoothing: !!res.raw_path });
      this.runsChanged();
      this.results.set(run.id, res);
      this.states.set(run.id, new TraceState(res));
      this.player.reset(true);
      this.emit("results");
      this.views.updateLabels();
      this.requestRender();
      return `Loaded ${res.label} result on "${data.environment.name}"`;
    }
    if (data && data.bounds) {
      this.setEnv(data, { scenario: null });
      return `Loaded environment "${data.name || "Untitled"}"`;
    }
    throw new Error("expected an environment JSON or a result written by `mpplay plan --output`");
  }

  exportEnv() {
    const slug = (this.env.name || "environment").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    downloadText(`${slug || "environment"}.json`, `${JSON.stringify(this.env, null, 2)}\n`);
  }

  // ------------------------------------------------------------------ chrome (header, toolbar, tabs, keys)

  bindChrome() {
    const $ = (id) => document.getElementById(id);

    const scenarioSelect = $("scenario-select");
    scenarioSelect.append(new Option("Custom", ""));
    for (const s of this.catalog.scenarios) scenarioSelect.append(new Option(s.label, s.name));
    scenarioSelect.addEventListener("change", () => {
      const s = this.catalog.scenarios.find((x) => x.name === scenarioSelect.value);
      if (s) this.setEnv(s.environment, { scenario: s.name });
      scenarioSelect.blur();
    });

    $("btn-generate").addEventListener("click", () => this.generateDialog.open());
    $("btn-undo").addEventListener("click", () => this.undo());
    $("btn-redo").addEventListener("click", () => this.redo());
    $("btn-export").addEventListener("click", () => this.exportEnv());
    $("btn-snapshot").addEventListener("click", async () => downloadBlob("motion-planning-playground.png", await this.views.snapshot()));
    $("btn-help").addEventListener("click", () => this.helpDialog.open());
    $("btn-theme").addEventListener("click", () => this.toggleTheme());

    const fileInput = $("file-input");
    $("btn-import").addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", async () => {
      const file = fileInput.files[0];
      fileInput.value = "";
      if (!file) return;
      try {
        toast(this.importData(JSON.parse(await file.text())));
      } catch (err) {
        toast(`Could not open ${file.name}: ${err.message}`, "error", 6000);
      }
    });

    $("btn-plan").addEventListener("click", () => this.planAll());
    const seed = $("seed");
    seed.value = this.seed;
    seed.addEventListener("change", () => {
      this.seed = Math.max(0, Math.round(Number(seed.value) || 0));
      seed.value = this.seed;
      this.persist();
      if (this.live) this.scheduleLive();
    });
    $("btn-reseed").addEventListener("click", () => {
      this.seed = Math.floor(Math.random() * 100000);
      seed.value = this.seed;
      this.persist();
      this.planAll({ animate: !this.live });
    });
    const live = $("live");
    live.checked = this.live;
    live.addEventListener("change", () => this.setLive(live.checked));

    for (const btn of $("view-mode").querySelectorAll("button")) {
      btn.addEventListener("click", () => {
        this.viewMode = btn.dataset.mode;
        this.views.layout();
        this.updateChrome();
        this.persist();
      });
    }
    $("btn-fit").addEventListener("click", () => {
      this.camera.fit();
      this.requestRender();
    });

    // Layers dropdown.
    const menu = $("layers-menu");
    const panel = $("layers-panel");
    for (const [key, label, desc] of LAYERS) {
      const cb = h("input", { type: "checkbox", checked: !!this.layers[key] });
      cb.addEventListener("change", () => {
        this.layers[key] = cb.checked;
        this.persist();
        this.requestRender();
      });
      panel.append(h("label", { class: "check-row" }, cb, h("span", {}, label, h("small", {}, desc))));
    }
    $("btn-layers").addEventListener("click", (e) => {
      e.stopPropagation();
      menu.classList.toggle("open");
    });
    document.addEventListener("click", (e) => {
      if (!menu.contains(e.target)) menu.classList.remove("open");
    });

    // Tabs.
    for (const btn of $("tabs").querySelectorAll("button")) {
      btn.addEventListener("click", () => this.setTab(btn.dataset.tab));
    }
    this.setTab(this.tab);

    // Mouse clicks should not leave focus on buttons (Space/Enter are global shortcuts).
    document.addEventListener("click", (e) => {
      const b = e.target.closest?.("button, select");
      if (b && e.detail > 0 && b.tagName === "BUTTON") b.blur();
    });
    document.addEventListener("keydown", (e) => this.onKey(e));
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => this.themeChanged());

    this.on("env", (e) => {
      if (!e.detail.transient) this.updateChrome();
    });
  }

  setTab(tab) {
    this.tab = tab;
    for (const btn of document.querySelectorAll("#tabs button")) {
      btn.setAttribute("aria-selected", String(btn.dataset.tab === tab));
    }
    for (const panel of document.querySelectorAll(".tab-panel")) {
      panel.classList.toggle("active", panel.dataset.panel === tab);
    }
    this.persist();
  }

  updateChrome() {
    const $ = (id) => document.getElementById(id);
    $("btn-undo").disabled = !this.undoStack.length;
    $("btn-redo").disabled = !this.redoStack.length;
    const select = $("scenario-select");
    select.value = this.scenario && this.catalog.scenarios.some((s) => s.name === this.scenario) ? this.scenario : "";
    for (const btn of $("view-mode").querySelectorAll("button")) {
      btn.setAttribute("aria-checked", String(btn.dataset.mode === this.viewMode));
    }
  }

  toggleTheme() {
    const next = this.isDark() ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      /* ignore */
    }
    this.themeChanged();
  }

  themeChanged() {
    themeColors(true);
    this.runsPanel.render();
    this.metricsPanel.render();
    this.chartsPanel.render();
    this.learnPanel.render();
    if (!this.benchmarkPanel.running) this.benchmarkPanel.render();
    this.views.updateLabels();
    this.requestRender();
  }

  onKey(e) {
    if (document.querySelector("dialog[open]")) return;
    if (isTyping(e)) return;
    const onControl = e.target instanceof HTMLElement && ["BUTTON", "A", "SUMMARY"].includes(e.target.tagName);
    if (onControl && (e.key === " " || e.key === "Enter")) return;
    if (this.editor.onKey(e)) {
      e.preventDefault();
      return;
    }
    const mod = e.ctrlKey || e.metaKey;
    const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    if (mod) {
      if (key === "z") {
        e.preventDefault();
        if (e.shiftKey) this.redo();
        else this.undo();
      } else if (key === "y") {
        e.preventDefault();
        this.redo();
      } else if (key === "d") {
        e.preventDefault();
        this.duplicateSelection();
      }
      return;
    }
    if (e.altKey) return;
    switch (key) {
      case " ":
        e.preventDefault();
        this.player.toggle();
        return;
      case "ArrowLeft":
        e.preventDefault();
        this.player.stepBy(e.shiftKey ? -10 : -1);
        return;
      case "ArrowRight":
        e.preventDefault();
        this.player.stepBy(e.shiftKey ? 10 : 1);
        return;
      case "Home":
        this.player.restart();
        return;
      case "End":
        this.player.end();
        return;
      case "Enter":
        e.preventDefault();
        this.planAll();
        return;
      case "Delete":
      case "Backspace":
        e.preventDefault();
        this.deleteSelection();
        return;
      case "Escape":
        this.editor.cancel();
        this.select(null);
        this.requestRender();
        return;
      case "f":
        this.camera.fit();
        this.requestRender();
        return;
      case "?":
        this.helpDialog.open();
        return;
      default: {
        const tool = TOOLS.find((t) => t.key === key);
        if (tool) this.setTool(tool.id);
      }
    }
  }
}

