// Entry point of the web UI.

import { App } from "./app.js";

const app = new App();
window.mpplay = app; // handy for debugging from the browser console
app.init();
