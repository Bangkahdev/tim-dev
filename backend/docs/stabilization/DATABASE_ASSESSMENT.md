# Database Assessment

- Single SQLite (backend/data/office.db).
- Tables: office + domain_* + dns_records + infra_* + ftp_* + mail_* + network_*.
- Migration: CREATE TABLE IF NOT EXISTS + ALTER with broad except; needs versioning.
- No FK constraints declared.
