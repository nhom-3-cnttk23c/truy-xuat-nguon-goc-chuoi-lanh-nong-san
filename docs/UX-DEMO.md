# UX và trình diễn Sprint 3–4

Cập nhật 12/10/2026. Chủ dự án đã cho phép commit/push ngày 12/10/2026; không tự merge hoặc triển khai. Mở `/demo` hoặc chọn
**Hướng dẫn trình diễn** trên thanh điều hướng: 12 bước có tài khoản cần dùng,
cách thao tác và kết quả đối chiếu. Checklist do người trình diễn tự đánh dấu,
không tự xác nhận nghiệm thu.

## Thay đổi UX

- Tạo/sửa nông sản và vùng trồng dùng hộp thoại tạm trên danh sách, nút “Sửa”.
  Lưu thành công cập nhật danh sách và đóng hộp thoại; hủy không lưu thay đổi.
  Các tác vụ khác điều hướng trong cùng tab, bỏ ký hiệu mở tab mới.
- Tên nông sản là nhãn chính của lô; mã truy xuất là thông tin phụ.
  Danh sách vùng trồng không hiển thị UUID kỹ thuật.
- Chi tiết lô có Tổng quan / Lịch sử sự kiện / Nguồn gốc, hỗ trợ bàn phím.
- Một vùng cuộn tài liệu chính; bỏ giới hạn chiều cao/cuộn riêng của bảng.
  Bảng hẹp chuyển thành hàng có nhãn; sơ đồ vừa vùng chứa và có phóng to/thu nhỏ.
- Danh sách lô tối đa 20 mục, lịch sử 10 sự kiện mỗi trang. Form gộp phân trang lô chưa chọn,
  luôn giữ lô đã chọn để kiểm tra lượng; tổng tính chính xác bằng số nguyên.
- Kết quả tách giữ toàn bộ mã lô con. Hiện lý do không chọn được lô khác
  sản phẩm/chủ giữ; tách vượt lượng không lưu được.
- Ghi hoạt động có nhãn tiếng Việt, nhiệt độ/ghi chú và xác nhận dữ liệu bất biến.
  Chi tiết mã kiểm chứng được mở khi cần.

## Mốc tham chiếu và kiểm chứng

Mục tiêu là WCAG 2.2 AA, **chưa tuyên bố tuân thủ đầy đủ**.

| Tham chiếu | Áp dụng / kiểm tra còn lại |
|---|---|
| [W3C Reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html) | Giảm cuộn hai chiều; sơ đồ có điều khiển riêng. Cần kiểm trực quan ở 320 px và zoom 400%. |
| [W3C Focus Not Obscured](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html) | Focus rõ, link bỏ qua điều hướng, khoảng tránh header. Cần duyệt toàn luồng bằng bàn phím. |
| [W3C Target Size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) | Mốc AA 24 px hoặc khoảng cách theo ngoại lệ; ưu tiên 44 px cho cảm ứng. Cần đo các nút/checkbox trên trình duyệt. |
| [NN/g: Modal & Nonmodal Dialogs](https://www.nngroup.com/articles/modal-nonmodal-dialog/) | Biểu mẫu sửa ngắn dùng dialog; cần kiểm giữ focus, Escape, quay focus về nút mở trên trình duyệt. |

Frontend: 12 test logic/render offline qua, lint sạch và build qua. Test render
không thực thi effect/API hoặc xác nhận kích thước/focus thực tế trên trình duyệt.
Bằng chứng browser cũ được ghi trước lần sửa UX này và cần chạy lại.
Công cụ browser đã từ chối truy cập tab localhost theo chính sách giao thức URL;
không sử dụng phương thức khác để vượt chặn.

Các yêu cầu cần nghiệm thu tiếp và quyết định thiết kế ở [bảng đối chiếu hiện hành](ACCEPTANCE.md).
Không khẳng định toàn bộ tính năng hoàn hảo hoặc hai sprint đã nghiệm thu.
Các script/ảnh/dữ liệu chuẩn bị demo trong `local_docs/` là artifact giả lập,
có thể tái tạo, không chứa dữ liệu sản xuất.

Demo quá hạn local đã chuẩn bị lô **H8G34DM4** (5 kg), bên gửi
`s34-farm@example.com`, bên nhận `s34-distribution@example.com`.
Yêu cầu được đánh dấu rõ dữ liệu giả lập, đặt tuổi 49 giờ và đã qua job quét;
API bên nhận xác nhận trạng thái pending và có `overdue_at`.
Nếu người trình diễn đã xác nhận lô này, tái tạo bằng script
`local_docs/prepare_ux_demo.py` với cấu hình đúng DB local; script chỉ cho phép
DB `ttcs_test` ở `127.0.0.1:55434` và ghi mã mới trong artifact JSON.

## Danh mục mẫu dễ đọc

Ngày 12/10: đổi 24 sản phẩm kiểm thử/mẫu thành tên nông sản thông dụng và
mô tả tiếng Việt, đổi 7 tên vùng trồng và 3 tên đơn vị mẫu. Không đổi ID,
khối lượng, quan hệ lô hay sự kiện; hash sự kiện trước/sau giống nhau.
Script local có bản sao tên/mô tả cũ và chỉ chạy trên DB mẫu localhost.
Seed mới dùng Bắp cải trắng, Thửa bắp cải Trại Mát và tên đơn vị theo vai trò.
Đây là dữ liệu giả lập, không chứng nhận nguồn gốc/chất lượng nông sản thực.
Test seed 1/1 và frontend 12/12 qua; lint/build qua. Đã tách DB test `ttcs_s34_tests` khỏi DB demo `ttcs_test`; pytest chặn chạy
nhầm trên DB demo. Lần chạy toàn bộ 228 test không đưa tên kỹ thuật vào danh mục.

Bộ mới Bắp cải xanh gồm 18 lô dựng bằng service thật. Lô cuối **DWCEN356**
còn 30 kg, có hai thửa nguồn; chọn Bắp cải xanh trong danh sách lô rồi mở
Nguồn gốc để đối chiếu. [Sơ đồ và đáp án](LINEAGE-ACCEPTANCE.md).
