> Tài liệu lịch sử. Xem [tình trạng nghiệm thu hiện hành](../ACCEPTANCE.md).

# Bằng chứng triển khai Sprint 3–4 local

Cập nhật 12/10/2026. Chủ dự án đã cho phép commit/push ngày 12/10/2026; baseline trước phát hành là `030bab3`. Checkout frontend ban đầu được giữ nguyên. Đây là bằng chứng kiểm chứng nghiệp vụ local, chưa nghiệm thu staging hoặc chuyển Jira Done. **Chưa hoàn tất tất cả nhiệm vụ con**: xem [đối chiếu trực tiếp Jira](SPRINT-3-4-SUBTASK-AUDIT.md). Những kết quả dưới đây không chứng minh toàn bộ AC đã đạt.

## Kết quả đã kiểm chứng

**Lượt sửa UX 12/10:** các bằng chứng browser bên dưới ghi trước khi chuyển
giao diện hộp thoại/trang thao tác hiện tại. Frontend mới có 12 test logic/render offline,
lint/build qua; browser chưa kiểm lại do công cụ từ chối truy cập localhost.
Xem [UX và hướng dẫn demo](../UX-DEMO.md). Không dùng ảnh/script browser cũ
để xác nhận toàn bộ luồng UX mới đã qua.

| Phạm vi | Bằng chứng |
|---|---|
| Tách/gộp, lượng đến gram, rollback, tranh chấp giao dịch | PostgreSQL thật; khóa và đọc lại dữ liệu; chuỗi Event hiện hành; kiểm hết lượng, tràn số, lỗi Event và mã lô trùng |
| Truy ngược/xuôi, nhiều gốc, chu trình, quyền | Fixture 12 lô/4 tầng/3 tổ chức, 24 đáp án cố định; đồ thị 1.000 lô dưới 2 giây; chi tiết 3 truy vấn nghiệp vụ; không lộ lô anh em hoặc logistics lịch sử |
| Địa điểm, di chuyển, tiêu thụ | Phân phối đúng vai trò; giao dịch cùng Event; tiêu thụ là trạng thái cuối; API và SQL runtime chặn INSERT/UPDATE vượt quyền; bàn giao xóa địa điểm cũ |
| Bàn giao quá hạn | Ngưỡng mặc định 48 giờ; maintenance idempotent; nhãn ở hai phía; xác nhận muộn ghi `late_acknowledgement`; không tự hủy |
| Audit | Ghi cùng commit nghiệp vụ; đăng xuất cùng giao dịch với thu hồi phiên; request bị từ chối có audit riêng; snapshot người/tổ chức/IP/thời gian/đối tượng; append-only và chỉ admin đọc; không ghi body/password/token |
| CSV | Admin nhập sản phẩm/thửa; UTF-8, 1 MiB/1.000 dòng; lỗi dòng/cột; cả tệp atomic; race tên trùng và tổ chức bị xóa không lưu một phần |
| Trình duyệt Chrome | Tách/gộp; di chuyển/tiêu thụ; CSV lỗi/thành công; audit phân trang; nhãn quá hạn hai phía; xác nhận muộn; đồ thị 7 node, thu gọn/mở; lịch sử nguồn đã ẩn payload; desktop và mobile 390 px không tràn trang |

Backend kiểm tra lại ngày 12/10 sau sửa UX/khôi phục môi trường: **228 passed** trong 86,01 giây trên DB riêng `ttcs_s34_tests`,
PostgreSQL 16. Ruff toàn bộ app/tests/alembic pass; lần Alembic check trước không
có schema drift. Còn một cảnh báo deprecation của dependency Starlette TestClient hiện hữu.

Frontend lint/build pass; npm audit **0 vulnerabilities**. Đồ thị được tải riêng. Truy vấn lịch sử 200 sự kiện giảm từ khoảng 2,5 giây xuống 0,34 giây khi nạp tên tổ chức theo lô thay vì join lặp qua RLS.

Kiểm tra bổ sung sau đối chiếu nhiệm vụ con: bài tranh chấp tách 40 kg thành
30 kg đã qua 20 lần liên tiếp trên PostgreSQL thật. Ruff toàn bộ
app/tests/alembic và format-check 111 file qua. Hai Docker image backend/frontend
build local qua; thêm `.dockerignore` riêng cho từng context để không đưa
`.env`, môi trường Python hoặc node_modules local vào build. Đã kiểm tra image
backend không chứa `/app/.env` hoặc `/app/.venv`. Đây chưa phải GitHub CI.

