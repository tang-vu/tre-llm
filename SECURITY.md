# Security Policy

## Báo cáo lỗ hổng

Mở GitHub issue với label `security` hoặc liên hệ maintainer qua thông tin trong
hồ sơ GitHub `tang-vu`. Không đăng PoC công khai trước khi fix.

## Mô hình bảo mật v0.1

- Server bind loopback mặc định; `--host` khác là chủ động của người dùng.
- Host header được kiểm tra cho `/v1/*` và `/api/*`; mutating endpoints kiểm Origin.
- CORS same-origin; không expose ra LAN trừ khi người dùng tự cấu hình.
- Download: sha256 bắt buộc, atomic rename, chặn path traversal trong `import_local`.
- Không thực thi metadata tải về; `trust_remote_code` mặc định tắt.
- Tài liệu nạp vào được coi là dữ liệu, không phải chỉ thị (prompt tách biệt) —
  đã có test chống injection trong eval suite.
- Hội thoại/tài liệu là plaintext trong SQLite cục bộ — không mã hoá ở v0.1.

## Không bảo đảm

- Không bảo vệ chống attacker đã có quyền đọc filesystem user.
- `--attach` server ngoài là tự nguyện — không bảo mật kênh ngoài.
