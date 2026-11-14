# Claude skill: `obs-integration`

## Dành cho ai

**Dành cho các service/repo khác** muốn kết nối vào OBS (đội phát triển của service đó, hoặc Claude
Code đang làm việc trong repo của service đó). **Không phải để dùng bên trong repo OBS này**: vì vậy nó
nằm ở `integrations/` chứ không ở `.claude/skills/`, để Claude Code chạy trong repo OBS không tự nạp nó.
Skill của chính OBS (vd. `skeleton-qa`) vẫn ở `.claude/skills/`.

OBS là nền tảng dùng chung; skill này không gắn với sản phẩm nào (Tin360 chỉ là một ví dụ).

## Nó làm gì

Hướng dẫn Claude kết nối một service bất kỳ vào OBS: register/heartbeat, `/health`, worker, job,
workflow event, `trace_id`. Phân biệt Service / Worker / Job / Workflow và có bước kiểm kê để không
bỏ sót. Tự chứa đủ thông tin, không cần truy cập repo OBS.

Gồm: `SKILL.md` (quy trình), `reference.md` (hợp đồng API), `client_template.py` (client gửi OBS),
`logging.md` + `log_template.py` (định dạng log JSON có `trace_id`/`obs.*`, sẵn sàng để truy vết).

## Cài vào một service

```bash
# chạy từ gốc repo của service đích
mkdir -p .claude/skills
cp -r <đường-dẫn-repo-OBS>/integrations/claude-skill/obs-integration .claude/skills/
```

Hoặc cài cho mọi project của một người dùng: copy vào `~/.claude/skills/`.
Sau đó trong repo đích, nhờ Claude: "kết nối service này vào OBS" (hoặc `/obs-integration`).
Service cần `OBS_URL` và `OBS_API_KEY` (xin từ người quản lý OBS; không commit key).

## Bảo trì (dành cho người quản lý OBS)

Khi API của OBS đổi, sửa `obs-integration/reference.md` và `client_template.py` trong cùng PR với thay
đổi API, rồi báo các service cập nhật bản copy.