DB mới: owner không SUPERUSER/BYPASSRLS và runtime riêng; upgrade head21 → downgrade14 → upgrade head21/check pass. Runtime harvest/split/traverse/history pass. Downgrade có dữ liệu phả hệ, địa điểm, tiêu thụ hoặc audit bị chặn để giữ bằng chứng.

Review độc lập bằng agent: foundation, seed, overdue, CSV, lifecycle, audit và toàn nhánh đã duyệt sau sửa các finding. Không ghi rằng thành viên nhóm đã review hoặc hai người đã tự đếm. Chủ dự án đã cho phép thay bước chờ người bằng kiểm thử/review này.

## Chạy và kiểm tra lại

- Test Windows local từ `backend`: `./scripts/test-local.ps1` dùng DB `ttcs_s34_tests` và runtime `ttcs_s34_test_app`. Hook pytest chặn DB demo `ttcs_test` tại localhost:55434 trước mọi test/fixture. Script khôi phục biến môi trường sau chạy. CI dùng DB test dịch vụ riêng tại cổng 5432.
- Từ `frontend`: `npm ci`, `npm run lint`, `npm run build`, `npm audit`; dev server dùng `VITE_BACKEND_TARGET` trỏ đến API local.
- Fixture demo: `APP_ENV=development` hoặc `staging`, đặt rõ `DEMO_PASSWORD`, chạy `python -m app.seed_lineage_demo`. Chỉ chạy trên DB demo; seed idempotent, không thay mật khẩu đã tồn tại. [Đáp án phả hệ](../LINEAGE-ACCEPTANCE.md).
- Maintenance riêng với credential owner: `python -m app.jobs.overdue_handovers --once`; bỏ `--once` để quét mỗi giờ. Không dùng credential owner cho HTTP API. `HANDOVER_OVERDUE_HOURS=48` cấu hình ngưỡng.
- Lịch sử có `payload_redacted=true` là bản hiển thị đã giới hạn quyền. Hash và kết quả integrity được kiểm trên Event gốc ở máy chủ; không dùng payload đã ẩn để tính lại hash phía client.

Script, log và ảnh thử nghiệm trong `local_docs/` là artifact local bị Git ignore, có thể tái tạo; không phải dữ liệu sản xuất. Kế hoạch chia nhánh và bản đồ Jira ở [kế hoạch triển khai](SPRINT-3-4-DELIVERY.md).

Đã được phép commit/push và mở PR nháp. Không tự merge main, staging hoặc
cập nhật Jira. CI GitHub được ghi theo kết quả thực tế trên PR.

## Lượt đối chiếu bổ sung 12/10

- 37 issue Jira đã đọc lại, không sửa remote. 21 nhiệm vụ con Cần làm;
  15 story Cần làm, N3-39 Hoàn tất.
- Cache tổ tiên 60 giây: không cache grants hoặc dữ liệu động, kiểm hết hạn,
  lượng thay đổi và tổ chức ngoài quyền. Truy vấn chi tiết một tầng + event_count,
  3 truy vấn, không CTE đệ quy. Nguồn sâu/vùng trồng gốc chỉ nạp ở phả hệ.
- Migration 22: tổ tiên của lô từng giữ vẫn xem được lịch sử tới lúc bàn giao;
  không thấy hoạt động mới hay logistics hiện tại. Kiểm qua bốn tổ chức.
  Downgrade22→21→upgrade22/check đã qua trên DB test; schema không drift.
- Seed nghiệp vụ 18 lô bằng service thật, 36 tập oracle JSON cố định; chạy hai lần
  giữ ID/hash, lỗi merge muộn rollback tất cả. Bộ 12 cũ vẫn được giữ làm bằng chứng.
- API HTTP trên demo đang chạy: 25 nông sản, không có tên kỹ thuật cũ;
  lô DWCEN356 có 6 node tổ tiên kể cả chính nó, 2 thửa gốc, event_count=1,
  history integrity hợp lệ. Đây là kiểm API, không phải kiểm trực quan browser.
- Ruff check và format-check 117 file, frontend 12 test/lint/build, diff-check qua.

NFR cache quyết định quyền và xóa bộ mẫu trước tái dựng được thay bằng đọc RLS
mới mỗi request và giữ bộ mẫu idempotent để bảo toàn bằng chứng. CTE/Kahn
thay cách viết BFS; farm dẫn xuất lấy từ phả hệ để hỗ trợ nhiều nguồn.
Đây là khác biệt thiết kế ghi rõ, không khẳng định mọi câu AC nguyên văn đã đạt.
