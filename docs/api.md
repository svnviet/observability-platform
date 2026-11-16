# Tài liệu API

Base URL production: `https://obs.vimob.sbs`. Không có tiền tố phiên bản (ADR-0006). Danh sách dưới đây trích từ OpenAPI
của bản đang chạy (`GET /openapi.json`, cần key).

## Quy ước chung

**Xác thực** (ADR-0005): header `X-API-Key: <key>`.

| Loại request | Cần key? |
|---|---|
| `GET`, `HEAD`, `OPTIONS` (mọi route dữ liệu) | **Không** |
| `POST`, `PUT`, `PATCH`, `DELETE` | **Có** |
| `GET /health`, giao diện `/`, `/ui/static/*` | Không |
| `GET /openapi.json`, `GET /auth/check` | **Có** (cả `GET`) |
| `/docs`, `/redoc` | Tắt (trả 404) |

**Mã lỗi:** `401` thiếu hoặc sai key khi ghi; `404` không tìm thấy (`{"detail": "<thứ> not found"}`); `422` sai dữ liệu
(chuẩn FastAPI); sự kiện sai trong `/events` **không** trả 422 mà trả `outcome: REJECTED` (xem mục Events).

**Phân trang:** `limit` (mặc định 50, tối đa 200; cấu hình `OBSKIT_PLATFORM_DEFAULT_PAGE_SIZE`, `_MAX_PAGE_SIZE`) và `offset`.
Phản hồi dạng trang: `{"items": [...], "total": N, "limit": N, "offset": N}`.

**Định dạng:** JSON, thời gian ISO 8601 có múi giờ, ID là UUID (trừ các ID do service tự đặt).

---

## Hệ thống

| Method | Path | Mô tả |
|---|---|---|
| GET | `/health` | `{"status":"ok"}` — mở, dùng cho liveness |
| GET | `/auth/check` | **Cần key.** `{"ok": true}`; giao diện dùng để kiểm tra key |
| GET | `/openapi.json` | **Cần key.** Schema OpenAPI |

## Services

| Method | Path | Body / Query | Phản hồi |
|---|---|---|---|
| POST | `/services/register` | `ServiceRegisterIn` | `ServiceRegisterOut` |
| GET | `/services` | | `[ServiceRead]` |
| GET | `/services/{service_id}` | | `ServiceDetail` (kèm `instances`) |
| POST | `/services/{service_id}/heartbeat` | `HeartbeatIn` | `ServiceRegisterOut` |
| PUT | `/services/{service_id}/instances/{instance_id}/health-url` | `HealthUrlIn` | `HealthUrlOut` |
| PATCH | `/services/{service_id}` | `ServiceUpdateIn` | `ServiceDetail` |
| DELETE | `/services/{service_id}` | `delete_jobs` (mặc định false) | `DeleteResult` |
| PATCH | `/services/{service_id}/instances/{instance_id}` | `InstanceUpdateIn` | `InstanceRead` |
| DELETE | `/services/{service_id}/instances/{instance_id}` | | `DeleteResult` |

- `ServiceRegisterIn`: `service_name`*, `instance_id`*, `environment` (mặc định `unknown`), `service_version`, `hostname`, `metadata`.
  Đăng ký lại cùng `(service_name, environment)` + `instance_id` là **upsert**: cập nhật bản ghi cũ, đặt `HEALTHY`, làm mới heartbeat,
  gộp `metadata`.
- `HeartbeatIn`: `instance_id`*, `stopping` (mặc định false). `stopping: true` → instance `STOPPED`. Instance chưa đăng ký → `404`.
- `HealthUrlIn`: `health_url` (`http://` hoặc `https://`, ≤ 500 ký tự) hoặc `null` để dừng probe. Sai scheme → `422`. Instance lạ → `404`.
- **Sửa** (`PATCH`, cần key): chỉ field được gửi mới đổi. `ServiceUpdateIn`: `version`, `metadata`. `InstanceUpdateIn`: `hostname`,
  `metadata` (`metadata.health_url` phải là `http(s)://`, sai → `422`). `metadata` được **gộp** vào giá trị cũ; key có giá trị `null` bị xóa.
  Tên và environment của service là định danh, **không sửa được**: đăng ký lại với tên mới.
