.PHONY: help install dev-backend dev-frontend test lint lint-fix migrate migration

help:
	@echo "Các lệnh phát triển dự án:"
	@echo "  make install        Cài đặt thư viện cho backend và frontend"
	@echo "  make dev-backend    Chạy máy chủ phát triển Backend (FastAPI)"
	@echo "  make dev-frontend   Chạy máy chủ phát triển Frontend (Vite)"
	@echo "  make test           Chạy bộ kiểm thử tự động (Pytest)"
	@echo "  make lint           Kiểm tra quy chuẩn mã nguồn"
	@echo "  make lint-fix       Tự động định dạng và sửa lỗi lint"
	@echo "  make migrate        Nâng cấp cơ sở dữ liệu lên bản mới nhất"
	@echo "  make migration      Tạo file migration mới (vd: make migration msg='init')"

install:
	cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
	cd frontend && npm ci

dev-backend:
	cd backend && .venv/Scripts/python -m app.startup

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && .venv/Scripts/pytest tests/ -v

lint:
	cd backend && .venv/Scripts/ruff check app/ tests/ alembic/
	cd frontend && npm run lint

lint-fix:
	cd backend && .venv/Scripts/ruff check --fix app/ tests/ alembic/ && .venv/Scripts/ruff format app/ tests/ alembic/

migrate:
	cd backend && .venv/Scripts/alembic upgrade head

migration:
	cd backend && .venv/Scripts/alembic revision --autogenerate -m "$(msg)"
