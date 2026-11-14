# OBS – Scope & Capability Checklist (generic, áp dụng cho mọi service)

OBS (Observability service) là nền tảng dùng chung cho **mọi service/hệ thống** đăng ký vào nó, không gắn riêng với một sản phẩm nào. OBS phải trả lời được: **chuyện gì xảy ra, ở đâu, ảnh hưởng đến đâu, cần xử lý gì** – không chỉ hiển thị CPU/RAM hay trạng thái service. Tin360 chỉ là một tenant/ví dụ (xem mục 4.5).

## 1. Nguyên tắc phạm vi

**In scope**
- Quản lý vòng đời & trạng thái: service, instance, worker, job, workflow, incident.
- Thu thập & liên kết dữ liệu: heartbeat, event, error, log, trace, metric hạ tầng.
- Truy vết nguyên nhân: Job → Workflow → Trace → Logs.
- Báo cáo độ tin cậy: success rate, uptime, MTTR/MTBF, SLO, capacity.

**Out of scope (non-goals)**
- OBS **không** thực thi/điều phối workflow – chỉ theo dõi và phản ánh trạng thái (event-driven).
- OBS **không** phải hệ thống queue/scheduler của bất kỳ service nào được giám sát.
- OBS chết **không được** làm gián đoạn service nghiệp vụ (SDK fail-safe, non-blocking, buffer local).
- Không thay thế APM/log backend chuyên dụng; OBS tích hợp/tham chiếu tới chúng.
- Không chứa logic nghiệp vụ riêng của một hệ thống (vd. Tin360); mọi thứ domain-specific phải cấu hình được.

**Nguyên tắc generic (multi-service)**
- Service/worker/workflow tự đăng ký qua SDK/API chuẩn; không hard-code tên service hay step.
- Mô hình dữ liệu dùng chung: `service`, `instance`, `worker`, `job`, `workflow` + `step`, `incident`, `trace_id`; thêm trường `tenant/system` để tách nhiều hệ thống.
- Định nghĩa workflow, ngưỡng health, SLO, retention cấu hình theo từng service/hệ thống.
- Mọi câu hỏi trong checklist phải trả lời được cho bất kỳ service nào đã tích hợp SDK.

**Trạng thái đáp ứng của mỗi câu hỏi**
- `SUPPORTED` – có dữ liệu và trả lời được.
- `PARTIAL` – có dữ liệu nhưng chưa đủ để kết luận.
- `NOT_SUPPORTED` – chưa có dữ liệu/chức năng.
- `NOT_APPLICABLE` – không thuộc phạm vi.

**Mức ưu tiên**: P0 (bắt buộc) · P1 (tìm nguyên nhân & tối ưu) · P2 (nâng cao).

## 2. Hiện trạng theo nhóm (sơ bộ)

| Nhóm | Hiện trạng |
|---|---|
| System Overview | Đã có nền tảng |
| Service Monitoring | Đã có nền tảng |
| Worker Monitoring | Đã có nền tảng |
| Job Monitoring | Đã có nền tảng |
| Workflow Monitoring | Đã có nền tảng |
| Incident Management | Đã có nền tảng |
| Error Monitoring | Một phần |
| Infrastructure | Một phần |
| Distributed Tracing | Thiếu correlation thực tế (SDK chưa gửi `trace_id` vào Job) |
| Logging | Chưa tích hợp đầy đủ |
| Reliability & Recovery | Một phần |
| Capacity Planning | Chưa có |

**Nhận định:** nền tảng vòng đời service/worker/job/workflow/incident đã tốt. Thiếu lớn nhất không phải thêm CRUD/dashboard mà là **kết nối dữ liệu** để trả lời câu hỏi nguyên nhân (trace_id, log correlation, telemetry hạ tầng).

## 3. Ưu tiên triển khai

**P0 – Phải trả lời được**
1. Service nào đang lỗi?
2. Worker nào lỗi hoặc mất heartbeat?
3. Job nào đang RUNNING / FAILED / stuck?
4. Workflow nào đang thất bại?
5. Workflow thất bại ở service/step nào?
6. Job/workflow thất bại vì lý do gì?
7. Incident nào đang OPEN?
8. Một job truy ra được worker, service, workflow, lịch sử xử lý?
9. Khi service hồi phục, trạng thái được cập nhật đúng?
10. OBS gặp sự cố mà không làm gián đoạn các service được giám sát?

**P1 – Tìm nguyên nhân & tối ưu**
1. Service nào có error rate cao nhất?
2. Job nào có processing time cao bất thường?
3. Workflow step nào là bottleneck?
4. Truy vết Job → Workflow → Trace → Logs.
5. CPU/RAM/Disk từng host.
6. Queue backlog có đang tăng?
7. Incident nào tái diễn?
8. Tỷ lệ thành công từng workflow.

