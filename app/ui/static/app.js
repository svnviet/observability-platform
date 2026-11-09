import {
  barGeometry,
  buildQuery,
  formatAge,
  formatDuration,
  formatTime,
  localInputToIso,
  statusClass,
  timelineSpan,
} from "./format.js";

const view = document.getElementById("view");
const nav = document.getElementById("nav");
const tools = document.getElementById("tools");
const dialog = document.getElementById("key-dialog");
const keyInput = document.getElementById("key-input");
const keyError = document.getElementById("key-error");

const SECTIONS = [
  ["overview", "Overview"],
  ["workflows", "Workflows"],
  ["services", "Services"],
  ["workers", "Workers"],
  ["errors", "Errors"],
  ["incidents", "Incidents"],
];
const REFRESH_MS = 10000;
const PAGE = 25;

// ---- tiny DOM helper: text is always set as text, never parsed as HTML -------------------------

function h(tag, props, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (key === "style") {
      // The page's CSP forbids inline style attributes; setting properties through the CSSOM is allowed.
      if (typeof value === "string") throw new Error("pass style as an object: inline style strings are blocked by CSP");
      for (const [prop, v] of Object.entries(value)) node.style.setProperty(prop, v);
    }
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

const chip = (status) => h("span", { class: `chip ${statusClass(status)}` }, String(status || "–").replaceAll("_", " "));
const mono = (text) => h("span", { class: "mono" }, text ?? "–");
const link = (href, text, external = false) =>
  h("a", { href, ...(external ? { target: "_blank", rel: "noopener noreferrer" } : {}) }, text);

function table(headers, rows, empty = "Nothing to show.") {
  if (!rows.length) return h("p", { class: "empty" }, empty);
  return h(
    "div",
    { class: "scroll" },
    h("table", null, h("thead", null, h("tr", null, headers.map((x) => h("th", null, x)))), h("tbody", null, rows)),
  );
}

function tile(label, value, sub, tone = "") {
  return h("div", { class: `tile ${tone}` }, h("div", { class: "tile-value" }, value), h("div", { class: "tile-label" }, label), sub ? h("div", { class: "tile-sub" }, sub) : null);
}

function section(title, ...body) {
  return h("section", null, h("h2", null, title), ...body);
}

// ---- API ----------------------------------------------------------------------------------------

let apiKey = sessionStorage.getItem("obskit-key") || "";
let links = {};

class AuthError extends Error {}

async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method,
    headers: { "X-API-Key": apiKey, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) throw new AuthError();
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${res.status} ${detail.slice(0, 200)}`);
  }
  return res.json();
}

function askForKey(message = "") {
  keyError.hidden = !message;
  keyError.textContent = message;
  keyInput.value = "";
  if (!dialog.open) dialog.showModal();
  keyInput.focus();
}

document.getElementById("key-button").addEventListener("click", () => askForKey());
document.getElementById("key-form").addEventListener("submit", async (event) => {
  const candidate = keyInput.value.trim();
  if (!candidate) return;
  const previous = apiKey;
  apiKey = candidate;
  try {
    await api("/monitoring/links");
    sessionStorage.setItem("obskit-key", apiKey);
    route();
  } catch (err) {
    apiKey = previous;
    event.preventDefault();
    askForKey(err instanceof AuthError ? "That key was not accepted." : "Could not reach the platform.");
  }
});

// ---- routing and refresh ------------------------------------------------------------------------

let timer = null;
let renderId = 0;

function parseHash() {
  const [, name = "overview", id] = location.hash.split("/");
  return { name: SECTIONS.some(([key]) => key === name) ? name : "overview", id };
}

function renderNav(active) {
  nav.replaceChildren(
    ...SECTIONS.map(([key, label]) => h("a", { href: `#/${key}`, class: key === active ? "active" : "", "aria-current": key === active ? "page" : null }, label)),
  );
}

function renderTools() {
  tools.replaceChildren(
    ...[["Traces", links.jaeger_url], ["Dashboards", links.perses_url], ["Metrics", links.prometheus_url]]
      .filter(([, url]) => url)
      .map(([label, url]) => link(url, label, true)),
  );
}

