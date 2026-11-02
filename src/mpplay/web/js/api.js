// Thin client for the JSON API served by `mpplay serve`.

async function request(path, body) {
  const init = body === undefined
    ? {}
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  let response;
  try {
    response = await fetch(path, init);
  } catch (err) {
    throw new Error("Cannot reach the server. Is `mpplay serve` still running?");
  }
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") message = data.detail;
      else if (Array.isArray(data.detail)) {
        message = data.detail.map((d) => `${(d.loc || []).join(".")}: ${d.msg}`).join("; ");
      }
    } catch {
      /* keep the HTTP status text */
    }
    throw new Error(message);
  }
  return response.json();
}

// Relative URLs keep the UI working behind a reverse proxy sub-path.
export const api = {
  info: () => request("api/info"),
  planners: () => request("api/planners"),
  scenarios: () => request("api/scenarios"),
  generators: () => request("api/generators"),
  generate: (body) => request("api/generate", body),
  plan: (body) => request("api/plan", body),
  benchmark: (body) => request("api/benchmark", body),
};