- **Xóa** (`DELETE`, cần key) trả `DeleteResult` (`deleted`, `instances`, `workers`, `jobs`, `events`):
  - Instance: xóa được ở mọi trạng thái, kèm worker và lịch sử probe của nó. Tiến trình còn chạy sẽ tự đăng ký lại ở heartbeat kế tiếp.
  - Service: `409` nếu còn instance chưa `STOPPED` (dừng hoặc xóa instance trước); `409` nếu còn job, trừ khi `delete_jobs=true`
    (khi đó job và lịch sử job của service bị xóa theo). Incident và workflow step được giữ, chỉ mất liên kết tới service.
  - Job và incident luôn giữ lịch sử khi xóa instance/worker; chỉ mất liên kết tới worker đã xóa.
- `ServiceDetail`, `InstanceRead` và `WorkerRead` có thêm `metadata`.
- `ServiceRead.status`: `HEALTHY` / `DEGRADED` / `UNHEALTHY` / `STOPPED` / `NO_INSTANCES` (quy tắc ở `data-model.md`).

## Workers

| Method | Path | Body / Query | Phản hồi |
|---|---|---|---|
| POST | `/workers/register` | `WorkerRegisterIn` | `WorkerRead` |
| GET | `/workers` | `status`, `service`, `limit`, `offset` | `[WorkerRead]` |
| GET | `/workers/{worker_id}` | | `WorkerRead` |
| POST | `/workers/{worker_id}/heartbeat` | `WorkerHeartbeatIn` | `WorkerRead` |
| POST | `/workers/{worker_id}/status` | `WorkerStatusIn` | `WorkerRead` |
| PATCH | `/workers/{worker_id}` | `WorkerUpdateIn` | `WorkerRead` |
| DELETE | `/workers/{worker_id}` | | `DeleteResult` |

- `WorkerRegisterIn`: `service_name`*, `instance_id`*, `worker_name`*, `environment`, `service_version`, `worker_type`, `capacity` (≥1), `metadata`.
  Đăng ký cũng upsert instance. Trạng thái ban đầu `REGISTERED`.
- `WorkerHeartbeatIn`: `status` (tùy chọn), `current_job_id` (tùy chọn). `WorkerStatusIn`: `status`*, `current_job_id`.
- `WorkerUpdateIn`: `worker_type`, `capacity` (≥1), `metadata` (gộp, `null` xóa key). Xóa worker giữ nguyên job của nó.
- `WorkerRead` có `heartbeat_age_s`, `current_job_id`, `capacity`.

## Events (nhật ký sự kiện workflow)

| Method | Path | Mô tả |
|---|---|---|
| POST | `/events` | Một sự kiện (body là object thô) → `IngestResult` |
| POST | `/events/batch` | `{"events": [object, ...]}`, 1–1000 sự kiện → `EventBatchResult` |
| POST | `/events/replay` | `{"workflow_run_ids": [...]}` — áp lại sự kiện theo `occurred_at` |
| GET | `/events/{event_id}` | Một sự kiện đã lưu |
| GET | `/events/rejected` | Trang các sự kiện bị từ chối |

Hợp đồng sự kiện (`event_version` hiện chỉ hỗ trợ `1`):

```json
{
  "event_id": "evt-123",
  "event_type": "STEP_FAILED",
  "event_version": 1,
  "occurred_at": "2026-11-14T10:00:00Z",
  "source":  { "service_name": "video-service", "instance_id": "i-1", "worker_id": "w-1",
               "environment": "production", "service_version": "1.2.0" },
  "context": { "workflow_id": "wf-001", "workflow_run_id": "run-001", "correlation_id": "c-1",
               "trace_id": "abc123", "step_id": "render", "step_attempt_id": "render-1" },
  "data":    { "workflow_name": "video", "step_name": "Render", "attempt_number": 1,
               "will_retry": true, "error": { "type": "TimeoutError", "message": "slow" } }
}
```

Quy tắc: `event_id`, `event_type`, `occurred_at` (có múi giờ), `source.service_name`, `context.workflow_id`,
`context.workflow_run_id` bắt buộc; sự kiện `STEP_*` bắt buộc `context.step_id`; khóa lạ trong `data` được giữ.