**P2 – Nâng cao**
1. Capacity hiện tại đáp ứng bao nhiêu workload?
2. Tăng 2–5× workload thì nghẽn ở đâu?
3. Dự đoán khi nào hết tài nguyên.
4. SLO từng service có đạt?
5. Xu hướng lỗi theo tuần/tháng.
6. Tự động phát hiện anomaly.
7. Đánh giá tác động khi một service ngừng.

## 4. Capability Checklist

Cột `Status` điền sau khi đánh giá; `P` = ưu tiên.

### 4.1 System Overview

| ID | Câu hỏi | P | Status |
|---|---|---|---|
| SYS-01 | Toàn hệ thống có bao nhiêu service? | P0 | |
| SYS-02 | Bao nhiêu service HEALTHY / DEGRADED / UNHEALTHY / STOPPED? | P0 | |
| SYS-03 | Bao nhiêu service instance đang hoạt động? | P0 | |
| SYS-04 | Bao nhiêu worker đang hoạt động? | P0 | |
| SYS-05 | Bao nhiêu job QUEUED / RUNNING / COMPLETED / FAILED? | P0 | |
| SYS-06 | Bao nhiêu workflow đang chạy? | P0 | |
| SYS-07 | Bao nhiêu incident đang OPEN? | P0 | |
| SYS-08 | Thành phần nào có vấn đề nghiêm trọng nhất? | P0 | |
| SYS-09 | Tình trạng đang tốt lên hay xấu đi so với kỳ trước? | P1 | |
| SYS-10 | Hệ thống còn đủ khả năng xử lý workload? | P2 | |

### 4.2 Service Monitoring

| ID | Câu hỏi | P | Status |
|---|---|---|---|
| SVC-01 | Service nào đang chạy? | P0 | |
| SVC-02 | Service nào UNHEALTHY / DEGRADED? | P0 | |
| SVC-03 | Service nào không gửi heartbeat? | P0 | |
| SVC-04 | Service nào hay restart / mất kết nối? | P1 | |
| SVC-05 | Service nào có error rate cao nhất? | P1 | |
| SVC-06 | Service nào có response time cao nhất? | P1 | |
| SVC-07 | Service nào tiêu thụ nhiều CPU/RAM? | P1 | |
| SVC-08 | Một service có bao nhiêu instance? | P0 | |
| SVC-09 | Các instance cùng service có đồng nhất trạng thái? | P1 | |
| SVC-10 | Service bắt đầu gặp vấn đề từ khi nào? | P0 | |
| SVC-11 | Lần hoạt động thành công cuối cùng khi nào? | P0 | |
| SVC-12 | Service từng gặp incident nào? | P1 | |

### 4.3 Worker Monitoring

| ID | Câu hỏi | P | Status |
|---|---|---|---|
| WRK-01 | Hiện có bao nhiêu worker? | P0 | |
| WRK-02 | Worker nào IDLE / BUSY / UNHEALTHY / STOPPED? | P0 | |
| WRK-03 | Worker nào đang xử lý job nào? | P0 | |
| WRK-04 | Worker nào bị treo / mất heartbeat? | P0 | |
| WRK-05 | Worker nào thường xuyên lỗi? | P1 | |
| WRK-06 | Worker nào xử lý nhiều job nhất? | P1 | |
| WRK-07 | Thời gian xử lý trung bình từng worker? | P1 | |
| WRK-08 | Worker nào có tỷ lệ FAILED cao nhất? | P1 | |
| WRK-09 | Worker có vượt capacity không? | P1 | |
| WRK-10 | Worker lỗi ảnh hưởng job nào? | P0 | |
| WRK-11 | Worker đã hồi phục sau incident chưa? | P0 | |
| WRK-12 | Worker tồn tại nhưng không nhận job? | P1 | |

### 4.4 Job Monitoring (nhóm quan trọng nhất: "một công việc cụ thể đã xảy ra chuyện gì?")

| ID | Câu hỏi | P | Status |
|---|---|---|---|
| JOB-01 | Job đang ở trạng thái nào? | P0 | |
| JOB-02 | Job được tạo lúc nào? | P0 | |
| JOB-03 | Job bắt đầu / kết thúc lúc nào? | P0 | |
| JOB-04 | Job chạy bao lâu? | P0 | |
| JOB-05 | Job do service và worker nào xử lý? | P0 | |
| JOB-06 | Job FAILED vì lý do gì? | P0 | |
| JOB-07 | Job retry bao nhiêu lần? | P0 | |
| JOB-08 | Job đang stuck ở đâu? | P0 | |
| JOB-09 | Job có exception/error không? | P0 | |
| JOB-10 | Xem được lịch sử đổi trạng thái của job? | P0 | |
| JOB-11 | Job thuộc workflow nào? | P0 | |
| JOB-12 | Truy cập được trace/log liên quan job? | P1 | |
| JOB-13 | Job nào xử lý lâu bất thường? | P1 | |
| JOB-14 | Job nào đã tạo nhưng chưa được worker nhận? | P0 | |
| JOB-15 | Job nào hoàn thành nhưng không có kết quả mong đợi? | P1 | |

