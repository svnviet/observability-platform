# Observability Correlation – thiết kế liên kết telemetry

**Nguyên tắc:** Service / Worker / Job / Workflow / Incident là *thực thể vận hành* (Operational Entities) trong
PostgreSQL của OBS. OBS **không lưu log, trace, metric**; nó lưu **định danh ổn định + ngữ cảnh liên kết + khoảng
thời gian** rồi dẫn link sang backend chuyên trách (ADR-0002, ADR-0012):

| Dữ liệu | Backend | Khóa liên kết |
|---|---|---|
| Trạng thái vận hành, lifecycle | OBS PostgreSQL | (nguồn sự thật) |
| Log | Loki | `trace_id`, `job_id`, `service`, `workflow_run_id` |
| Trace | Jaeger | `trace_id`, `span_id`, `service` |
| Metric | Prometheus | `service`, `instance`, `worker`, `job_type`, `status` |
| Dashboard | Perses | template + biến (`service`, `instance`, `environment`…) |

## 1. Correlation contract (bộ ID dùng xuyên suốt)

| Field | Đại diện | Ghi chú |
|---|---|---|
| `service_id` / `service.name` | Service logic | `service.name` (OTel) phải trùng `services.name` |
| `instance_id` / `service.instance.id` | Một instance | cố định giữa các lần restart |
| `worker_id` | Worker cụ thể | |
| `job_id` (UUID của OBS) | Job trong OBS | **khác** `external_job_id` |
| `external_job_id` | ID job do service đặt | không dùng thay `job_id` |
| `workflow_id` | Loại workflow | |
| `workflow_run_id` | Một lần chạy | **khác** `workflow_id`; thiếu nó không tách được log/trace từng lần chạy |
| `step_id`, `attempt` | Bước và lần thử | |
| `trace_id`, `span_id` | W3C Trace Context | truyền bằng `traceparent` qua HTTP/queue |

**Tên field trong log** là tên mà `svn-obskit` đã phát ra (`service_name`, `instance_id`, `trace_id`, `span_id`, `job_id`,
`worker_id`, `workflow_id`, `workflow_run_id`, `step_id`, `step_attempt_id`, `correlation_id`) và là chuẩn chung; không đổi
sang `obs.*` để khỏi phá log của các service đang chạy. Với OpenTelemetry resource, `service.name` ↔ `service_name`,
`service.instance.id` ↔ `instance_id`.

## 2. Quy tắc

1. Một bộ ID thống nhất; không để mỗi service tự đặt tên khác nhau.
2. Truyền **trace context** (`traceparent`) qua HTTP, queue, worker — không chỉ lưu ID trong DB.
3. **Không** đưa `job_id`, `workflow_run_id`, `trace_id` vào Prometheus label hoặc Loki indexed label (cardinality).
   Metric tổng hợp theo service/instance/worker pool/job type/status; hiệu năng một job xem qua trace và timestamp.
4. **Fail-open:** OBS/Loki/Jaeger/Collector lỗi không được dừng xử lý nghiệp vụ.
5. **Link an toàn:** frontend không gửi LogQL/PromQL tùy ý. Chỉ dùng query template cấu hình sẵn, giá trị được
   URL-encode, có kiểm tra quyền và giới hạn khoảng thời gian.
6. Một workflow **không** giả định một `trace_id`: nhiều job/service ⇒ nhiều trace. Liên kết ở cấp `workflow_run_id`,
   mỗi job/attempt giữ trace riêng.

## 3. Hiện trạng so với thiết kế (đối chiếu code, 2026-11)

| Hạng mục | Trạng thái | Chi tiết |
|---|---|---|
| Không lưu log/metric/trace trong OBS | ✅ đúng thiết kế | chỉ dẫn link |
| `trace_id` ở workflow run, step attempt | ✅ | cột riêng |
| `trace_id` ở job | ✅ (sau khi chạy 0005) | SDK đã gửi `trace_id` trong cập nhật job (sửa ở `svn-obskit`); OBS lưu ở cột `jobs.trace_id` có index (migration 0005, đã viết, **chưa chạy** trên DB thật) |
| `span_id` | ❌ | không có ở bất kỳ bảng/hợp đồng nào |
| `attempt` của job; liên kết job ↔ step | ❌ | job chỉ nối tới run (`workflow_run_key`), không nối tới `step`/`attempt` |
| `instance` của job | ⚠️ | chỉ suy ra qua `worker`; job chưa có worker thì mất instance |
| `incidents` | ⚠️ | có `service_id`, `worker_id`, `workflow_run_id`; thiếu `instance_id`, `job_id` |
| `service_instances.otel_service_name` / host | ❌ | hiện dựa vào quy ước `service.name == services.name` |
| Link resolver | ✅ (trừ instance) | job, service, worker, workflow-run, incident có `/…/observability`; chưa có route riêng cho instance |
| Tập placeholder của log template | ✅ | thêm `{workflow_run_id} {instance} {environment} {from} {to}` (job vẫn dùng `{job_id}`) |
| Dashboard theo biến | ✅ | `OBSKIT_PLATFORM_DASHBOARD_URL_TEMPLATE` với biến `{service} {instance} {worker} {environment} {workflow_id}` |
| `capabilities` | ✅ tương đương | mỗi link có `available` |
| Giới hạn thời gian truy vấn, kiểm soát quyền cho link | ⚠️ | khoảng thời gian của incident bị chặn ≤ 24 giờ; link chỉ từ template, giá trị được URL-encode; đọc vẫn mở (xem README, mục Deviations) |
| Context propagation / SDK (`svn-obskit`) | ➖ ngoài repo này | SDK đã truyền `traceparent` và context (`job_id`, `workflow_run_id`, `step_id`…) và gửi `trace_id` cho job; chưa gửi `span_id` |

**Kết luận:** thiết kế hiện tại **đủ để lưu lifecycle và dẫn link**, và đúng nguyên tắc không chứa telemetry. Chưa đủ
cho mô hình correlation đầy đủ: thiếu `span_id`, cột `trace_id` của job, liên kết job↔step/attempt, resolver cho các
entity khác, dashboard biến hóa và giới hạn truy vấn.

## 4. Thứ tự triển khai

1. **P1 Correlation contract** – chốt bộ ID ở trên (tài liệu + hợp đồng event/job: thêm `span_id`, `attempt`, `step_id` cho job).
2. **P2 SDK** (`svn-obskit`, repo khác) – structured log, OTel propagation, job/workflow context.
3. **P3 Telemetry backends** – Loki, Jaeger, Prometheus, OTel Collector (repo observability-stack).
4. **P4 Link Resolver** – `GET /{services|instances|workers|jobs|workflow-runs|incidents}/{id}/observability`
   với `entity`, `correlation`, `links`, `capabilities`; query template cấu hình, có giới hạn thời gian.
5. **P5 UI** – tab Logs / Traces / Metrics / Dashboard ở trang từng entity.

Migration cho P1/P4 (cột `jobs.trace_id`, `jobs.span_id`, `jobs.attempt`, `jobs.step_id`, `incidents.instance_id`,
`incidents.job_id`) là việc riêng, cần review trước khi chạy trên DB thật.
