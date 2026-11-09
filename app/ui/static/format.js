// Pure helpers (no DOM) so they can be tested with `node --test`.

export function formatDuration(ms) {
  if (ms === null || ms === undefined) return "–";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s < 10 ? s.toFixed(1) : Math.round(s)} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ${Math.round(s - m * 60)} s`;
  const h = Math.floor(m / 60);
  return `${h} h ${m - h * 60} min`;
}

export function formatAge(seconds) {
  if (seconds === null || seconds === undefined) return "–";
  if (seconds < 1) return "just now";
  if (seconds < 60) return `${Math.round(seconds)} s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} d ago`;
}

export function formatTime(iso) {
  if (!iso) return "–";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "–";
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" });
}

const GOOD = new Set(["COMPLETED", "HEALTHY", "IDLE", "RESOLVED", "APPLIED"]);
const BAD = new Set(["FAILED", "UNHEALTHY", "TIMED_OUT", "OPEN", "CRITICAL", "HIGH", "QUARANTINED"]);
const WARN = new Set(["RETRYING", "DEGRADED", "DRAINING", "MEDIUM", "STOPPED", "CANCELLED", "STALE"]);
const ACTIVE = new Set(["RUNNING", "BUSY", "QUEUED", "STARTING", "REGISTERED", "CREATED", "LOW"]);

/** CSS class that conveys a status; the label text always accompanies it, color is never the only cue. */
export function statusClass(status) {
  const s = String(status || "").toUpperCase();
  if (GOOD.has(s)) return "good";
  if (BAD.has(s)) return "bad";
  if (WARN.has(s)) return "warn";
  if (ACTIVE.has(s)) return "active";
  return "neutral";
}

/**
 * Position of one timeline bar as percentages of the whole span.
 * Entries without a start time get no bar (queued or skipped steps).
 */
export function barGeometry(entry, spanStartMs, spanEndMs, nowMs = Date.now()) {
  if (!entry.started_at) return null;
  const total = Math.max(1, spanEndMs - spanStartMs);
  const start = new Date(entry.started_at).getTime();
  const end = entry.finished_at ? new Date(entry.finished_at).getTime() : nowMs;
  const left = Math.min(100, Math.max(0, ((start - spanStartMs) / total) * 100));
  const width = Math.min(100 - left, Math.max(0.6, ((Math.max(end, start) - start) / total) * 100));
  return { left, width };
}

export function timelineSpan(entries, nowMs = Date.now()) {
  const starts = entries.filter((e) => e.started_at).map((e) => new Date(e.started_at).getTime());
  if (!starts.length) return null;
  const ends = entries.map((e) => (e.finished_at ? new Date(e.finished_at).getTime() : null)).filter((x) => x !== null);
  const open = entries.some((e) => e.started_at && !e.finished_at);
  return { start: Math.min(...starts), end: Math.max(...ends, ...starts, open ? nowMs : 0) };
}

/** `datetime-local` value (no zone) -> ISO string in UTC, or "" when empty or invalid. */
export function localInputToIso(value) {
  if (!value) return "";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "" : d.toISOString();
}

export function buildQuery(params) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== "" && v !== null && v !== undefined) q.set(k, v);
  const s = q.toString();
  return s ? `?${s}` : "";
}
