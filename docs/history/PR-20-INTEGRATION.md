> Tài liệu lịch sử. Xem [tình trạng nghiệm thu hiện hành](../ACCEPTANCE.md).

# Tích hợp lịch sử PR #20

PR #22 đã được merge vào `main` trước khi tích hợp PR #20. Nhánh
`feature/integrate-n3-39-history` nối lịch sử commit gốc của #20 vào bản hiện tại,
giữ nguyên tác giả, email và co-author của các commit đó. Commit giải quyết tích hợp
và chuyển kiểm thử ghi tác giả `hieu-kiien`.

## Quyết định kỹ thuật

Giữ một triển khai duy nhất: `lineage_service`, `lot_relations` và `events`.
Không đưa thêm `transactions`, `batch_relations`, `batch_events`, API tách lô
trùng hoặc migration 16 của #20 vào trạng thái cuối cùng của ứng dụng.

Lý do:
- Migration 17 hiện nối từ 15. Thêm migration 16 của #20 tạo một nhánh Alembic
  khác; không thể chạy hai hệ phả hệ song song mà chưa thiết kế chuyển dữ liệu.
- #20 đọc đối tượng cha trước khi khóa nhưng không làm mới lượng tồn đã đọc;
  bản hiện tại khóa và đọc lại, được kiểm thử bằng hai giao dịch đồng thời.
- #20 tạo sự kiện tách cha từ genesis mỗi lần. Bản hiện tại nối tiếp chuỗi sự kiện.
- Quyền tách hiện giới hạn theo vai trò/tổ chức; không giữ đường gọi tách của
  grower trong bản cũ để tránh bỏ qua quy tắc nghiệp vụ hiện hành.

## Phần kiểm thử được chuyển

Nguồn: commit `23c220d` và các commit trước đó của
[PR #20](https://github.com/nhom-3-cnttk23c/truy-xuat-nguon-goc-chuoi-lanh-nong-san/pull/20).

| Tình huống từ #20 | Bằng chứng ở bản hiện tại |
|---|---|
| 100 kg, tách 60 rồi từ chối 50 | `test_pr20_integration.py`: không thay tồn, lô con hoặc số sự kiện khi từ chối; sau đó tách 40 và kiểm tra nối chuỗi |
| Tách 50/30/10 và chỉ lấy lô con trực tiếp | `test_pr20_integration.py`: tạo thêm lô cháu, xác nhận detail chỉ trả ba lô con và lineage truy đúng gốc |
| Tách đồng thời | `test_sprint3_lineage.py`: hai luồng/giao dịch PostgreSQL thực sự, một thành công và một bị từ chối |
| Khối lượng, quyền, API và bất biến sự kiện | Bộ `test_sprint3_lineage*`, `test_lineage_persistence.py` và `test_lineage_traversal.py` |

Đây là chuyển tình huống kiểm thử, không tuyên bố giữ nguyên code chạy của #20.
Bản lịch sử gốc vẫn xem được bằng Git; không sửa lại tác giả để tạo Contributors.
GitHub chỉ liên kết đóng góp với tài khoản khi email commit đáp ứng điều kiện của
GitHub. Việc nối lịch sử không tự sửa email `nhom3@ttcs.dev` trong commit gốc.

Không có dữ liệu triển khai từ migration 16 trong cơ sở dữ liệu local đang dùng.
Nếu một môi trường khác đã chạy migration 16, cần kế hoạch chuyển dữ liệu riêng;
không áp dụng nhánh này lên môi trường đó chỉ dựa trên kết quả CI.