`IngestResult.outcome`: `ACCEPTED` (kèm `disposition`: `APPLIED`/`STALE`/`QUARANTINED`), `DUPLICATE` (cùng `event_id` đã có;
idempotent, không đổi gì), `REJECTED` (ghi vào `rejected_events`, **HTTP vẫn 200**). Một sự kiện hỏng trong batch không làm hỏng
cả batch. `EventBatchResult` có `accepted`, `duplicates`, `rejected`.

## Workflows

| Method | Path | Mô tả |
|---|---|---|
| POST | `/workflow-runs` | Tạo run tường minh, idempotent theo `run_id` (`WorkflowRunCreateIn`) |
| GET | `/workflow-runs` | Lọc: `workflow_id`, `run_key`, `status`, `service`, `started_after`, `started_before` + phân trang |
| GET | `/workflow-runs/{run_id}` | `WorkflowRunDetail` (kèm `steps`, mỗi bước có `attempts`) |
| GET | `/workflow-runs/{run_id}/steps` | `[StepRead]` |
| GET | `/workflow-runs/{run_id}/timeline` | `[TimelineEntry]` — bước và lần thử theo thời gian, kèm `duration_ms` |
| GET | `/workflow-runs/{run_id}/events` | Trang `EventRead` của run |
| DELETE | `/workflow-runs/{run_id}` | Xóa run cùng step, attempt và nhật ký sự kiện → `DeleteResult`. Run chưa kết thúc: `409` trừ khi `force=true` |
| POST | `/workflows` | Tạo định nghĩa (`WorkflowDefinitionIn`) |
| GET | `/workflows` | `[WorkflowDefinitionRead]` |

`run_id` là UUID của platform (không phải `run_key`). Run và attempt có `trace_url` khi cấu hình `OBSKIT_PLATFORM_JAEGER_URL`.

## Jobs

| Method | Path | Mô tả |
|---|---|---|
| POST | `/jobs` | Upsert trạng thái job (`JobUpsertIn`) → `JobRead` |
| GET | `/jobs` | Lọc: `status`, `service`, `external_job_id` (khớp chính xác) + phân trang |
| GET | `/jobs/{job_id}` | `JobRead` |
| GET | `/jobs/{job_id}/events` | `[JobEventRead]` — mọi lần đổi trạng thái, cũ trước |
| GET | `/jobs/{job_id}/timeline` | `JobTimeline`: `job`, `events`, `queued_s`, `running_s`, `total_s` |
| GET | `/jobs/{job_id}/observability` | `JobObservability`: link tới trace, log, metric |

- `JobUpsertIn`: `service_name`*, `external_job_id`*, `status`* (`QUEUED|RUNNING|COMPLETED|FAILED|CANCELLED`), `environment`,
  `instance_id` + `worker_name` (để gắn worker), `workflow_run_key`, `trace_id`, `metadata`, `error`.
- Job kết thúc thì cố định: cập nhật sau đó không đổi trạng thái và không ghi sự kiện.
- `job_id` trong đường dẫn là **UUID của platform**; tìm theo ID của service bằng `GET /jobs?external_job_id=...`.
- `JobObservability`: `trace.url` (từ `trace_id` của job hoặc của workflow run + `OBSKIT_PLATFORM_JAEGER_URL`),
  `logs.url` (từ `OBSKIT_PLATFORM_LOGS_URL_TEMPLATE`), `metrics.url` (từ `..._METRICS_URL_TEMPLATE`, nếu không có thì URL Perses/Prometheus).
  Mỗi link có `available: bool`; thiếu giá trị cho một placeholder thì link không khả dụng.

## Observability links (service, worker, workflow run, incident)

| Method | Path | Phản hồi |
|---|---|---|
| GET | `/services/{service_id}/observability` | `EntityObservability` |
| GET | `/workers/{worker_id}/observability` | `EntityObservability` |
| GET | `/workflow-runs/{run_id}/observability` | `EntityObservability` |
| GET | `/incidents/{incident_id}/observability` | `EntityObservability` (kèm khoảng thời gian ≤ 24 giờ) |

