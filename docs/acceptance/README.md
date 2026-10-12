# Snapshot Jira Sprint 1–4

`sprint-1-4.csv` là artifact có thể sinh lại từ JSON Jira chứa `rows`. Không coi cột trạng thái là kết quả nghiệm thu.

Tái tạo: `python docs/acceptance/export_snapshot.py <jira-snapshot.json> docs/acceptance/sprint-1-4.csv`.

Giữ key, parent và nguyên văn AC/NFR để đối chiếu đủ 92 mục; kết luận hiện hành nằm ở [ACCEPTANCE](../ACCEPTANCE.md). Không lưu thông tin tài khoản/token trong snapshot.
