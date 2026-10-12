# Nghiệm thu Sprint 1–4 — 12/10/2026

Báo cáo này ghi nhận kiểm tra local trên nhánh `fix/sprint-acceptance-hardening`, sau bản main `62d54714`. Không xác nhận tất cả Jira Done hoặc staging đã chạy bản này. Phạm vi đối chiếu: **33 nhiệm vụ chính, 59 nhiệm vụ con (92 mục)**; Sprint 4 chưa có nhiệm vụ con trong Jira tại thời điểm đọc.

## Bằng chứng kiểm tra

| Kiểm tra | Kết quả local |
|---|---|
| Backend tích hợp, quyền/RLS, tách/gộp, bàn giao, hash, CSV, audit | 238 passed, 3 test hiệu năng tách riêng |
| Hiệu năng không chạy cùng coverage | 3 passed; lịch sử 200 sự kiện ~143 ms; danh sách 5.000 lô ~76 ms; đồ thị 1.000 node ~0,80 s xuôi / ~0,73 s ngược |
| Coverage nhánh / main cùng bộ đo | 91,57% / 91,48%; không giảm |
| Frontend | 12 test offline, lint và TypeScript/production build đạt |
| Thư viện | npm audit và pip-audit không phát hiện lỗ hổng tại thời điểm chạy |
| DB trống bằng Docker Compose riêng | Nâng lên revision 20261012_24; backend/frontend khởi động |
| Migration vòng 24 → 22 → 24 | Đạt trên DB test riêng; Alembic check không phát hiện lệch schema |
| Readiness | DB tốt trả 200; candidate sai DB trả 503, API cũ tốt vẫn trả 200 trong thử nghiệm local riêng |
| Quyền runtime | Web không giữ mật khẩu migration; vai trò app không SUPERUSER/BYPASSRLS |

Số đo là trên máy local và bộ dữ liệu test cố định, không phải SLA staging. Test frontend render HTML offline, **chưa chứng minh** focus, drag/pan, mobile hoặc mọi thao tác trình duyệt của bản mới. Coverage artifact do CI tái tạo; không commit bản build/cache.

## Các thiếu sót đã xử lý trong mã

| Jira | Thay đổi và kiểm chứng |
|---|---|
| N3-1 / N3-77 | Dừng khởi động khi thiếu mật khẩu; bootstrap/migration lỗi không tiếp tục phục vụ. Test cấu hình/startup và Compose DB trống. |
| N3-2 / N3-79 / N3-81 | CI mọi push; lint/test/audit/coverage; Docker gắn nhãn và tag SHA. |
| N3-3 / N3-82 / N3-83 | Readiness DB/job, version SHA; workflow kiểm đúng commit và 20 hợp đồng route thay 11 route bản cũ. Chưa nghiệm thu deploy/rollback Render. |
| N3-4 | Sửa công thức hash và giới hạn bằng chứng trong tài liệu; bỏ khẳng định 100%, chữ ký số/pháp lý. |
| N3-23 / N3-107 | Một truy vấn dữ liệu sự kiện, phân trang server, kiểm toàn chuỗi kể cả ngoài trang. 501 sự kiện + tamper và 200 sự kiện dưới 200 ms được kiểm tra. Còn hai truy vấn quyền/ẩn dữ liệu, cần điều chỉnh câu “đúng một SQL” trong Jira. |
| N3-26 / N3-131 / N3-132 | Job chạy ngay và theo giờ; hàm DB giới hạn 500 dòng/transaction, SKIP LOCKED, chỉ đánh dấu quá hạn. Không đổi chủ lô/tạo sự kiện. Lịch GitHub đánh thức Render free. Cần xác nhận job trên staging. |
| N3-34 / N3-109 / N3-110 | Danh sách 20 lô/trang, giới hạn IDs trước join; test 5.000 lô dưới 300 ms, cursor không trùng. |
| N3-35 / N3-133 / N3-134 | Hiện tên tất cả vùng trồng gốc ở trang chi tiết, kể cả nhiều lần tách/gộp; giữ tổng ba truy vấn detail. |
| N3-135 | Lô chọn đầu tự đặt bộ lọc nông sản; đổi bộ lọc xóa lựa chọn không còn phù hợp. |
| N3-47 | React Flow dùng Dagre bố cục; bỏ thuật toán tọa độ tự viết. Pan/fit thay cuộn ngang toàn trang theo yêu cầu UX của chủ dự án. |

Các yêu cầu còn lại được đối chiếu mã và test trong [bảng 92 mục](acceptance/sprint-1-4.csv). Bảng là snapshot đọc Jira ngày 12/10; trạng thái Jira giữ nguyên. “Có test local” không có nghĩa từng AC đã đạt trên staging.

## Các quyết định cần ghi nhận khi nghiệm thu

- **Triển khai:** Render native build đang được giữ; image SHA dùng kiểm tra build, chưa phải image được phát hành lên Render. [Render giữ bản cũ nếu bản mới không healthy](https://render.com/docs/health-checks), cửa sổ kiểm tra có thể đến 15 phút. Không khẳng định đáp ứng rollback tự động trong 60 giây hoặc image-only của Jira.
- **N3-88:** Guard tenant ở API, RLS và test kiến trúc kiểm tra đường truy cập. Chưa có lint chứng minh mọi câu SQL nghiệp vụ dùng cùng helper; bulk/recursive SQL có kiểm quyền riêng.
- **Traversal/cache:** Recursive SQL và kiểm chu trình thay cách diễn đạt BFS; cache cấu trúc 60 giây, quyền và payload kiểm tra mới mỗi lần. Không cache nguyên response mang quyền cũ (N3-125).
- **Oracle N3-44/N3-128:** Chủ dự án đã miễn chờ hai người đếm; dùng oracle cố định và test thật. Không ghi rằng có hai người ký hoặc oracle được viết trước mã. Xem [mẫu phả hệ](LINEAGE-ACCEPTANCE.md).
- **GitHub:** Main yêu cầu một người khác review và checks. Không giả tác giả hoặc bỏ rule để chuyển Done.

## Trước khi người giám sát nghiệm thu

1. CI của commit cuối phải xanh, reviewer thật duyệt PR, merge không conflict.
2. Xác nhận workspace Render, health path /health và bản /version khớp SHA vừa merge.
3. Chạy [12 bước demo](UX-DEMO.md) trên staging: đổi vai trò, quyền từ chối, tách/gộp, nguồn gốc, hash, bàn giao/đến hạn, chuyển vị trí/tiêu thụ, CSV, audit.
4. Kiểm bảng quyền ở desktop/mobile, dialog sửa (focus/đóng/lưu), phân trang và đồ thị; lưu kết quả thực tế.
5. Cập nhật Jira theo bằng chứng và các điều chỉnh AC đã thống nhất; không tự chuyển toàn bộ Done.

## Dọn dự án

README và tài liệu hiện hành được rút gọn, có [mục lục](README.md). Bảy báo cáo cũ được chuyển vào history và gắn cảnh báo thời điểm. Đã bỏ sprite SVG không còn tham chiếu. Không xóa migrations, oracle, test bảo mật hoặc DB mẫu để giảm số file. Tài liệu sinh tự động có thể tái tạo; bản local tạm/ảnh cũ không thuộc source chính.