async function route() {
  clearTimeout(timer);
  const myRender = ++renderId;
  const { name, id } = parseHash();
  renderNav(name);
  if (!apiKey) {
    view.replaceChildren(h("p", { class: "empty" }, "Enter the API key to connect."));
    askForKey();
    return;
  }
  const scroll = window.scrollY;
  try {
    if (!Object.keys(links).length) {
      links = await api("/monitoring/links");
      renderTools();
    }
    const page = await PAGES[name](id);
    if (myRender !== renderId) return; // a newer navigation won
    view.replaceChildren(...page.content.filter(Boolean)); // replaceChildren would print null as text
    window.scrollTo(0, page.keepScroll ? scroll : 0);
    if (page.live) timer = setTimeout(route, REFRESH_MS);
  } catch (err) {
    if (myRender !== renderId) return;
    if (err instanceof AuthError) {
      sessionStorage.removeItem("obskit-key");
      apiKey = "";
      askForKey("The key was rejected. Enter it again.");
      return;
    }
    view.replaceChildren(h("div", { class: "panel bad" }, h("strong", null, "Could not load this page. "), String(err.message || err)));
  }
}

// ---- pages --------------------------------------------------------------------------------------

async function overviewPage() {
  const [o, m, failed, incidents] = await Promise.all([
    api("/monitoring/overview"),
    api("/monitoring/metrics"),
    api("/workflow-runs?status=FAILED&limit=5"),
    api("/incidents?status=OPEN&limit=5"),
  ]);
  const content = [
    h("h1", null, "System overview"),
    h(
      "div",
      { class: "tiles" },
      tile("Services healthy", `${o.services_healthy}/${o.services_total}`, `${o.instances_total} instances`, o.services_unhealthy ? "bad" : "good"),
      tile("Workers active", o.workers_active, `${o.workers_unhealthy} unhealthy`, o.workers_unhealthy ? "bad" : ""),
      tile("Workflows running", o.workflows_active),
      tile("Completed", o.workflows_completed, "all time", "good"),
      tile("Failed", o.workflows_failed, "all time", o.workflows_failed ? "bad" : ""),
      tile("Jobs", `${o.jobs_running} running`, `${o.jobs_queued} queued`),
      tile("Open incidents", o.open_incidents, null, o.open_incidents ? "bad" : "good"),
      tile("Rejected events", o.rejected_events, "failed validation", o.rejected_events ? "warn" : ""),
    ),
    section(
      "Needs attention",
      h(
        "div",
        { class: "two" },
        h("div", { class: "panel" }, h("h3", null, "Open incidents"), incidentList(incidents.items), link("#/incidents", "All incidents")),
        h("div", { class: "panel" }, h("h3", null, "Recent failed workflows"), runList(failed.items), link("#/workflows", "Open the explorer")),
      ),
    ),
    section(
      `Last ${m.window_hours} hours`,
      h(
        "dl",
        { class: "facts" },
        fact("Workflows", Object.entries(m.workflows_by_status).map(([k, v]) => `${v} ${k.toLowerCase()}`).join(" · ") || "none"),
        fact("Workflow duration", `avg ${formatDuration(m.workflow_duration_avg_ms)} · p95 ${formatDuration(m.workflow_duration_p95_ms)}`),
        fact("Step attempts", `${m.attempts_total} total · ${m.retries_total} retries`),
        fact("Events received", `${m.events_received}` + (Object.keys(m.events_by_disposition).length ? ` (${Object.entries(m.events_by_disposition).map(([k, v]) => `${v} ${k.toLowerCase()}`).join(", ")})` : "")),
      ),
    ),
  ];
  return { content, live: true, keepScroll: true };
}

const fact = (label, value) => [h("dt", null, label), h("dd", null, value)];

