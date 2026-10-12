# Frontend AgroChain

React, TypeScript và Vite. Hướng dẫn chạy: [README](../README.md); trình diễn: [UX-DEMO](../docs/UX-DEMO.md).

Chạy `npm ci`, đặt `VITE_BACKEND_TARGET=http://127.0.0.1:8000` cho API local rồi `npm run dev`.

`VITE_BACKEND_TARGET` dùng cho proxy dev; `VITE_API_BASE_URL` dùng khi build/deploy. Chỉ đặt địa chỉ API công khai, không đưa mật khẩu/token vào biến Vite.

Kiểm tra: `npm test`, `npm run lint`, `npm run build`, `npm audit`. Test HTML chạy offline; nghiệm thu giao diện tương tác cần thực hiện riêng.

Không commit `node_modules/`, `dist/`, cache hoặc `.env`. Dùng hàm API và kiểu dữ liệu chung trong `src/services/api.ts` và `src/types/index.ts`, tránh lớp gọi API trùng.
