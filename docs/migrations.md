# Migration và rollback

Migration là bước **chủ động** (service `migrate` trong `docker-compose.yml`, hoặc `alembic upgrade head`), không tự chạy khi
ứng dụng khởi động. Thiết kế để một migration lỗi không để lại database ở trạng thái nửa vời.

## Khi migration lỗi: tự rollback

- PostgreSQL có DDL transactional và `alembic/env.py` chạy **toàn bộ** migration đang chờ trong **một transaction**. Một migration lỗi
  ở bất kỳ bước nào ⇒ cả lần nâng cấp bị hoàn tác, database vẫn ở revision cũ (`alembic current` không đổi).
- `SET LOCAL lock_timeout = '10s'`: nếu migration không lấy được khóa bảng trong 10 giây (đang có tải), nó **lỗi và rollback** thay vì
  chờ và chặn các request đang chạy. Chạy lại sau.
- Trong `docker-compose.yml`, `platform` có `depends_on: migrate: service_completed_successfully`: migrate lỗi thì phiên bản mới
  không khởi động; container platform cũ vẫn chạy với schema cũ.
- Mọi migration hiện tại chỉ **thêm** (bảng, cột, index) và không xóa hay sửa dữ liệu cũ, nên bản code cũ vẫn chạy được trên schema mới.

## Muốn quay lại sau khi đã nâng cấp thành công

```bash
alembic current                  # revision hiện tại
alembic downgrade -1             # lùi một bước (hoặc: alembic downgrade 0004)
```
Sau đó chạy lại image/commit trước đó. Mỗi migration đều có `downgrade()`; test `tests/test_migrations.py` áp dụng rồi lùi từng
bước đến rỗng và nâng lại (SQLite).

| Migration | Downgrade làm gì | Mất dữ liệu? |
|---|---|---|
| 0005 `jobs.trace_id` | chép `trace_id` ngược về `jobs.metadata` (PostgreSQL), rồi xóa cột và index | Không |
| 0004 `job_events` | xóa bảng lịch sử job | **Có**: lịch sử đổi trạng thái của job (job vẫn còn) |
| 0003 `health_checks` | xóa bảng probe | **Có**: lịch sử probe và số liệu uptime |
| 0002, 0001 | xóa các bảng tương ứng | **Có**: toàn bộ dữ liệu của chúng |

Chỉ lùi qua 0005 là không mất dữ liệu; lùi sâu hơn thì chấp nhận mất dữ liệu của bảng bị xóa.

## Giới hạn đã biết

Hành vi rollback khi lỗi giữa chừng dựa vào tính transactional của PostgreSQL; test tự động chạy trên SQLite nên **không** chứng minh được
điều đó. Nếu cần chắc chắn, thử một lần trên PostgreSQL tạm (`TEST_DATABASE_URL`): `alembic upgrade head`, `alembic downgrade 0004`,
kiểm tra `jobs.metadata->>'trace_id'` còn đủ, rồi `alembic upgrade head` lại.