function incidentList(items) {
  if (!items.length) return h("p", { class: "empty" }, "No open incidents.");
  return h("ul", { class: "list" }, items.map((i) => h("li", null, chip(i.severity), " ", h("span", null, i.title), h("span", { class: "muted" }, ` · ${formatTime(i.detected_at)}`), i.workflow_run_id ? [" ", link(`#/workflows/${i.workflow_run_id}`, "view run")] : null)));
}

function runList(items) {
  if (!items.length) return h("p", { class: "empty" }, "No failed workflows.");
  return h("ul", { class: "list" }, items.map((r) => h("li", null, chip(r.status), " ", link(`#/workflows/${r.id}`, r.workflow_name || r.workflow_id), h("span", { class: "muted" }, ` · ${formatTime(r.finished_at || r.started_at)}`))));
}

// Explorer filters live outside the page so they survive navigation and auto refresh.
const wf = { workflow_id: "", status: "", service: "", after: "", offset: 0 };

async function workflowsPage() {
  const query = buildQuery({
    workflow_id: wf.workflow_id.trim(),
    status: wf.status,
    service: wf.service.trim(),
    started_after: localInputToIso(wf.after),
    limit: PAGE,
    offset: wf.offset,
  });
  const page = await api(`/workflow-runs${query}`);
  const apply = (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    Object.assign(wf, { workflow_id: form.get("workflow_id"), status: form.get("status"), service: form.get("service"), after: form.get("after"), offset: 0 });
    route();
  };
  const statuses = ["", "CREATED", "QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"];
  const content = [
    h("h1", null, "Workflow explorer"),
    h(
      "form",
      { class: "filters", onsubmit: apply },
      field("Workflow id", h("input", { name: "workflow_id", value: wf.workflow_id, placeholder: "wf-123" })),
      field("Status", h("select", { name: "status" }, statuses.map((s) => h("option", { value: s, selected: s === wf.status }, s || "Any")))),
      field("Service", h("input", { name: "service", value: wf.service, placeholder: "video-generator" })),
      field("Started after", h("input", { name: "after", type: "datetime-local", value: wf.after })),
      h("button", { type: "submit", class: "primary" }, "Search"),
      h("button", { type: "button", class: "ghost", onclick: () => { Object.assign(wf, { workflow_id: "", status: "", service: "", after: "", offset: 0 }); route(); } }, "Clear"),
    ),
    table(
      ["Workflow", "Status", "Started", "Duration", "Trace"],
      page.items.map((r) =>
        h("tr", null,
          h("td", null, link(`#/workflows/${r.id}`, r.workflow_name || r.workflow_id), h("div", { class: "muted small" }, `${r.workflow_id} · ${r.run_key}`)),
          h("td", null, chip(r.status)),
          h("td", null, formatTime(r.started_at)),
          h("td", null, formatDuration(r.duration_ms)),
          h("td", null, r.trace_url ? link(r.trace_url, "Open trace", true) : mono(r.trace_id ? r.trace_id.slice(0, 8) : "–")),
        ),
      ),
      "No workflow runs match.",
    ),
    pager(page, (offset) => { wf.offset = offset; route(); }),
  ];
  return { content, live: false };
}

const field = (label, input) => h("label", { class: "field" }, h("span", null, label), input);

function pager(page, go) {
  if (page.total <= page.limit) return h("p", { class: "muted small" }, `${page.total} result${page.total === 1 ? "" : "s"}`);
  const from = page.offset + 1;
  const to = Math.min(page.total, page.offset + page.limit);
  return h(
    "div",
    { class: "pager" },
    h("button", { class: "ghost", type: "button", disabled: page.offset === 0, onclick: () => go(Math.max(0, page.offset - page.limit)) }, "Previous"),
    h("span", { class: "muted" }, `${from}–${to} of ${page.total}`),
    h("button", { class: "ghost", type: "button", disabled: to >= page.total, onclick: () => go(page.offset + page.limit) }, "Next"),
  );
}

