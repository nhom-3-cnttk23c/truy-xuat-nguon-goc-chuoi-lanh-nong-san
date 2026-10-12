> Tài liệu lịch sử. Xem [tình trạng nghiệm thu hiện hành](../ACCEPTANCE.md).

# Kế hoạch hoàn thành Sprint 3–4

Cập nhật code local 12/10/2026 (Asia/Saigon), snapshot Jira đọc lại ngày 12/10. Phạm vi: 16 story trên Jira, 9 ở Sprint 3 và 7 ở Sprint 4. Tài liệu tổng hợp có thể tái tạo; không thay thế bằng chứng nghiệm thu. Owner triển khai: hieu-kiien, theo xác nhận của người dùng. Không ghi tác giả hoặc đồng tác giả cho người chưa tham gia.

Lệnh hiện hành ngày 12/10: commit và push lên fork hieu-kiien trong các nhánh
riêng, mở PR nháp để review. Không tự merge main, triển khai hoặc sửa Jira.
Nhánh phát hành nối tiếp: feature/sprint-3-4-backend → feature/sprint-3-4-frontend
→ feature/sprint-3-4-delivery; nhánh cuối là bản tích hợp để review.
Chủ dự án đã cho phép bỏ bước chờ hai người tự đếm/reviewer thành viên;
dùng kiểm thử API và review độc lập bằng agent, ghi trung thực người/công cụ
thực hiện. Điều chỉnh này chưa được ghi lên Jira. Nghiệm thu staging vẫn
là bước riêng chưa thực hiện trong phiên local.

Mốc local hiện tại: 228 backend test và 12 frontend test qua, lint/build,
migration/check và API demo qua. Đã bổ sung cache tổ tiên, quyền nguồn gốc của
lô từng giữ, chi tiết một tầng + event_count, lỗi rõ mã/lượng và seed nghiệp vụ
18 lô kèm JSON oracle. DB test/demo được tách riêng. Cần kiểm trực quan UX mới
và nghiệm thu môi trường triển khai; các khác biệt thiết kế với câu chữ Jira
được ghi ở [bảng đối chiếu](SPRINT-3-4-SUBTASK-AUDIT.md).
[Bằng chứng và hướng dẫn chạy](SPRINT-3-4-VERIFICATION.md).

## Cách làm và điều kiện hoàn tất

