# AgroChain — Truy xuất nguồn gốc nông sản

Học phần TTCS, nhóm TTCS_T926_K18C4_N3. Quản lý vùng trồng, nông sản, lô thu hoạch, bàn giao, tách/gộp, nguồn gốc, phân phối và nhật ký.

## Sử dụng
- [Web staging](https://ttcs-frontend-staging.onrender.com)
- [API tương tác](https://ttcs-backend-staging.onrender.com/docs)
- [Hướng dẫn demo từng vai trò](docs/UX-DEMO.md)
- [Tài liệu và tình trạng nghiệm thu](docs/README.md)

Chức năng cảm biến tự động, thu hồi, QR và báo cáo PDF thuộc sprint sau. Có thể ghi sự kiện thủ công; không coi đó là tích hợp cảm biến đã hoàn thành.

## Chạy local
Yêu cầu Docker Desktop:
```sh
cp .env.example .env
# Điền DB_PASSWORD và DB_ADMIN_PASSWORD trong .env.
docker compose up --build -d
```
Web: http://localhost:5173. API: http://localhost:8000/docs.
Dừng bằng `docker compose down`; không thêm `-v` nếu cần giữ dữ liệu.

Chạy trực tiếp (Python 3.12+, Node 20+, PostgreSQL 15+):
```sh
cd backend
python -m venv .venv
# Kích hoạt .venv theo hệ điều hành.
pip install -r requirements-dev.txt
cp .env.example .env
# Điền mật khẩu và địa chỉ DB vào .env.
python -m app.startup
```
Trong terminal khác:
```sh
cd frontend
npm ci
npm run dev
```
Đặt `VITE_BACKEND_TARGET` khi cần frontend dev proxy đến API local.

## Dữ liệu demo
Seed chỉ chạy khi `APP_ENV=development` hoặc `staging`; production không tự tạo tài khoản mẫu.
Mật khẩu demo lấy từ `DEMO_PASSWORD`, mặc định `Password123!` chỉ dành cho môi trường mẫu. Các vai trò/email xem trên trang `/demo`. Không dùng dữ liệu cá nhân thật để trình diễn.

## Kiểm tra
Backend local dùng **DB riêng**, không dùng DB đang trình diễn:
```powershell
cd backend
./scripts/test-local.ps1 -TestArgs @('-q', '-m', 'not performance', '--cov=app', '--cov-report=json:coverage.json')
./scripts/test-local.ps1 -TestArgs @('-q', '-m', 'performance')
```
Script này dành cho bộ PostgreSQL local đã cấu hình tại cổng 55434, DB `ttcs_s34_tests`. Với môi trường khác, cấu hình DB test riêng trước khi chạy `pytest`. Hook test chặn DB trình diễn local.
```sh
ruff check app tests alembic
ruff format --check app tests alembic
# Trong frontend:
npm test
npm run lint
npm run build
npm audit
```
CI chạy lint, test, typecheck/build, migration, quét thư viện và build images. Coverage được lưu thành artifact. Test xanh không thay nghiệm thu tương tác trên staging.

## Vận hành
- `python -m app.startup`: kiểm cấu hình, chuẩn bị quyền DB, migrate trước khi phục vụ. Thiếu mật khẩu hoặc migration lỗi sẽ dừng.
- `GET /health`: readiness DB và tình trạng job bảo trì; trả 503 khi chưa sẵn sàng.
- `GET /version`: SHA bản phát hành; không lộ thông tin cấu hình.
- Job quá hạn chạy khi web khởi động và mỗi giờ bằng một hàm DB chỉ được phép đánh dấu bàn giao chờ quá hạn. Web không giữ mật khẩu migration.
- GitHub workflow định kỳ gọi health để đánh thức Render miễn phí. Lịch GitHub có thể trễ; free tier không có cam kết thời gian thực.
- Render health check dùng `/health`; deploy workflow kiểm SHA đúng commit và hợp đồng API Sprint 1–4. Không lấy OpenAPI của bản cũ làm bằng chứng triển khai thành công.
- Staging hiện dùng Render native build; Docker images gắn SHA là kiểm chứng build/tính truy vết, không phải images đang chạy trên Render.

## An toàn và đóng góp
API kiểm RBAC, PostgreSQL kiểm RLS theo session. Sự kiện chỉ thêm; hash SHA-256/RFC 8785 giúp phát hiện sửa đổi nhưng không phải chữ ký số hay bằng chứng chống quản trị viên viết lại cả chuỗi. Chi tiết: [DB](docs/database.md), [toàn vẹn](docs/N3-4-INTEGRITY.md).

Đóng góp qua nhánh và PR theo [CONTRIBUTING.md](CONTRIBUTING.md). Giữ tác giả thật; không dùng số commit/Contributors để chứng minh nghiệm thu. Chỉ chuyển Jira Done khi có đủ bằng chứng theo DoD hoặc có điều chỉnh được ghi nhận.