async function workflowDetailPage(id) {
  const [run, timeline, events] = await Promise.all([
    api(`/workflow-runs/${id}`),
    api(`/workflow-runs/${id}/timeline`),
    api(`/workflow-runs/${id}/events?limit=200`),
  ]);
  const span = timelineSpan(timeline);
  const live = !["COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"].includes(run.status);
  const copy = (text) => h("button", { class: "ghost tiny", type: "button", title: "Copy", onclick: (e) => { navigator.clipboard?.writeText(text); e.target.textContent = "Copied"; } }, "Copy");

  const content = [
    h("p", { class: "crumb" }, link("#/workflows", "Workflows"), " / ", run.workflow_id),
    h("h1", null, run.workflow_name || run.workflow_id, " ", chip(run.status)),
    h(
      "dl",
      { class: "facts" },
      fact("Run", [mono(run.run_key), " ", copy(run.run_key)]),
      fact("Workflow id", run.workflow_id),
      fact("Correlation id", run.correlation_id ? [mono(run.correlation_id), " ", copy(run.correlation_id)] : "–"),
      fact("Started", formatTime(run.started_at)),
      fact("Duration", formatDuration(run.duration_ms)),
      fact("Trace", run.trace_url ? link(run.trace_url, "Open in Jaeger", true) : run.trace_id ? [mono(run.trace_id), " ", copy(run.trace_id)] : "–"),
      fact("Logs", run.correlation_id ? "Search your log store for the correlation id above." : "–"),
    ),
    run.error_details ? errorPanel("Run error", run.error_details) : null,
    section("Timeline", ganttChart(timeline, span)),
    section("Steps and attempts", stepsTable(run.steps)),
    section("Event history", eventsTable(events)),
    h("div", { class: "row" }, replayButton(id)),
  ];
  return { content, live, keepScroll: true };
}

function ganttChart(entries, span) {
  if (!span) return h("p", { class: "empty" }, "Nothing has started yet.");
  const total = span.end - span.start;
  const rows = entries.map((e) => {
    const geo = barGeometry(e, span.start, span.end);
    const label = e.kind === "workflow" ? e.name : `${e.name}${e.attempt_number ? ` #${e.attempt_number}` : ""}`;
    return h(
      "div",
      { class: `gantt-row ${e.kind}` },
      h("div", { class: "gantt-label" }, h("span", null, label), e.service_name ? h("span", { class: "muted small" }, e.service_name + (e.worker_key ? ` · ${e.worker_key}` : "")) : null),
      h("div", { class: "gantt-track" }, geo ? h("div", { class: `gantt-bar ${statusClass(e.status)}`, style: { left: `${geo.left}%`, width: `${geo.width}%` }, title: `${e.status} · ${formatDuration(e.duration_ms)}` }) : h("span", { class: "muted small gantt-none" }, e.status)),
      h("div", { class: "gantt-time" }, chip(e.status), " ", formatDuration(e.duration_ms)),
    );
  });
  return h("div", { class: "gantt" }, h("div", { class: "muted small" }, `Total ${formatDuration(total)}`), rows);
}

function errorPanel(title, error) {
  return h("div", { class: "panel bad" }, h("strong", null, `${title}: `), error.type || "Error", error.message ? ` — ${error.message}` : "", error.stack_trace ? h("details", null, h("summary", null, "Stack trace"), h("pre", null, error.stack_trace)) : null);
}

function stepsTable(steps) {
  if (!steps.length) return h("p", { class: "empty" }, "No steps recorded.");
  return h(
    "div",
    { class: "steps" },
    steps.map((s) =>
      h(
        "details",
        { class: "step", open: s.status === "FAILED" || s.status === "RETRYING" },
        h("summary", null, chip(s.status), " ", h("strong", null, s.step_name), h("span", { class: "muted" }, ` · ${s.service_name || "unknown service"} · ${s.attempts.length} attempt${s.attempts.length === 1 ? "" : "s"}`)),
        table(
          ["Attempt", "Status", "Worker", "Duration", "Trace"],
          s.attempts.map((a) =>
            h("tr", null,
              h("td", null, `#${a.attempt_number}`),
              h("td", null, chip(a.status), a.error_details ? h("div", { class: "small bad-text" }, `${a.error_details.type || "Error"}${a.error_details.message ? `: ${a.error_details.message}` : ""}`) : null, a.error_details?.stack_trace ? h("details", null, h("summary", { class: "small" }, "Stack trace"), h("pre", null, a.error_details.stack_trace)) : null),
              h("td", null, a.worker_key ? mono(a.worker_key) : "–"),
              h("td", null, a.started_at && a.finished_at ? formatDuration(new Date(a.finished_at) - new Date(a.started_at)) : "–"),
              h("td", null, a.trace_url ? link(a.trace_url, "Trace", true) : "–"),
            ),
          ),
        ),
      ),
    ),
  );
}

