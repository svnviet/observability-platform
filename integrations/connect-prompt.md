# Prompt: kết nối một service vào OBS qua svn-obskit (từ cài đặt đến chạy)

Dán nguyên khối dưới đây vào Claude Code đang mở ở **repo của service cần kết nối**. Thay `<...>` trước khi gửi.
Không dán API key vào prompt; để agent hỏi hoặc tự đọc từ nơi bạn lưu secret.

---

```text
Hãy kết nối service trong repo này vào nền tảng OBS bằng SDK svn-obskit, làm từ cài đặt đến chạy được và kiểm chứng.

Thông tin:
- OBS URL: https://obs.vimob.sbs
- service_name: <tên service, cố định, vd. news-crawler>
- environment: <production | staging | development>
- OBSKIT_INSTANCE_ID: <cố định cho mỗi process/pod, vd. news-crawler-1; KHÔNG dùng pid hay giá trị ngẫu nhiên>
- API key OBS: nằm ở <nơi lưu secret>. Đừng ghi key vào code, prompt, log hay file được commit.

Làm theo thứ tự, dừng và báo nếu một bước thất bại:

1. CÀI ĐẶT
   - Thêm `svn-obskit>=0.2.0` vào file dependency của repo (requirements*.txt / pyproject.toml), kèm extras nếu repo cần:
     `svn-obskit[otel,metrics]` (trace + Prometheus). Python >= 3.11. Cài vào môi trường của repo.
   - Chạy `obskit init-claude` ở gốc repo (hoặc `python -m svn_obskit init-claude`). Lệnh này chép skill `obs-integration` vào
     `.claude/skills/` và thêm khối hướng dẫn vào CLAUDE.md. Sau đó ĐỌC `.claude/skills/obs-integration/SKILL.md` và
     `recipes.md` và làm theo; đó là nguồn hướng dẫn chính cho các bước 2-4.

2. PHÂN LOẠI (trước khi sửa code)
   Quét repo và lập bảng: service/process triển khai được, worker (consumer/loop/thread nhận việc), job (một đơn vị việc có một
   kết quả), workflow/step (quy trình nhiều bước), điểm gọi service khác, nơi ghi log. Mục nào "không có" phải là kết luận
   sau khi đã tìm, không phải bỏ qua. Cho tôi xem bảng này trước khi viết code.

3. TÍCH HỢP (chỉ các lớp mà service thật sự có)
   - Cấu hình qua biến môi trường, thêm vào `.env.example` (không có giá trị thật):
     OBSKIT_PLATFORM_URL, OBSKIT_API_KEY, OBSKIT_ENVIRONMENT, OBSKIT_SERVICE_VERSION, OBSKIT_INSTANCE_ID,
     và tùy chọn OBSKIT_OUTBOX_PATH, OBSKIT_OTLP_ENDPOINT, OBSKIT_METRICS_PORT.
   - Khởi tạo `Observability("<service_name>").initialize()` một lần mỗi process và `shutdown()` khi thoát.
   - Service HTTP: thêm ObservabilityMiddleware, mount /metrics, giữ route /health (OBS probe nó; trả 2xx + JSON status).
   - Worker/job: `obs.worker(...)` cho mỗi vòng nhận việc, `worker.job(job_id, workflow_run_id=...)` cho mỗi việc.
   - Workflow: `tracker.workflow(...)` và `wf.step(...)`; retry là attempt của cùng step. Qua queue/HTTP/process khác thì
     truyền context (xem recipes.md), dùng cùng một run id.
   - Log: dùng `logging.getLogger(__name__)` sau initialize(); không thêm logger thứ hai; không log bí mật.
   - Không bọc logic nghiệp vụ trong try/except chỉ vì OBS; SDK không bao giờ ném lỗi ra ngoài.

4. CHẠY VÀ KIỂM CHỨNG (chạy thật, đừng suy đoán)
   Đặt OBSKIT_PLATFORM_URL và OBSKIT_API_KEY trong môi trường chạy, khởi động service, rồi:
   a. `curl https://obs.vimob.sbs/services` có service này, trạng thái HEALTHY, đúng instance id cố định.
   b. Chạy một job thật: `curl "https://obs.vimob.sbs/jobs?external_job_id=<id>"` thấy RUNNING rồi COMPLETED, có worker và trace_id;
      cho một job lỗi cố ý: thấy FAILED kèm error.
   c. Chạy một workflow (nếu có): `curl "https://obs.vimob.sbs/workflow-runs?workflow_id=<id>"` thấy các step; ép retry thì thấy attempt 2.
   d. Một dòng log trong job parse được JSON và có job_id, trace_id (và workflow_run_id nếu có workflow).
   e. Đổi OBSKIT_PLATFORM_URL sang host không tồn tại: service vẫn khởi động và chạy bình thường, không chậm.
   f. Restart service: không sinh instance trùng (instance id vẫn là giá trị cố định).

5. BÁO CÁO
   Bảng: khái niệm -> tìm thấy ở file nào -> đã báo bằng API nào -> cách đã kiểm chứng. Nêu rõ mục nào bỏ qua và vì sao,
   và các lệnh/test đã chạy cùng kết quả thật. Chạy test và lint của repo; nếu không chạy được thì nói rõ.

Ràng buộc: không commit API key; không đổi hành vi nghiệp vụ; mỗi thay đổi nhỏ và có thể review; không push nếu tôi chưa bảo.
```

---

## Ghi chú cho người dùng prompt

- Đọc dữ liệu từ OBS (`GET`) không cần key; chỉ việc ghi (SDK gửi event/heartbeat) cần `OBSKIT_API_KEY` do người quản lý OBS cấp.
- `obskit init-claude` có `--force` (thay bản cũ), `--user` (cài vào `~/.claude`), `--no-claude-md` (không đụng CLAUDE.md).
- Service chưa dùng Python: skill đi kèm SDK chỉ cho Python; dùng skill `obs-integration` trong
  `integrations/claude-skill/` của repo OBS (hợp đồng HTTP, không cần SDK).
- SDK không gửi trạng thái `QUEUED` cho job; nếu cần thấy thời gian chờ queue, service tự POST `/jobs` lúc enqueue.
