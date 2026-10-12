# API

Hợp đồng API hiện hành được sinh từ Pydantic/FastAPI tại `/openapi.json`; dùng `/docs` để xem và thử. Không duy trì thêm bảng endpoint bằng tay.

- Staging: https://ttcs-backend-staging.onrender.com/docs
- Local: http://localhost:8000/docs
- Browser đăng nhập bằng cookie HttpOnly, Secure, SameSite=None; không lưu session token vào localStorage.
- Các route nghiệp vụ dưới `/api/v1` kiểm quyền ở máy chủ; dữ liệu ngoài phạm vi được từ chối.
- `GET /health` kiểm readiness, không yêu cầu đăng nhập. `GET /version` chỉ trả commit SHA.
- Danh sách lô dùng cursor, mặc định UI 20 dòng, lọc theo sản phẩm và tìm mã không phân biệt hoa/thường.
- Lịch sử `/api/v1/events/lots/{lot_id}/history` nhận `after` (sequence) và `page_size` (1–500). Trả `events`, `next_cursor`, `total`, `integrity`. Toàn bộ chuỗi có quyền xem vẫn được kiểm tra, kể cả khi trang chỉ chứa 10 sự kiện.
- Chi tiết lô trả `root_farms` để tổng quan hiển thị nguồn gốc; dữ liệu logistics của lô lịch sử bị ẩn.
- Sự kiện không có route sửa/xóa. Các sự kiện hệ thống chỉ được tạo qua thao tác nghiệp vụ tương ứng.