function eventsTable(page) {
  return table(
    ["Occurred", "Event", "From", "Handling"],
    page.items.map((e) =>
      h("tr", null,
        h("td", null, formatTime(e.occurred_at)),
        h("td", null, mono(e.event_type), e.payload?.context?.step_id ? h("span", { class: "muted small" }, ` ${e.payload.context.step_id}`) : null),
        h("td", null, e.source_service),
        h("td", null, chip(e.disposition), e.disposition_reason ? h("div", { class: "muted small" }, e.disposition_reason) : null),
      ),
    ),
    "No events.",
  );
}

function replayButton(id) {
  const button = h("button", { class: "ghost", type: "button" }, "Rebuild state from events");
  let armed = false;
  button.addEventListener("click", async () => {
    if (!armed) {
      armed = true;
      button.textContent = "Click again to rebuild this run";
      setTimeout(() => { armed = false; button.textContent = "Rebuild state from events"; }, 4000);
      return;
    }
    button.disabled = true;
    try {
      await api("/events/replay", { method: "POST", body: { workflow_run_ids: [id] } });
      route();
    } catch (err) {
      button.disabled = false;
      button.textContent = `Failed: ${err.message}`;
    }
  });
  return button;
}

async function servicesPage() {
  const services = await api("/services");
  const details = await Promise.all(services.map((s) => api(`/services/${s.id}`)));
  const content = [
    h("h1", null, "Services"),
    table(
      ["Service", "Environment", "Version", "Status", "Instances", "Last heartbeat"],
      details.flatMap((s) => [
        h("tr", null,
          h("td", null, h("strong", null, s.name)),
          h("td", null, s.environment),
          h("td", null, s.version || "–"),
          h("td", null, chip(s.status)),
          h("td", null, `${s.instances_healthy}/${s.instances_total} healthy`),
          h("td", null, s.last_heartbeat_at ? formatAge((Date.now() - new Date(s.last_heartbeat_at)) / 1000) : "–"),
        ),
        ...s.instances.map((i) =>
          h("tr", { class: "sub" },
            h("td", { colspan: 2 }, mono(i.instance_id)),
            h("td", null, i.hostname || "–"),
            h("td", null, chip(i.status)),
            h("td", null, `registered ${formatTime(i.registered_at)}`),
            h("td", null, formatAge(i.heartbeat_age_s)),
          ),
        ),
      ]),
      "No services have registered yet.",
    ),
  ];
  return { content, live: true, keepScroll: true };
}

const workerFilter = { status: "", service: "" };

async function workersPage() {
  const query = buildQuery({ status: workerFilter.status, service: workerFilter.service.trim(), limit: 200 });
  const workers = await api(`/workers${query}`);
  const statuses = ["", "REGISTERED", "STARTING", "IDLE", "BUSY", "DRAINING", "STOPPED", "UNHEALTHY"];
  const content = [
    h("h1", null, "Workers"),
    h(
      "form",
      { class: "filters", onsubmit: (event) => { event.preventDefault(); const f = new FormData(event.target); workerFilter.status = f.get("status"); workerFilter.service = f.get("service"); route(); } },
      field("Status", h("select", { name: "status" }, statuses.map((s) => h("option", { value: s, selected: s === workerFilter.status }, s || "Any")))),
      field("Service", h("input", { name: "service", value: workerFilter.service, placeholder: "video-generator" })),
      h("button", { type: "submit", class: "primary" }, "Filter"),
    ),
    table(
      ["Worker", "Service", "Type", "Status", "Current job", "Capacity", "Last heartbeat"],
      workers.map((w) =>
        h("tr", null,
          h("td", null, h("strong", null, w.worker_name)),
          h("td", null, w.service_name, h("div", { class: "muted small" }, w.instance_id)),
          h("td", null, w.worker_type),
          h("td", null, chip(w.status)),
          h("td", null, w.current_job_id ? mono(w.current_job_id) : "–"),
          h("td", null, w.capacity),
          h("td", { class: w.status === "UNHEALTHY" ? "bad-text" : "" }, formatAge(w.heartbeat_age_s)),
        ),
      ),
      "No workers match.",
    ),
  ];
  return { content, live: true, keepScroll: true };
}

