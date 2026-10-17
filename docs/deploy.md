# Đưa lên VPS

Hướng dẫn từng bước chạy production trên VPS qua Cloudflare Tunnel (decisions.md mục Q, R, S). Các chỗ ghi **chủ sở hữu** là việc chỉ chủ sở hữu làm: tạo và dán mã, giữ khóa.

## 1. Chuẩn bị

| Thứ | Yêu cầu |
|---|---|
| VPS | Ubuntu 24.04, 2 vCPU, 4 GB RAM, 40 GB SSD, đặt ở Singapore hoặc Việt Nam |
| Tên miền | Dùng nameserver của Cloudflare (ví dụ `app.vidu.vn`) |
| Cloudflare | Một tunnel (README mục "Production qua Cloudflare Tunnel"), một bucket R2 và API token chỉ cho bucket đó (README mục "Sao lưu DB") |
| Máy của chủ sở hữu | Khóa `age` cho sao lưu, tạo bằng `age-keygen`. File khóa giữ ngoài VPS |

## 2. Cài VPS (một lần)

Đăng nhập bằng tài khoản root mà nhà cung cấp cấp, rồi chạy:

```bash
adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy
mkdir -p /home/deploy/.ssh && cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh && chmod 700 /home/deploy/.ssh
passwd deploy   # mật khẩu cho sudo, chủ sở hữu tự đặt

# Chỉ đăng nhập SSH bằng khóa, không cho root đăng nhập.
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/; s/^#\?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart ssh

# Tường lửa: chỉ mở SSH. Đi qua tunnel nên không cần mở 80/443.
ufw allow OpenSSH && ufw --force enable

# Tự cài bản vá bảo mật.
apt-get update && apt-get install -y unattended-upgrades make git
dpkg-reconfigure -f noninteractive unattended-upgrades

# Docker Engine và Compose (theo docs.docker.com/engine/install/ubuntu).
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker deploy
```

Mở một phiên SSH mới bằng `deploy` trước khi đóng phiên root, để chắc vẫn vào được.

## 3. Lấy mã nguồn và tạo `.env`

Từ bước này trở đi đăng nhập bằng `deploy`:

```bash
sudo mkdir -p /opt/fanpage && sudo chown deploy:deploy /opt/fanpage
git clone https://github.com/khongmanhpro/dashboard_saas.git /opt/fanpage
cd /opt/fanpage
make env-prod DOMAIN=app.vidu.vn
```

`make env-prod` sinh bí mật ngẫu nhiên, đặt `APP_ENV=production` và `MOCK_MODE=false`, rồi in tên các biến còn trống. **Chủ sở hữu** mở `.env` (`nano .env`) và điền:

| Biến | Lấy ở đâu |
|---|---|
| `META_APP_ID`, `META_APP_SECRET` | Ứng dụng Meta → Cài đặt → Cơ bản |
| `CLOUDFLARE_TUNNEL_TOKEN` | Cloudflare Zero Trust → Tunnels → tunnel vừa tạo |
| `BACKUP_AGE_RECIPIENT` | Dòng `# public key: age1…` trong file khóa age |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` | Cloudflare R2 → bucket và API token |
| `BOOTSTRAP_WORKSPACE_NAME`, `BOOTSTRAP_OWNER_EMAIL`, `BOOTSTRAP_OWNER_PASSWORD` | Tên doanh nghiệp, email và mật khẩu tạm của chủ sở hữu (hệ thống bắt đổi ở lần đăng nhập đầu) |
| `TELEGRAM_BOT_TOKEN` | Không bắt buộc. Bot tạo qua @BotFather |

Không dán các mã này vào chat, tài liệu hay git. `.env` có quyền 600 và nằm ngoài git.

## 4. Chạy lần đầu

```bash
scripts/deploy.sh
docker compose -f docker-compose.prod.yml -f docker-compose.tunnel.yml run --rm migrate python -m app.cli bootstrap-owner
```

Chạy xong thì xóa giá trị `BOOTSTRAP_OWNER_PASSWORD` trong `.env`.

Kiểm tra:

1. `https://app.vidu.vn/healthz` trả `{"status":"ok"}`. Đăng nhập bằng tài khoản chủ sở hữu, đổi mật khẩu.
2. `docker compose -f docker-compose.prod.yml -f docker-compose.tunnel.yml ps`: `backend` là `healthy`. `backup` sao lưu ngay ở lần đầu nên phải lên `healthy`. Nếu `unhealthy` thì xem `logs backup`, thường do thiếu biến R2.
3. Cloudflare R2: bucket có một file `fanpage-….dump.age`.

## 5. Nối webhook Meta

Ứng dụng Meta → Webhooks → Page:

- Callback URL: `https://app.vidu.vn/webhooks/meta`
- Verify token: giá trị `META_WEBHOOK_VERIFY_TOKEN` trong `.env` (xem bằng `grep META_WEBHOOK_VERIFY_TOKEN .env`).

Sau đó làm theo README mục "Nối với Meta thật".

## 6. Cập nhật bản mới

Khi `main` có bản mới mà chủ sở hữu muốn đưa lên:

```bash
cd /opt/fanpage && scripts/deploy.sh
```

Script sao lưu ngay, `git pull`, build, chạy migration, chờ backend khỏe rồi in trạng thái. Sao lưu lỗi thì script dừng và không cập nhật. Vì vậy phải cấu hình R2 xong trước lần cập nhật đầu tiên: thiếu R2 thì sao lưu bị tính là lỗi (decisions.md mục R4).

## 7. Khi có sự cố

| Việc | Lệnh (thêm `-f docker-compose.tunnel.yml` sau `-f docker-compose.prod.yml`) |
|---|---|
| Xem trạng thái | `docker compose -f docker-compose.prod.yml ps` |
| Xem log | `docker compose -f docker-compose.prod.yml logs --tail 100 backend worker` |
| Khởi động lại | `docker compose -f docker-compose.prod.yml restart backend worker` |
| Khôi phục DB | README mục "Sao lưu DB" |
| Trang không vào được | Kiểm tra `logs cloudflared` và trạng thái tunnel trên dashboard Cloudflare |
