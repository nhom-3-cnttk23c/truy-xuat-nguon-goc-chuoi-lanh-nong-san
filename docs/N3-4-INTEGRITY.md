# N3-4 — Chọn cơ chế kiểm tra toàn vẹn sự kiện

## Quyết định
Dùng chuỗi SHA-256 kết hợp quyền DB và trigger chỉ thêm. Không dùng blockchain vì phạm vi dự án có DB quản lý tập trung, cần triển khai đơn giản và chưa có yêu cầu đồng thuận giữa nhiều bên độc lập.

## Công thức hiện hành
`hash = SHA256(previous_hash + ":" + RFC8785(content))`
Code chuẩn nằm ở `backend/app/core/crypto.py`. Genesis dùng 64 ký tự `0`. Nội dung gồm loại sự kiện, lot_id, organization_id, payload và sequence_number. Dấu `:` là một phần của dữ liệu băm.

RFC 8785 canonicalize JSON qua thư viện rfc8785, SHA-256 dùng hashlib. Không tự viết thuật toán mật mã. Khi xác minh, kiểm thứ tự sequence, previous_hash và content hash; sự kiện sau điểm sai lệch được đánh dấu chưa xác minh.

## Benchmark
Spike cũ: khoảng 11,63 ms tạo hash và 6,76 ms kiểm hash cho 1.000 sự kiện **trong bộ nhớ JavaScript**. Đây không phải thời gian ghi 1.000 giao dịch DB, API hoặc số đo staging. Có thể tái tạo bằng:
```sh
node backend/tests/integrity.test.js
```
Test Python hiện hành kiểm chuỗi 1.000 sự kiện dưới 1 giây trên môi trường kiểm thử. Thời gian phụ thuộc máy/DB; không suy ra SLA triển khai từ spike.

## Giới hạn
Hash giúp phát hiện dữ liệu khác với chuỗi đã ghi trong các ca kiểm thử. Nếu người có quyền quản trị viết lại cả dữ liệu và toàn bộ hash, chỉ chuỗi nằm trong cùng DB không đủ chứng minh bản gốc. Cần nguồn neo độc lập/chữ ký nếu phát sinh yêu cầu chống chối bỏ.

Ứng dụng hiện không triển khai chữ ký số, không khẳng định “100% chống giả mạo” hoặc giá trị chứng cứ pháp lý. Quyền DB/trigger hạn chế thao tác ứng dụng; không mô tả quản trị DB là không thể can thiệp.