- Phát triển từ main nhóm trong worktree riêng; giữ nguyên checkout frontend đang sửa.
- Mỗi nhánh giải quyết một nhóm yêu cầu liên quan, có test và PR; không push trực tiếp main.
- Với logic mới: test thất bại đúng nguyên nhân trước, sửa đến khi test qua, kiểm tra regression và migration.
- Với khối lượng: PostgreSQL thật, hai kết nối/giao dịch đồng thời, rollback khi lỗi giữa chừng, Decimal đến gram.
- Với sự kiện: dùng chuỗi events hiện tại; timeline và integrity phải thấy toàn bộ tách/gộp. Không tạo một chuỗi thứ hai mà các API hiện tại bỏ qua.
- Với quyền: kiểm API và RLS bằng tài khoản runtime, không chỉ session quản trị; kiểm ba tổ chức và giới hạn lịch sử sau bàn giao.
- Với UI: giữ thiết kế main, dữ liệu API thật, trạng thái tải/rỗng/lỗi; kiểm browser desktop và mobile theo AC.
- DoD [N3-146](https://nhom3-k23c.atlassian.net/browse/N3-146) trên Jira còn ghi review thành viên và AC qua staging. Chủ dự án đã điều chỉnh bước review như trên; không ghi rằng thành viên đã review hoặc staging đã qua.
- Chỉ chuyển Jira Done sau khi đủ bằng chứng. Hoàn tất code/CI là mốc riêng với nghiệm thu.

## Thứ tự nhánh và phạm vi

Tên nhánh theo CONTRIBUTING.md, không đặt theo tên cá nhân. Các nhánh phụ thuộc tạo từ đầu nhánh đã kiểm chứng; PR phải ghi base/phụ thuộc và cần cập nhật về main trước merge.

| Thứ tự | Nhánh | Jira | Kết quả và kiểm thử quyết định |
|---|---|---|---|
| 0 | docs/sprint3-4-delivery | Toàn phạm vi | Kế hoạch, quy tắc ghi nhận đóng góp, bản đồ yêu cầu |
| 1 | fix/n3-39-split-hardening | N3-39,40,42 (phần tách) | Rà PR #20, sửa quyền cooperative/distributor, trạng thái lô, dữ liệu mới sau lock, rollback và nối events hiện tại; form tách, hai giao dịch tách tranh cùng lô |
| 2 | feature/n3-41-merge-lots | N3-41,42 (phần gộp),135 | Gộp toàn bộ/một phần; cùng sản phẩm/chủ giữ; khóa nhiều mẹ theo thứ tự cố định, không deadlock; event mọi mẹ/con; UI gộp |
| 3 | feature/n3-44-lineage-fixture | N3-44,127,128 | Ít nhất 12 lô/3 tầng/3 tổ chức; seed idempotent; đáp án cố định kiểm độc lập theo điều chỉnh của chủ dự án, xem LINEAGE-ACCEPTANCE.md |
| 4 | feature/n3-43-lineage-traversal | N3-43,45 | Truy ngược đủ mọi gốc khi gộp; truy xuôi không bỏ sót lô pha trộn; chu trình báo lỗi; đồ thị 1000 lô dưới 2 giây |
| 5 | feature/n3-28-35-lineage-access | N3-28,35 | Quyền xem tổ tiên/lịch sử cũ theo thời điểm bàn giao; không thấy lô không liên quan; detail cha/con, tối đa 3 query cho truy vấn chi tiết |
| 6 | feature/n3-26-overdue-handovers | N3-26,131,132 | Job mỗi giờ, ngưỡng cấu hình 48 giờ, nhãn hai phía, accept muộn ghi event; không tự hủy |
| 7 | feature/n3-36-48-lot-lifecycle | N3-36,48 | Địa điểm thuộc tổ chức; chuyển nội bộ/chi nhánh bằng tách; trạng thái đã tiêu thụ cuối cùng, chặn tách/gộp/bàn giao |
| 8 | feature/n3-46-47-lineage-view | N3-46,47 | Hậu duệ có nơi giữ/địa điểm/khối lượng/trạng thái; sơ đồ bằng thư viện, thu gọn, bấm detail, cuộn ngang mobile |
| 9 | feature/n3-29-audit-log | N3-29 | Middleware ghi thành công/thất bại, người/tổ chức/IP/thời điểm/mã đối tượng; append-only, không password/token |
| 10 | feature/n3-37-csv-import | N3-37 | CSV sản phẩm/thửa, mẫu rõ, giới hạn tệp, lỗi dòng/cột, cả tệp atomic, quyền server |
| 11 | test/sprint3-4-acceptance | Toàn phạm vi | Migration upgrade/downgrade/reupgrade, regression Sprint 1–2, browser, staging và bảng bằng chứng AC |

Không coi một PR lớn duy nhất là hoàn tất hai sprint. Các nhánh trên có thể tách nhỏ thêm nếu diff quá lớn; không giảm AC để làm đẹp tiến độ.

## Những điểm PR #20 cần kiểm chứng trước khi làm nền

Baseline từ main nhóm cb56390 ngày 11/10: 89 backend tests pass trên PostgreSQL 16 riêng tại localhost:55434; Alembic upgrade head và check pass; frontend lint/build pass. npm audit --omit=dev không phát hiện lỗ hổng; audit đầy đủ báo source-map-js (dev dependency) high theo GHSA-68fv-2mgg-jv7q, có bản sửa. Cần xử lý advisory trong nhánh bảo trì riêng trước khi chốt DoD. Baseline này không chứng minh PR #20 hoặc Sprint 3–4 đã pass.

Head rà soát: 23c220d22982c63d1460bc17c6758d22ce97ce2e. CI xanh; PR còn open. Đây là kết quả đọc code, chưa phải toàn bộ lỗi đã tái hiện bằng runtime.

1. Route split dùng lots:create; cooperative/distributor không có quyền này dù là vai trò nghiệp vụ tách/gộp.
2. split_lot đọc parent trước khi lock; SELECT FOR UPDATE sau đó không refresh object đã đọc. Cần test hai session cùng đọc bản cũ và tranh lock.
3. Không kiểm parent.status active; cần chặn pending_handover/đã tiêu thụ và race với handover.
4. Ghi BatchEvent với prev_hash genesis mỗi lần, trong khi timeline/integrity đọc Event. AC chuỗi sự kiện/timeline chưa được chứng minh.
5. Child.organization_id lấy tổ chức đang giữ, còn farm_id lấy farm gốc; sau bàn giao khác tổ chức có thể vi phạm FK farm–organization. Cần tách rõ nguồn gốc và quyền giữ.
6. Hai test concurrency hiện chạy tuần tự trên admin_session; chưa chứng minh RLS runtime hoặc tranh chấp giao dịch.
7. Truy ngược trả một root_harvest_id; dữ liệu gộp nhiều gốc cần tập gốc và phát hiện chu trình, không tin một trường denormalized.
8. PR chưa có form tách UI; chưa thể đánh dấu story end-to-end Done.

## Ghi nhận Contributors đúng người

Đối chiếu REST API ngày 11/10: dtc245200244-dotcom (37), hieu-kiien (17), cautim38 (5), minesan2297 (1), trkien412 (1). Đây là thống kê commit hiện tại, không phải điểm đánh giá công sức và có thể thay đổi.

GitHub Contributors chỉ tính commit có nội dung trên default branch; merge/empty commits không được tính. Email author phải liên kết với đúng tài khoản. Push nhánh, gán assignee Jira, mở PR hoặc bấm approve chưa đủ để xuất hiện trong biểu đồ này. Co-authored-by ghi nhận đồng tác giả ở commit/profile khi cấu hình đúng; không bảo đảm riêng biểu đồ Contributors GitHub.com.

Cách có đóng góp thật dù không viết nghiệp vụ chính:
- Nếu thành viên tham gia kiểm tra đáp án, ghi đúng tên và công việc thực tế. Chủ dự án đã bỏ bước bắt buộc chờ hai người; không gán chữ ký hoặc commit giả.
- Một người chạy kịch bản staging và commit báo cáo kết quả, ảnh đã loại dữ liệu cá nhân, bước tái hiện lỗi.
- Một người viết hướng dẫn chạy/demo hoặc test case và tự kiểm bằng thao tác thực tế.
- Một người review PR có nội dung; nếu có sửa/test/tài liệu thật, commit phần đó. Review đơn thuần vẫn có giá trị nhưng không đảm bảo vào biểu đồ commit.

Người thực hiện tự commit bằng tài khoản/email của họ; merge commit giữ các commit gốc, hoặc kiểm tra author/trailers khi squash. Không đổi author hàng loạt, không ký thay, không tạo commit rỗng để tăng số. CONTRIBUTORS.md có thể ghi cả đóng góp kiểm thử/review/đáp án thật; nó không điều khiển biểu đồ GitHub.

## Rủi ro tiến độ trong hai tuần

- 16 story là phạm vi lớn; đường găng: tách/gộp và events → fixture → truy ngược/xuôi → quyền → UI → staging.
- Điều kiện two-person oracle/reviewer đã được chủ dự án cho phép điều chỉnh trong phiên local; khi cập nhật Jira cần nêu rõ thay đổi, không ghi nhận hai người đã kiểm.
- Sprint 2 còn N3-148: API đã có nhưng bàn giao/role staging chưa nghiệm thu; kiểm hồi quy trước khi dựa vào luồng này.
- Ưu tiên xong một nhánh đã chứng minh hơn nhiều nhánh đang dở. Ngày hoàn tất là dự báo sau khi baseline/test rủi ro đầu tiên có kết quả, không cam kết chỉ dựa trên SP.

Nguồn: [Board N3](https://nhom3-k23c.atlassian.net/jira/software/projects/N3/boards/4), [PR #20](https://github.com/nhom-3-cnttk23c/truy-xuat-nguon-goc-chuoi-lanh-nong-san/pull/20), [GitHub Contributors docs](https://docs.github.com/en/repositories/viewing-activity-and-data-for-your-repository/viewing-a-projects-contributors), [GitHub co-author docs](https://docs.github.com/en/pull-requests/how-tos/commit-changes/creating-a-commit-with-multiple-authors).

