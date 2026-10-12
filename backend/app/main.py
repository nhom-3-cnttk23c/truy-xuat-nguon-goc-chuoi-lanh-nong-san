import asyncio
import os
import re
import time
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.endpoints import auth
from app.api.v1.router import api_router
from app.core.audit import AuditMiddleware
from app.core.config import settings
from app.core.database import engine
from app.jobs import scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_runtime()
    app.state.maintenance_started = True
    task = asyncio.create_task(scheduler.run_hourly())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        app.state.maintenance_started = False


app = FastAPI(
    title="Cold Chain Traceability API",
    description="API hệ thống truy xuất nguồn gốc và giám sát chuỗi lạnh nông sản",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Authorization"],
)
app.add_middleware(AuditMiddleware)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(auth.session_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(api_router, prefix="/api/v1")

FRONTEND_URL = "https://ttcs-frontend-staging.onrender.com"

HTML_LANDING = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AgroChain — Cổng Dịch vụ API Backend</title>
  <style>
    :root { --brand: #15803d; --brand-dark: #166534; --bg: #f8fafc; --card: #ffffff; --text: #0f172a; --sub: #64748b; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 24px; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
    .card { background: var(--card); max-width: 540px; width: 100%; border-radius: 16px; padding: 36px 32px; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.06), 0 8px 10px -6px rgba(0,0,0,0.04); border: 1px solid #e2e8f0; text-align: center; }
    .status-badge { display: inline-flex; align-items: center; gap: 8px; background: #dcfce7; color: var(--brand-dark); padding: 6px 14px; border-radius: 999px; font-size: 13px; font-weight: 600; margin-bottom: 20px; }
    .status-dot { width: 8px; height: 8px; background: #22c55e; border-radius: 50%; box-shadow: 0 0 0 3px rgba(34,197,94,0.25); }
    h1 { font-size: 22px; margin: 0 0 10px 0; color: #0f172a; }
    p.desc { color: var(--sub); font-size: 14px; line-height: 1.6; margin: 0 0 28px 0; }
    .btn-group { display: flex; flex-direction: column; gap: 12px; }
    .btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; padding: 14px 20px; border-radius: 10px; font-size: 15px; font-weight: 600; text-decoration: none; transition: all 0.2s; }
    .btn-primary { background: var(--brand); color: #ffffff; box-shadow: 0 4px 12px rgba(21,128,61,0.25); }
    .btn-primary:hover { background: var(--brand-dark); transform: translateY(-1px); }
    .btn-secondary { background: #f1f5f9; color: #334155; border: 1px solid #cbd5e1; }
    .btn-secondary:hover { background: #e2e8f0; }
    .note { margin-top: 24px; padding-top: 20px; border-top: 1px solid #f1f5f9; font-size: 12px; color: var(--sub); line-height: 1.5; }
  </style>
</head>
<body>
  <div class="card">
    <div class="status-badge"><span class="status-dot"></span> Máy chủ Backend đang Hoạt động (Online)</div>
    <h1>AgroChain Backend API</h1>
    <p class="desc">Bạn đang truy cập vào cổng dịch vụ API của hệ thống Giám sát Chuỗi lạnh &amp; Truy xuất Nguồn gốc Nông sản (Nhóm TTCS_T926_K18C4_N3 — TTCS).</p>
    <div class="btn-group">
      <a href="https://ttcs-frontend-staging.onrender.com" class="btn btn-primary">
        🚀 Mở Giao diện Web Người dùng (Frontend)
      </a>
      <a href="/docs" class="btn btn-secondary">
        📖 Xem Tài liệu &amp; Thử nghiệm API (Swagger UI)
      </a>
    </div>
    <div class="note">
      💡 <b>Dành cho thành viên nhóm:</b> Để sử dụng phần mềm, các bạn chỉ cần bấm vào nút <b>Mở Giao diện Web</b> ở trên. Toàn bộ tính năng đều có thể dùng trực tiếp trên trình duyệt.
    </div>
  </div>
</body>
</html>"""

HTML_404 = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>404 — Không tìm thấy đường dẫn | AgroChain</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8fafc; color: #0f172a; margin: 0; padding: 24px; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
    .card { background: #ffffff; max-width: 520px; width: 100%; border-radius: 16px; padding: 36px 32px; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; text-align: center; }
    .icon { font-size: 40px; margin-bottom: 12px; }
    h1 { font-size: 20px; margin: 0 0 8px 0; }
    p { color: #64748b; font-size: 14px; line-height: 1.6; margin: 0 0 24px 0; }
    .btn-group { display: flex; flex-direction: column; gap: 10px; }
    .btn { display: inline-flex; align-items: center; justify-content: center; padding: 12px 18px; border-radius: 8px; font-size: 14px; font-weight: 600; text-decoration: none; }
    .btn-primary { background: #15803d; color: #ffffff; }
    .btn-secondary { background: #f1f5f9; color: #334155; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">🔍</div>
    <h1>404 — Đường dẫn không tồn tại</h1>
    <p>Địa chỉ bạn vừa truy cập không có trên máy chủ API Backend (có thể do dán nhầm đường dẫn hoặc trùng lặp tên miền). Vui lòng chọn một trong các liên kết bên dưới:</p>
    <div class="btn-group">
      <a href="https://ttcs-frontend-staging.onrender.com" class="btn btn-primary">
        👉 Mở Giao diện Web (Frontend)
      </a>
      <a href="/docs" class="btn btn-secondary">
        📖 Xem Tài liệu Kỹ thuật API (/docs)
      </a>
    </div>
  </div>
</body>
</html>"""


@app.get("/", tags=["health"])
def health_check(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept and "application/json" not in accept:
        return HTMLResponse(content=HTML_LANDING)
    return {"status": "ok", "message": "Backend service is online"}


@app.get("/health", tags=["health"])
def readiness():
    if getattr(app.state, "maintenance_started", False) and (
        scheduler.last_success is None
        or time.monotonic() - scheduler.last_success > 7200
    ):
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}


@app.get("/version", tags=["health"])
def release_version():
    commit = os.getenv("RENDER_GIT_COMMIT") or os.getenv("APP_COMMIT_SHA", "")
    return {"commit": commit if re.fullmatch(r"[a-fA-F0-9]{40}", commit) else None}


@app.exception_handler(404)
async def custom_404_handler(request: Request, exc: Exception):
    accept = request.headers.get("accept", "")
    if "text/html" in accept and "application/json" not in accept:
        return HTMLResponse(content=HTML_404, status_code=404)
    return JSONResponse(
        status_code=404,
        content={
            "detail": "Not Found",
            "message": "Đường dẫn không tồn tại trên máy chủ Backend.",
            "frontend_url": FRONTEND_URL,
            "docs_url": "/docs",
        },
    )