`EntityObservability`: `entity` (`type`, `id`), `correlation` (các ID mà backend telemetry dùng: `service`, `environment`, `instance`,
`worker`, `workflow_id`, `workflow_run_id`, `trace_id`), `links` (`logs`, `trace`, `metrics`, `dashboard`, mỗi cái có `available`) và
`capabilities` (cờ bool tương ứng). Chỉ trả link, không trả dữ liệu log/trace/metric. Link dựng từ template cấu hình
(`OBSKIT_PLATFORM_LOGS_URL_TEMPLATE`, `..._METRICS_URL_TEMPLATE`, `..._DASHBOARD_URL_TEMPLATE`, `..._JAEGER_URL`); thiếu giá trị cho một
placeholder thì link không khả dụng. Placeholder: `{service} {environment} {instance} {worker} {workflow_id} {workflow_run_id}
{trace_id}`, và `{from} {to}` (epoch mili giây) cho incident. Job có route riêng `GET /jobs/{job_id}/observability`.

## Incidents

| Method | Path | Mô tả |
|---|---|---|
| GET | `/incidents` | Lọc: `status` (`OPEN|RESOLVED`), `severity` + phân trang |
| POST | `/incidents/{incident_id}/resolve` | Đóng incident thủ công → `IncidentRead` (`404` nếu không có) |

Incident tự mở khi: instance/worker mất heartbeat; workflow kết thúc `FAILED`/`TIMED_OUT`; probe health thất bại liên tiếp.
Tự đóng khi điều kiện hết (heartbeat trở lại, replay làm run không còn thất bại, probe thành công).

## Monitoring

| Method | Path | Query | Phản hồi |
|---|---|---|---|
| GET | `/monitoring/overview` | | `OverviewRead` (số service/instance/worker/workflow/job/incident/sự kiện bị từ chối) |
| GET | `/monitoring/services` | | `[ServiceRead]` |
| GET | `/monitoring/workers` | `status`, `service`, `limit`, `offset` | `[WorkerRead]` |
| GET | `/monitoring/queues` | | `[QueueStat]` theo service: queued/running/completed/failed, `oldest_queued_age_s` |
| GET | `/monitoring/errors` | `window_hours` (1–2160, mặc định 24), `limit` (1–500) | `[ErrorGroup]` nhóm theo loại lỗi, service, workflow |
| GET | `/monitoring/metrics` | `window_hours` | `MetricSummary` |
| GET | `/monitoring/links` | | `LinksRead` (URL Jaeger/Perses/Prometheus đã cấu hình) |
| POST | `/monitoring/scan` | | **Cần key.** Chạy quét heartbeat ngay → `ScanResult` |
| GET | `/monitoring/infra/instances` | `window_hours` (1–720, mặc định 24) | `[InfraInstance]` |
| GET | `/monitoring/infra/hosts` | `window_hours` | `[InfraHost]` |

`InfraInstance`: `state` (`UP`/`DOWN`/`UNKNOWN`), `checks`, `uptime_pct`, `latency_p50_ms`, `latency_p95_ms`, `down_since`,
`outages[]` (một outage = ít nhất `OBSKIT_PLATFORM_HEALTH_FAIL_THRESHOLD` lần probe lỗi liên tiếp), `system_latest|p95|peak`.
`InfraHost`: gộp theo `hostname`, kèm `findings[]` (ví dụ CPU p95 ≥ 80%, bộ nhớ ≥ 85%, đĩa ≥ 85%, có outage, nhiều service dùng chung host).

## Hợp đồng `/health` của service được probe

Platform gọi `GET <health_url>` mỗi `OBSKIT_PLATFORM_HEALTH_PROBE_INTERVAL_S` giây (mặc định 30). HTTP 2xx là UP; một `status`
trong body thuộc `down|error|fail|failed|unhealthy` là DOWN. Không theo redirect; body tối đa 64 KB; timeout mặc định 5 giây.
Có thể trả các số sau ở cấp ngoài cùng hoặc dưới `"system"` (khóa khác bị bỏ qua): `cpu_percent`, `memory_percent`,
`disk_percent`, `load_1m`, `cpu_count`, `memory_total_mb`, `memory_used_mb`, `disk_total_gb`, `disk_used_gb`,
`process_cpu_percent`, `process_memory_mb`, `active_requests`, `queue_depth`.

## Ví dụ nhanh

```bash
K=<api key>; B=https://obs.vimob.sbs
# đọc không cần key
curl $B/services
curl "$B/jobs?external_job_id=job-123"
# ghi cần key
curl -X POST $B/services/register -H "X-API-Key: $K" -H 'Content-Type: application/json' \
  -d '{"service_name":"demo","instance_id":"demo-1","environment":"test","metadata":{"health_url":"https://demo.example/health"}}'
```