const errorWindow = { hours: 24 };

async function errorsPage() {
  const groups = await api(`/monitoring/errors?window_hours=${errorWindow.hours}&limit=100`);
  const windows = [[24, "24 hours"], [168, "7 days"], [720, "30 days"]];
  const content = [
    h("h1", null, "Error explorer"),
    h("div", { class: "filters" }, field("Window", h("select", { onchange: (e) => { errorWindow.hours = Number(e.target.value); route(); } }, windows.map(([v, l]) => h("option", { value: v, selected: v === errorWindow.hours }, l))))),
    table(
      ["Exception", "Service", "Workflow", "Count", "First seen", "Last seen", "Example"],
      groups.map((g) =>
        h("tr", null,
          h("td", null, h("strong", null, g.exception_type), g.sample_message ? h("div", { class: "small muted clip" }, g.sample_message) : null),
          h("td", null, g.service_name || "–"),
          h("td", null, g.workflow_name || "–"),
          h("td", null, g.count),
          h("td", null, formatTime(g.first_seen)),
          h("td", null, formatTime(g.last_seen)),
          h("td", null, g.sample_workflow_run_id ? link(`#/workflows/${g.sample_workflow_run_id}`, "Open run") : "–"),
        ),
      ),
      "No failed step attempts in this window.",
    ),
    h("p", { class: "muted small" }, "Grouped from the most recent failed attempts; failures that the SDK retried successfully are included."),
  ];
  return { content, live: false };
}

const incidentFilter = { status: "OPEN" };

async function incidentsPage() {
  const page = await api(`/incidents${buildQuery({ status: incidentFilter.status, limit: 100 })}`);
  const content = [
    h("h1", null, "Incidents"),
    h("div", { class: "filters" }, field("Status", h("select", { onchange: (e) => { incidentFilter.status = e.target.value; route(); } }, [["OPEN", "Open"], ["RESOLVED", "Resolved"], ["", "All"]].map(([v, l]) => h("option", { value: v, selected: v === incidentFilter.status }, l))))),
    table(
      ["Severity", "Incident", "Detected", "Status", ""],
      page.items.map((i) =>
        h("tr", null,
          h("td", null, chip(i.severity)),
          h("td", null, h("strong", null, i.title), i.description ? h("div", { class: "small muted" }, i.description) : null, i.workflow_run_id ? link(`#/workflows/${i.workflow_run_id}`, "View run") : null),
          h("td", null, formatTime(i.detected_at)),
          h("td", null, chip(i.status), i.resolved_at ? h("div", { class: "small muted" }, formatTime(i.resolved_at)) : null),
          h("td", null, i.status === "OPEN" ? h("button", { class: "ghost", type: "button", onclick: async () => { await api(`/incidents/${i.id}/resolve`, { method: "POST" }); route(); } }, "Resolve") : null),
        ),
      ),
      "No incidents.",
    ),
  ];
  return { content, live: true, keepScroll: true };
}

const PAGES = {
  overview: overviewPage,
  workflows: (id) => (id ? workflowDetailPage(id) : workflowsPage()),
  services: servicesPage,
  workers: workersPage,
  errors: errorsPage,
  incidents: incidentsPage,
};

window.addEventListener("hashchange", route);
route();
