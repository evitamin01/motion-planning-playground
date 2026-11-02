// Incremental replay of planner traces (format: docs/trace-format.md).
//
// A TraceState accumulates the visual state after the first `k` steps of a
// trace. Seeking forward applies only the new events; seeking backward
// replays from the beginning (cheap: traces have at most ~1e6 events).

const FRONTIER = 1;
const EXPANDED = 2;

function decodeBase64(text) {
  const bin = atob(text);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/** Decode a grid description from the API (row-major j * nx + i). */
export function decodeGrid(grid, key = "occupancy") {
  const [nx, ny] = grid.shape;
  return {
    nx,
    ny,
    res: grid.resolution,
    ox: grid.origin[0],
    oy: grid.origin[1],
    data: decodeBase64(grid[key] ?? grid.values),
  };
}

export class TraceState {
  constructor(result) {
    this.result = result;
    const trace = result.trace || { events: [], steps: [] };
    this.events = trace.events;
    this.steps = trace.steps;
    this.numSteps = trace.steps.length;
    this.truncated = !!trace.truncated;
    this.grid = result.grid ? decodeGrid(result.grid) : null;
    this.heatmaps = (result.overlays || [])
      .filter((o) => o.type === "heatmap")
      .map((o) => ({ ...decodeGrid(o, "values"), label: o.label }));
    this.version = 0;
    this.reset();
  }

  reset() {
    this.cursor = 0; // number of events applied
    this.shown = 0; // number of steps applied
    this.stepAt = -1; // step index of the last applied event
    this.cells = this.grid ? new Uint8Array(this.grid.nx * this.grid.ny) : null;
    this.changedCells = [];
    this.cellsReset = true;
    this.edges = new Map();
    this.nodes = [];
    this.path = null;
    this.overlays = new Map();
    this.sample = null;
    this.sampleStep = -1;
    this.version++;
  }

  get complete() {
    return this.shown >= this.numSteps;
  }

  /** Show the first `k` steps (k = numSteps shows everything). */
  seek(k) {
    k = Math.max(0, Math.min(this.numSteps, Math.floor(k)));
    const target = k >= this.numSteps ? this.events.length : this.steps[k];
    if (target < this.cursor) this.reset();
    if (target === this.cursor) {
      this.shown = k;
      return;
    }
    const nx = this.grid ? this.grid.nx : 0;
    for (let idx = this.cursor; idx < target; idx++) {
      while (this.stepAt + 1 < this.numSteps && this.steps[this.stepAt + 1] <= idx) this.stepAt++;
      const ev = this.events[idx];
      switch (ev[0]) {
        case "X": {
          const c = ev[2] * nx + ev[1];
          if (this.cells && this.cells[c] !== EXPANDED) {
            this.cells[c] = EXPANDED;
            this.changedCells.push(c);
          }
          break;
        }
        case "F": {
          const c = ev[2] * nx + ev[1];
          if (this.cells && this.cells[c] === 0) {
            this.cells[c] = FRONTIER;
            this.changedCells.push(c);
          }
          break;
        }
        case "S":
          this.sample = [ev[1], ev[2]];
          this.sampleStep = this.stepAt;
          break;
        case "N":
          this.nodes.push(ev);
          break;
        case "E":
          this.edges.set(ev[1], ev);
          break;
        case "R":
          this.edges.delete(ev[1]);
          break;
        case "P":
          this.path = ev[1];
          break;
        case "G":
          if (ev[2] === null) this.overlays.delete(ev[1]);
          else this.overlays.set(ev[1], ev[2]);
          break;
        default:
          break;
      }
    }
    this.cursor = target;
    this.shown = k;
    this.version++;
  }

  /** The random sample of the most recent step, if any (it is transient). */
  currentSample() {
    return this.sample && this.sampleStep === this.shown - 1 && !this.complete ? this.sample : null;
  }

  /** Counts for the status line. */
  counts() {
    let expanded = 0;
    let frontier = 0;
    if (this.cells) {
      for (const v of this.cells) {
        if (v === EXPANDED) expanded++;
        else if (v === FRONTIER) frontier++;
      }
    }
    return { expanded, frontier, edges: this.edges.size, nodes: this.nodes.length };
  }
}

export const CELL = { FRONTIER, EXPANDED };
