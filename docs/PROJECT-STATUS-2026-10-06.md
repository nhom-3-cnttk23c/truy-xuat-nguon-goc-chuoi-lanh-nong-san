# Tình hình dự án Nhóm 3 — 06/10/2026

Snapshot kiểm tra ngày 06/10/2026 (Asia/Saigon), từ Jira, GitHub và mã nguồn. Đây là báo cáo; không thay đổi trạng thái, lịch hoặc phân công trên Jira.

## Sprint 2 — Bàn giao lô

- Sprint 2 (id 2, board 4) đang chạy, hạn kết thúc 00:00 ngày 07/10; goal trên Jira đang trống.
- N3 có 147 issue: 22 Hoàn tất, 2 Đang làm, 123 Cần làm. Sprint 2 có 10 story / 20 SP: N3-20 và N3-21 Đang làm; 8 story còn lại Cần làm.
- 23 subtask N3-92..114 đều Cần làm và chưa được gán assignee. Không xem SP hay code đã merge là bằng chứng issue hoàn tất.
- Ưu tiên chốt N3-20/21, phân công và cập nhật subtask, sau đó xác nhận luồng tạo lô và bàn giao có dữ liệu nghiệp vụ thật.

## Tình hình mã nguồn và rủi ro tích hợp

- Nhánh chính Nhóm 3 đang ở `09f0b334` (sau `d2d9c852`); `origin/main` trên fork cá nhân ở `038b3a2`. Hai nhánh đã được fetch và còn lệch nhau: 10 commit chỉ có ở nhóm, 5 commit chỉ có ở fork; chưa merge.
- Backend nhóm đã có event append-only và cookie-only auth cho N3-21. Model `lots` hiện mới có `id`, `organization_id`, `farm_id`, `name`; chưa có mã lô, sản phẩm, ngày thu hoạch, khối lượng hay chủ giữ hiện tại.
- Migration của nhóm đi `20260929_03 → 20260930_04 → 20261005_05`; fork có revision thay thế `20261001_04` sau `20260929_03`. Cần thống nhất revision graph và kiểm tra database trước khi nhập thay đổi.
- Chưa xác minh CI của `d2d9c852` và `09f0b334`; kết quả Actions đã xem là run cũ trên `9b35621`. Trạng thái staging sau các commit mới cũng chưa được xác minh.
- Bản frontend đang làm ở máy cá nhân còn thay đổi chưa commit; một số import trong `App.tsx` chưa có file tương ứng. Chưa có kết quả build cho bản này.

## Việc cần xác nhận

1. Nhóm chốt owner và kết quả nghiệm thu cho 10 story, đặc biệt các subtask còn trống.
2. Xác nhận phạm vi dữ liệu lô và luồng bàn giao trước khi mở rộng frontend.
3. Chọn cách hợp nhất migration, sau đó kiểm tra CI và staging trên đúng commit mới.

Nguồn đối chiếu: Jira project N3, nhánh chính repo Nhóm 3 và nhánh chính fork cá nhân.
