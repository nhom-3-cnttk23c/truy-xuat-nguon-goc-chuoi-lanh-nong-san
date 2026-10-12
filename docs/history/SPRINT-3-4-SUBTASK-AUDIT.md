> Tài liệu lịch sử. Xem [tình trạng nghiệm thu hiện hành](../ACCEPTANCE.md).

# Đối chiếu nhiệm vụ con Sprint 3–4

Cập nhật code local 12/10/2026; snapshot Jira đọc lại ngày 12/10/2026. Phạm vi 16 story, 21 nhiệm vụ con.
Đây là bảng tổng hợp có thể tái tạo, không phải biên bản nghiệm thu.
Toàn bộ 21 nhiệm vụ con trên Jira vẫn ở trạng thái **Cần làm**; chưa cập nhật remote.
“Có bằng chứng local” không có nghĩa staging hoặc CI GitHub đã qua.

| Nhiệm vụ con | Kết quả đối chiếu local / việc còn lại |
|---|---|
| N3-115 | Có bảng quan hệ, khóa/index/unique và migration; tên triển khai `lot_relations`. |
| N3-116 | Tách atomic, rollback và kế thừa sản phẩm đã kiểm; lô dẫn xuất lấy vùng trồng qua phả hệ, không sao chép một farm FK. Cần ghi rõ khác biệt thiết kế với yêu cầu. |
| N3-117 | Đã triển khai tổng lượng trực tiếp, khóa nút lưu khi vượt lượng, thêm/xóa dòng và hiển thị toàn bộ mã con sau tách. Logic/render offline qua; cần kiểm lại thao tác browser sau sửa UX. |
| N3-118 | Có khóa hàng/Decimal; lỗi chứa mã lô và lượng còn lại cùng đơn vị. Test API vượt 40.000 kg qua. |
| N3-119 | Test 20 lần liên tiếp trên PostgreSQL thật đã qua: mỗi lần hai yêu cầu đồng thời, một 201/một 409, lô 40 kg còn 10 kg và chỉ sinh một lô con 30 kg. |
| N3-120 | Gộp một phần, thứ tự khóa ổn định, atomic/rollback có bằng chứng local. |
| N3-121 | Có kiểm sản phẩm/chủ giữ/lượng/trạng thái. Lỗi nêu mã lô đã được phép biết; lỗi lô ngoài quyền giữ thông báo chung để tránh lộ dữ liệu. |
| N3-122 | Event cha/con và các cha/lô gộp nằm cùng giao dịch; chuỗi hash có bằng chứng local. |
| N3-123 | Đã kiểm sửa Event khai sinh một lô con: chỉ chuỗi đó sai, chuỗi lô mẹ và con còn lại vẫn đúng. |
| N3-124 | CTE UNION chống lặp và Kahn phát hiện chu trình, thông báo ID lô liên quan. Khác cách viết BFS; giữ triển khai hiện tại vì có kiểm oracle, chu trình và hiệu năng 1.000 lô. |
| N3-125 | API/đồ thị/nguồn gốc và cache tổ tiên 60 giây đã kiểm. Cache chỉ lưu tập ID cấu trúc; mỗi lần vẫn kiểm RLS, đọc lại cạnh/lượng/chủ giữ và phát hiện cạnh mới. Có kiểm hết hạn và không cấp quyền qua cache. |
| N3-126 | Oracle tổ tiên/hậu duệ cố định cho 12 lô và chu trình SQL đã kiểm local; CI GitHub chưa chạy. |
| N3-127 | Có bộ mới 18 lô/3 tổ chức/4 tầng: nghiệp vụ thật 3→6→3→6, dùng service harvest/handover/split/merge; chạy lại giữ ID/hash, lỗi muộn rollback cả lần dựng. Giữ bộ 12 cũ và không xóa lịch sử mẫu thay vì yêu cầu xóa trước dựng; đây là điều chỉnh có chủ ý để giữ bằng chứng. |
| N3-128 | Có hai file JSON oracle độc lập với traversal: 24 tập cho bộ 12 lô, 36 tập cho bộ 18 lô; đều nạp trong test. Chủ dự án đã bỏ bước chờ hai người; không ghi tên/chữ ký giả hoặc nói oracle có trước triển khai. |
| N3-129 | Migration 22 giữ quyền nguồn gốc của lô từng giữ, cắt lịch sử theo lần bàn giao và ẩn logistics hiện tại. Test qua bốn tổ chức, cả sự kiện sau bàn giao. Không cache quyết định cấp quyền giữa các request; vẫn đọc RLS mới, cache cấu trúc riêng. NFR cache quyền là khác biệt thiết kế còn ghi rõ. |
| N3-130 | Có kiểm nhiều tổ chức, không lộ lô không liên quan, fixture dọn dữ liệu; CI GitHub chưa chạy. |
| N3-131 | Có job quá hạn 48 giờ, chạy mỗi giờ, đếm/log/idempotency. Chưa kích hoạt trên môi trường triển khai. |
| N3-132 | Nhãn quá hạn hai phía và xác nhận muộn đã kiểm API/trình duyệt local. |
| N3-133 | Chi tiết đọc một tầng, có COUNT sự kiện cùng truy vấn bulk, tổng 3 truy vấn nghiệp vụ; test xác nhận không CTE đệ quy. Vùng trồng gốc đầy đủ nằm ở API phả hệ; chi tiết trả `direct_farms`. |
| N3-134 | Đã triển khai ba tab Tổng quan / Lịch sử sự kiện / Nguồn gốc, trang thao tác riêng và ẩn theo quyền/trạng thái. Cần kiểm browser/focus trực tiếp. |
| N3-135 | Đã triển khai chọn nhiều lô từ danh sách, mặc định lấy hết lượng đã chọn, tổng trực tiếp và phân trang ứng viên. Có test lọc quyền/sản phẩm/lượng/loại trùng; cần kiểm luồng browser hoàn chỉnh. |

Ưu tiên tiếp theo: sửa các thiếu sót chức năng/UI và quyền; bổ sung bằng chứng
đồng thời/integrity; đối chiếu lại seed/oracle; chạy lại kiểm thử và browser.
Không đánh dấu toàn bộ hoàn tất dựa riêng vào số test qua.
Chi tiết thay đổi UX và giới hạn kiểm chứng ở [UX và demo](../UX-DEMO.md).

Baseline trước commit là `030bab3`; checkout frontend ban đầu giữ nguyên.
Đã xác nhận quyền push trên fork hieu-kiien ngày 12/10. Bản tích hợp dùng
`feature/sprint-3-4-delivery`; trạng thái CI xem trực tiếp trên PR.
Staging, merge main và cập nhật Jira chưa được thực hiện.

Đọc lại toàn bộ 37 issue ngày 12/10: 21 nhiệm vụ con vẫn Cần làm; 15 story
Cần làm, riêng N3-39 Hoàn tất. Không thay đổi Jira. Các khác biệt thiết kế
được ghi công khai, không xem số test là bằng chứng cho AC chưa kiểm browser.