### 4.5 Workflow Monitoring

Workflow là chuỗi step đi qua nhiều service, định nghĩa bởi từng hệ thống (OBS không hard-code). Ví dụ (Tin360): News Collection → Story Intelligence → Script → Video Rendering → Video QA → YouTube Integration.

> OBS theo dõi và quản lý **trạng thái** workflow, không thực thi/điều phối.

| ID | Câu hỏi | P | Status |
|---|---|---|---|
| WF-01 | Workflow đang ở trạng thái nào? | P0 | |
| WF-02 | Workflow đã đi qua service nào? | P0 | |
| WF-03 | Workflow đang dừng ở step nào? | P0 | |
| WF-04 | Step nào đang RUNNING? | P0 | |
| WF-05 | Step nào FAILED / TIMED_OUT? | P0 | |
| WF-06 | Step nào mất nhiều thời gian nhất? | P1 | |
| WF-07 | Step nào đã retry? | P1 | |
| WF-08 | Step nào đã hoàn thành? | P0 | |
| WF-09 | Workflow thất bại do service nào? | P0 | |
| WF-10 | Workflow mất tổng cộng bao lâu? | P1 | |
| WF-11 | Xem được timeline toàn bộ workflow? | P1 | |
| WF-12 | Replay / rebuild trạng thái từ event? | P2 | |
| WF-13 | Workflow nào stuck lâu bất thường? | P0 | |
| WF-14 | Workflow nào thất bại nhiều nhất? | P1 | |
| WF-15 | Một workflow ảnh hưởng bao nhiêu job? | P1 | |

### 4.6 Error & Exception Monitoring

| ID | Câu hỏi | P | Status |
|---|---|---|---|
| ERR-01 | Hiện có bao nhiêu lỗi? | P0 | |
| ERR-02 | Lỗi nào xuất hiện nhiều nhất? | P1 | |
| ERR-03 | Lỗi ở service nào? | P0 | |
| ERR-04 | Lỗi ở worker nào? | P0 | |
| ERR-05 | Lỗi liên quan job/workflow nào? | P0 | |
| ERR-06 | Lỗi bắt đầu từ khi nào? | P1 | |
| ERR-07 | Lỗi mới hay đã từng xuất hiện? | P1 | |
| ERR-08 | Tần suất lỗi có đang tăng? | P1 | |
| ERR-09 | Lỗi nào ảnh hưởng nhiều workflow? | P1 | |
| ERR-10 | Xem được stack trace và log liên quan? | P1 | |
| ERR-11 | Lỗi nào đã xử lý, nào còn tồn tại? | P1 | |
| ERR-12 | Lỗi nào cần ưu tiên xử lý trước? | P1 | |

### 4.7 Incident Management

| ID | Câu hỏi | P | Status |
|---|---|---|---|
| INC-01 | Hiện có những incident nào? | P0 | |
| INC-02 | Incident nào đang OPEN? | P0 | |
| INC-03 | Incident bắt đầu từ khi nào? | P0 | |
| INC-04 | Ảnh hưởng service/worker/job nào? | P0 | |
| INC-05 | Nguyên nhân incident? | P0 | |
| INC-06 | Mức độ nghiêm trọng? | P0 | |
| INC-07 | Incident nào trùng nguyên nhân (dedup)? | P1 | |
| INC-08 | Incident đã tự động đóng chưa? | P0 | |
| INC-09 | Incident tồn tại bao lâu? | P0 | |
| INC-10 | Incident nào xảy ra thường xuyên nhất? | P1 | |
| INC-11 | Sự cố nào tái diễn sau khi xử lý? | P1 | |
| INC-12 | Lịch sử incident từng service? | P1 | |

### 4.8 Infrastructure & Performance

> Cần telemetry thực tế từ host/service, không chỉ dựa trên heartbeat registry.

