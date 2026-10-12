# Quyền và bảo toàn dữ liệu

Migration chạy bằng tài khoản riêng. Web dùng role không SUPERUSER/BYPASSRLS; startup loại mật khẩu migration khỏi môi trường runtime.

- RLS suy ra tổ chức/vai trò từ phiên hợp lệ trong transaction; không tin organization_id/role từ request.
- Bảng sản phẩm dùng chung; chỉ quản trị hệ thống được sửa qua API.
- Lô hiển thị cho bên giữ, bên nhận chờ xác nhận và nguồn gốc được phép. Người từng giữ chỉ xem lịch sử đến thời điểm bàn giao; không được xem logistics hiện tại hoặc lô anh em.
- Lượng dùng NUMERIC/Decimal. Tách/gộp khóa các lô theo thứ tự UUID ổn định, đọc lại số dư và ghi toàn bộ thay đổi/Event trong cùng giao dịch.
- events, lot_relations và audit_logs có ràng buộc chỉ thêm. Role ứng dụng không được cấp quyền sửa/xóa nhật ký.
- SECURITY DEFINER có search_path cố định, không nhận tổ chức từ người gọi. `app_mark_overdue_handovers` chỉ đánh dấu tối đa 500 bàn giao pending quá hạn mỗi lần, không chuyển quyền giữ và không sửa chuỗi Event; PUBLIC bị thu hồi EXECUTE.
- Web chạy maintenance bằng quyền EXECUTE hẹp, không dùng tài khoản migration để xử lý request.
- Không sửa/xóa migration đã phát hành. Thay đổi mới là revision tiếp theo, có downgrade.
- Các bảng dùng RLS theo chính sách tương ứng; không khẳng định mọi bảng đều FORCE RLS. Owner/migration có thể bảo trì theo quyền riêng.

CI kiểm nâng cấp từ trạng thái legacy, Alembic metadata và các luồng giao dịch/tenant. Bằng chứng test/coverage được tái tạo; không dùng DB demo để chạy fixture.
