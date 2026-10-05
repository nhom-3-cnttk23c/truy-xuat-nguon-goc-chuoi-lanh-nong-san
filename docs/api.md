# Tài liệu đặc tả API

Tài liệu kỹ thuật mô tả các RESTful API của hệ thống. Để thử nghiệm trực tiếp các endpoint, truy cập giao diện Swagger UI tại `/docs` khi máy chủ Backend đang hoạt động.

## Base URL

| Môi trường | Địa chỉ |
|---|---|
| Local | `http://localhost:8000` |
| Staging | `https://ttcs-backend-staging.onrender.com` |

---

## Authentication

- Login: POST /api/v1/auth/login with email and password.
- Session cookie: __Host-session; HttpOnly, Secure, SameSite=Lax.
- Current user: GET /api/v1/auth/me.
- Logout: POST /api/v1/auth/logout.

Browser clients authenticate through the cookie. The API does not return or
accept a session token in a response header.

## Endpoints

### 1. Health Check
Kiểm tra trạng thái hoạt động của dịch vụ Backend.

- **Method:** `GET`
- **Path:** `/`
- **Response `200 OK`:**
```json
{
  "status": "ok",
  "message": "Backend service is online"
}
```

### 2. Farms

- List farms in the caller's organization: GET /api/v1/farms/
- Create a farm: POST /api/v1/farms/
- Read a farm: GET /api/v1/farms/{farm_id}
- Update a farm: PUT /api/v1/farms/{farm_id}

The organization is taken from the authenticated principal. Farm IDs remain
stable when a farm is renamed.

### 3. Lots

- List lots: GET /api/v1/lots/
- Read a lot: GET /api/v1/lots/{lot_id}

Lots have stable IDs and foreign keys to both their organization and farm.
Ordinary users see lots from their own organization; inspectors can read all
organizations. The API exposes no lot write routes.

### 4. Events (Cold Chain Traceability Log — N3-20 & N3-21)

- List events: GET /api/v1/events/
- Read an event: GET /api/v1/events/{event_id}
- Record an event: POST /api/v1/events/

#### Nguyên tắc bất biến và chỉ ghi nối tiếp (N3-21):
- **Không có đường sửa hay xoá:** API hoàn toàn không cung cấp các route `PUT`, `PATCH`, hay `DELETE` cho thực thể sự kiện. Mọi yêu cầu thay đổi qua HTTP method này đều trả về `405 Method Not Allowed`.
- **RBAC không cấp quyền sửa/xoá:** Các vai trò nghiệp vụ chỉ được cấp quyền `events:create`, `events:read`, hoặc `events:read_all`. Không tồn tại quyền `events:update` hoặc `events:delete`.
- **Chuỗi băm nối tiếp:** Mỗi sự kiện khi tạo được gắn số thứ tự tăng dần (`sequence_number`), liên kết với mã băm của sự kiện trước (`prev_hash`) và tạo mã băm mới (`event_hash`) theo chuẩn RFC 8785 (Canonical JSON) + SHA-256.