| ID | Câu hỏi | P | Status |
|---|---|---|---|
| INF-01 | CPU hiện tại từng host? | P1 | |
| INF-02 | RAM hiện tại? | P1 | |
| INF-03 | Disk còn bao nhiêu? | P1 | |
| INF-04 | Disk nào sắp đầy? | P1 | |
| INF-05 | Network traffic ở mức nào? | P2 | |
| INF-06 | Service nào tiêu thụ tài nguyên nhiều nhất? | P1 | |
| INF-07 | CPU/RAM có tăng bất thường? | P2 | |
| INF-08 | API response time p50/p95/p99? | P1 | |
| INF-09 | DB connection pool đang dùng bao nhiêu? | P2 | |
| INF-10 | DB query chậm nhất? | P2 | |
| INF-11 | Queue backlog hiện tại? | P1 | |
| INF-12 | Queue đang tăng hay giảm? | P1 | |
| INF-13 | Có thiếu worker capacity? | P1 | |
| INF-14 | Khi nào cần nâng cấp tài nguyên? | P2 | |

### 4.9 Distributed Tracing & Logging

> Hiện thiếu dữ liệu thực tế: SDK chưa gửi `trace_id` vào Job. Đây là **blocker** cho TRACE-04…11 và JOB-12.

| ID | Câu hỏi | P | Status |
|---|---|---|---|
| TRACE-01 | Request/job đi qua những service nào? | P1 | |
| TRACE-02 | Service nào xử lý từng đoạn? | P1 | |
| TRACE-03 | Đoạn nào mất nhiều thời gian nhất? | P1 | |
| TRACE-04 | Truy vết từ Job đến Trace? | P1 | |
| TRACE-05 | Truy vết từ Workflow đến Trace? | P1 | |
| TRACE-06 | Xem log theo `trace_id`? | P1 | |
| TRACE-07 | Tìm log theo `job_id`? | P1 | |
| TRACE-08 | Tìm log theo `workflow_id`? | P1 | |
| TRACE-09 | Xác định request gây lỗi ở service nào? | P1 | |
| TRACE-10 | Phát hiện bottleneck giữa các service? | P1 | |
| TRACE-11 | Xem toàn bộ trace của một workflow? | P1 | |
| TRACE-12 | Phân biệt lỗi application / network / dependency? | P2 | |

### 4.10 Reliability, Capacity & Recovery

| ID | Câu hỏi | P | Status |
|---|---|---|---|
| REL-01 | Hệ thống có đáp ứng SLA/SLO? | P2 | |
| REL-02 | Tỷ lệ job thành công trong 24h? | P1 | |
| REL-03 | Tỷ lệ thành công từng workflow? | P1 | |
| REL-04 | Uptime % từng service? | P1 | |
| REL-05 | MTTR trung bình? | P2 | |
| REL-06 | MTBF? | P2 | |
| REL-07 | Service chết thì thành phần nào bị ảnh hưởng? | P2 | |
| REL-08 | OBS chết, service nghiệp vụ có tiếp tục chạy? | P0 | |
| REL-09 | Telemetry backend chết, dữ liệu có mất? | P0 | |
| REL-10 | Service hoạt động lại, trạng thái có được đồng bộ? | P0 | |
| REL-11 | Có job bị bỏ sót / thất lạc? | P0 | |
| REL-12 | Job nào cần chạy lại? | P0 | |
| REL-13 | Còn đủ capacity cho workload hiện tại? | P2 | |
| REL-14 | Workload tăng 2×/5× thì thành phần nào quá tải trước? | P2 | |
| REL-15 | Dữ liệu monitoring/lifecycle giữ bao lâu (retention)? | P1 | |

## 5. Bước tiếp theo

Biến checklist thành **ma trận QA / Acceptance Criteria**: mỗi câu hỏi gắn với
`API endpoint` · `nguồn dữ liệu` · `dashboard/panel` · `điều kiện kiểm chứng` · `Status`.

Thứ tự đề xuất: (1) đánh giá Status cho toàn bộ P0; (2) sửa blocker `trace_id` trong SDK; (3) bổ sung telemetry hạ tầng + queue backlog; (4) capacity/SLO (P2).

## 6. Ghi chú chỉnh sửa so với bản gốc

- Chuyển sang dạng generic cho mọi service (Tin360 chỉ làm ví dụ); thêm mục **Out of scope** và nguyên tắc fail-safe (OBS không được làm gián đoạn service nghiệp vụ nào).
- Gắn mức ưu tiên P0/P1/P2 trực tiếp lên từng ID (bản gốc chỉ có danh sách riêng).
- Đưa REL-08/09/10/11/12 lên P0 vì khớp các câu P0 "OBS gặp sự cố không làm gián đoạn" và "service hồi phục thì trạng thái đúng".
- SYS-10 và REL-13 trùng ý (capacity) → giữ cả hai, nhưng cùng đánh giá P2.
- Thêm cột `Status` để theo dõi mức đáp ứng.
