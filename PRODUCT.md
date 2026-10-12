# Định hướng sản phẩm AgroChain

Ứng dụng web ghi nhận và truy xuất nguồn gốc nông sản từ vùng trồng đến phân phối. Dự án học phần TTCS của nhóm TTCS_T926_K18C4_N3; dữ liệu trình diễn là giả lập.

## Người sử dụng

- Nông hộ: quản lý vùng trồng, khai báo lô thu hoạch và ghi sự kiện.
- HTX, đơn vị vận chuyển/phân phối: quản lý lô đang giữ, bàn giao và xử lý theo quyền được cấp.
- Quản trị đơn vị/hệ thống: quản lý dữ liệu trong phạm vi tương ứng.
- Thanh tra: tra cứu nguồn gốc, kiểm tra toàn vẹn và nhật ký thao tác.

## Phạm vi hiện tại

Có đăng nhập/phân quyền, danh mục nông sản, vùng trồng, lô hàng, tách/gộp, phả hệ, bàn giao, vị trí phân phối, tiêu thụ, nhập CSV và audit. Tiêu chí và giới hạn xem [ACCEPTANCE](docs/ACCEPTANCE.md); danh sách này không xác nhận tất cả sprint đã Done.

Cảm biến tự động, cảnh báo nhiệt độ tự động, thu hồi, QR và PDF thuộc phạm vi tiếp theo. Ghi sự kiện thủ công không thay tích hợp cảm biến.

## Nguyên tắc thiết kế

- Dùng tên nông sản/vùng trồng dễ hiểu; mã kỹ thuật chỉ hiện khi cần tra cứu.
- Sửa bằng hộp thoại tạm; nhãn nút ngắn, lỗi và kết quả bằng tiếng Việt.
- Danh sách phân trang; hạn chế cuộn lồng nhau và cuộn ngang toàn trang.
- Đồ thị dùng React Flow/Dagre; ưu tiên đọc được nguồn gốc.
- Hỗ trợ sáng/tối và bàn phím. WCAG AA là mục tiêu cần đo/kiểm tra, chưa phải chứng nhận đã đạt.

## Giới hạn bảo đảm dữ liệu

API kiểm quyền, PostgreSQL RLS giới hạn dữ liệu theo phiên; trigger chặn sửa/xóa sự kiện đối với vai trò runtime. Chuỗi SHA-256 giúp phát hiện sửa đổi khi đối chiếu, không phải chữ ký số hoặc bảo đảm quản trị viên DB không thể viết lại dữ liệu.

Chi tiết: [toàn vẹn](docs/N3-4-INTEGRITY.md), [database](docs/database.md). Cách chạy và tài khoản mẫu xem [README](README.md) và trang demo, tránh sao chép mật khẩu/cấu hình vào nhiều tài liệu.
