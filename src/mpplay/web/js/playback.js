// Synchronized step-by-step playback of all planner traces.

import { setIcon } from "./dom.js";

export const SPEEDS = [
  { value: "auto", label: "Auto" },
  { value: 2, label: "2 /s" },
  { value: 10, label: "10 /s" },
  { value: 30, label: "30 /s" },
  { value: 100, label: "100 /s" },
  { value: 300, label: "300 /s" },
  { value: 1000, label: "1k /s" },
  { value: 3000, label: "3k /s" },
  { value: 10000, label: "10k /s" },
];

/** Target duration of an "Auto"-speed animation in seconds. */
const AUTO_SECONDS = 8;

export class Player {
  constructor(app) {
    this.app = app;
    this.t = 0;
    this.total = 0;
    this.playing = false;
    this.speed = "auto";
    this.sync = "steps";
    this.lastTs = null;
  }

  states() {
    return [...this.app.states.values()];
  }

  stepsPerSecond() {
    if (this.speed !== "auto") return Number(this.speed);
    return Math.max(this.total / AUTO_SECONDS, 5);
  }

  /** Called when new results arrive. */
  reset(animate) {
    this.total = Math.max(0, ...this.states().map((s) => s.numSteps));
    this.t = animate ? 0 : this.total;
    this.playing = animate && this.total > 0;
    this.lastTs = null;
    this.apply();
  }

  stepFor(state) {
    if (this.sync === "progress" && this.total > 0) {
      return Math.floor((this.t / this.total) * state.numSteps + 1e-9);
    }
    return Math.floor(this.t + 1e-9);
  }

  apply() {
    for (const s of this.states()) s.seek(this.stepFor(s));
  }

  tick(ts) {
    if (!this.playing) {
      this.lastTs = null;
      return;
    }
    if (this.lastTs !== null) {
      const dt = Math.min((ts - this.lastTs) / 1000, 0.25);
      this.t = Math.min(this.t + dt * this.stepsPerSecond(), this.total);
    }
    this.lastTs = ts;
    if (this.t >= this.total) this.playing = false;
    this.apply();
  }

  play() {
    if (!this.total) return;
    if (this.t >= this.total) this.t = 0;
    this.playing = true;
    this.lastTs = null;
    this.app.requestRender();
  }

  pause() {
    this.playing = false;
  }

  toggle() {
    if (this.playing) this.pause();
    else this.play();
    this.app.requestRender();
  }

  seek(t) {
    this.t = Math.max(0, Math.min(this.total, t));
    this.apply();
    this.app.requestRender();
  }

  stepBy(delta) {
    this.pause();
    this.seek(Math.floor(this.t + 1e-9) + delta);
  }

  restart() {
    this.seek(0);
    this.play();
  }

  end() {
    this.pause();
    this.seek(this.total);
  }
}

/** Binds the playback bar controls to a Player. */
export class Playbar {
  constructor(app, player) {
    this.app = app;
    this.player = player;
    const $ = (id) => document.getElementById(id);
    this.play = $("pb-play");
    this.timeline = $("pb-timeline");
    this.counter = $("pb-counter");
    this.speed = $("pb-speed");
    this.sync = $("pb-sync");
    for (const s of SPEEDS) this.speed.append(new Option(s.label, String(s.value)));
    this.speed.value = String(player.speed);
    this.sync.value = player.sync;

    this.play.addEventListener("click", () => player.toggle());
    $("pb-back").addEventListener("click", () => player.stepBy(-1));
    $("pb-forward").addEventListener("click", () => player.stepBy(1));
    $("pb-restart").addEventListener("click", () => player.restart());
    $("pb-end").addEventListener("click", () => player.end());
    this.timeline.addEventListener("input", () => {
      player.pause();
      player.seek(Number(this.timeline.value));
    });
    this.speed.addEventListener("change", () => {
      player.speed = this.speed.value === "auto" ? "auto" : Number(this.speed.value);
      app.persist();
    });
    this.sync.addEventListener("change", () => {
      player.sync = this.sync.value;
      player.apply();
      app.requestRender();
      app.persist();
    });
    this.lastIcon = null;
  }

  update() {
    const p = this.player;
    const icon = p.playing ? "pause" : "play";
    if (icon !== this.lastIcon) {
      setIcon(this.play, icon);
      this.lastIcon = icon;
    }
    this.timeline.max = String(p.total);
    this.timeline.value = String(Math.floor(p.t));
    this.counter.textContent = `${Math.floor(p.t).toLocaleString("en-US")} / ${p.total.toLocaleString("en-US")}`;
    const disabled = p.total === 0;
    for (const id of ["pb-play", "pb-back", "pb-forward", "pb-restart", "pb-end"]) {
      document.getElementById(id).disabled = disabled;
    }
    this.timeline.disabled = disabled;
  }
}
