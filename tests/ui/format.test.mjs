import assert from "node:assert/strict";
import { test } from "node:test";
import {
  barGeometry, buildQuery, formatAge, formatDuration, localInputToIso, statusClass, timelineSpan,
} from "../../app/ui/static/format.js";

test("durations read naturally at every scale", () => {
  assert.equal(formatDuration(null), "–");
  assert.equal(formatDuration(250), "250 ms");
  assert.equal(formatDuration(1500), "1.5 s");
  assert.equal(formatDuration(42000), "42 s");
  assert.equal(formatDuration(125000), "2 min 5 s");
  assert.equal(formatDuration(3_900_000), "1 h 5 min");
});

test("ages", () => {
  assert.equal(formatAge(0.2), "just now");
  assert.equal(formatAge(45), "45 s ago");
  assert.equal(formatAge(600), "10 min ago");
  assert.equal(formatAge(7200), "2 h ago");
  assert.equal(formatAge(null), "–");
});

test("status classes: failures are bad, retries are warnings, unknown is neutral", () => {
  for (const s of ["FAILED", "UNHEALTHY", "TIMED_OUT", "QUARANTINED"]) assert.equal(statusClass(s), "bad");
  for (const s of ["COMPLETED", "HEALTHY", "IDLE"]) assert.equal(statusClass(s), "good");
  for (const s of ["RETRYING", "DEGRADED", "DRAINING"]) assert.equal(statusClass(s), "warn");
  for (const s of ["RUNNING", "BUSY", "QUEUED"]) assert.equal(statusClass(s), "active");
  assert.equal(statusClass("SOMETHING_NEW"), "neutral");
  assert.equal(statusClass(undefined), "neutral");
});

test("timeline bars are placed proportionally and never leave the track", () => {
  const entries = [
    { started_at: "2026-11-09T12:00:00Z", finished_at: "2026-11-09T12:00:10Z" },
    { started_at: "2026-11-09T12:00:05Z", finished_at: "2026-11-09T12:00:07Z" },
    { started_at: null, finished_at: null },
  ];
  const span = timelineSpan(entries);
  assert.equal(span.end - span.start, 10000);
  assert.deepEqual(barGeometry(entries[0], span.start, span.end), { left: 0, width: 100 });
  assert.deepEqual(barGeometry(entries[1], span.start, span.end), { left: 50, width: 20 });
  assert.equal(barGeometry(entries[2], span.start, span.end), null);
});

test("a zero-length step still gets a visible bar, and an open step runs to now", () => {
  const instant = { started_at: "2026-11-09T12:00:05Z", finished_at: "2026-11-09T12:00:05Z" };
  const geo = barGeometry(instant, Date.parse("2026-11-09T12:00:00Z"), Date.parse("2026-11-09T12:00:10Z"));
  assert.ok(geo.width >= 0.6 && geo.left + geo.width <= 100);
  const open = [{ started_at: "2026-11-09T12:00:00Z", finished_at: null }];
  const now = Date.parse("2026-11-09T12:00:30Z");
  assert.equal(timelineSpan(open, now).end, now);
  assert.equal(timelineSpan([{ started_at: null }]), null);
});

test("filters: empty values are dropped from the query and times become UTC", () => {
  assert.equal(buildQuery({ a: "x", b: "", c: null, d: 0 }), "?a=x&d=0");
  assert.equal(buildQuery({}), "");
  assert.equal(localInputToIso(""), "");
  assert.equal(localInputToIso("not a date"), "");
  assert.match(localInputToIso("2026-11-09T12:00"), /^2026-11-09T\d\d:00:00\.000Z$/);
});
