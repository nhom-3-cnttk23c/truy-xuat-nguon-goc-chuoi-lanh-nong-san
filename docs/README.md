# Tài liệu dự án

Ưu tiên đọc:
1. [Hướng dẫn chạy](../README.md)
2. [Demo từng vai trò](UX-DEMO.md)
3. [Nghiệm thu Sprint 1–4 và quyết định thiết kế](ACCEPTANCE.md)
4. [API](api.md), [quyền DB](database.md), [chuỗi hash](N3-4-INTEGRITY.md)
5. [Mẫu phả hệ và oracle](LINEAGE-ACCEPTANCE.md)

Các kế hoạch, ảnh chụp tiến độ và báo cáo cũ nằm trong [history](history/). Chúng ghi nhận trạng thái tại thời điểm viết, không phải xác nhận trạng thái hiện tại. Không xóa migrations hoặc oracle để giảm số file: chúng vẫn cần cho nâng cấp DB và kiểm chứng.

Báo cáo/coverage/CSV sinh tự động có thể tái tạo, để trong artifact CI hoặc `local_docs/` đã được gitignore. Không commit node_modules, .venv, cache, bản build hoặc dữ liệu trình diễn.
