# Mô hình dữ liệu (thiết kế cho cả 7 bước)

Quy ước chung:

- Mọi bảng nghiệp vụ có `workspace_id uuid NOT NULL` và bật **Row-Level Security**. Ngoại lệ được ghi rõ ở cuối file.
- Khóa chính là `id uuid` (UUIDv7). Bảng ghi nhiều (tin nhắn, sự kiện) dùng `bigint identity`.
- Khóa ngoại tới bảng nghiệp vụ khác dùng cặp `(workspace_id, <bảng>_id)` → `(workspace_id, id)`, nên không thể trỏ chéo workspace.
- Thời gian là `timestamptz` (lưu UTC). Ngày tổng hợp (`date`) tính theo múi giờ của workspace; riêng số liệu quảng cáo theo múi giờ của tài khoản QC.
- Tiền là `bigint`, tên cột kết thúc bằng `_vnd`. Tiền gốc của tài khoản QC dùng `_minor` (đơn vị nhỏ nhất) kèm `currency`.
- Mã truy cập lưu dạng `bytea` đã mã hóa Fernet (`*_ciphertext`), kèm `*_last4` để hiển thị.
- Cột "Bước" cho biết migration nào tạo bảng.

## Tenant & người dùng (Bước 1)

| Bảng | Cột chính | Ghi chú |
|---|---|---|
| `workspaces` | name, slug (unique), timezone, plan_code, status | RLS theo `id`. |
| `users` | email (citext, unique), full_name, password_hash, must_change_password, is_active, last_login_at | **Toàn cục**, không thuộc workspace. |
| `workspace_members` | user_id, role (`owner`/`manager`/`team_lead`/`staff`/`viewer`), team_id, status (`active`/`disabled`) | unique(workspace_id, user_id). |
| `teams` | name, lead_member_id | unique(workspace_id, name). |
| `workspace_settings` | work_start, work_end, slow_reply_minutes, result_deadline_hours, lead_session_gap_days, posts_per_week_target, min_leads_for_ranking, one_page_per_member, staff_can_see_leaderboard | Một dòng mỗi workspace. |
| `auth_sessions` | user_id, workspace_id, token_hmac (unique), csrf_hmac, created_at, last_seen_at, expires_at, idle_expires_at, revoked_at, ip, user_agent | Tra theo token **trước khi** biết workspace nên không bật RLS. |
| `audit_logs` | actor_member_id, action, entity_type, entity_id, before, after (jsonb), ip, created_at | Không bao giờ ghi mã truy cập hay mật khẩu. |
| `password_tokens` *(khi làm luồng mời/đặt lại mật khẩu)* | user_id, purpose, token_hmac, expires_at, used_at | Toàn cục. |

## Kết nối Meta (Bước 2 với fixture, Bước 6 màn hình)

| Bảng | Cột chính |
|---|---|
| `business_managers` | fb_business_id, name, verification_status, system_user_id, token_ciphertext, token_last4, token_fingerprint, scopes text[], status (`active`/`missing_permissions`/`disconnected`), status_detail, last_checked_at, last_synced_at, connected_by_member_id |
| `pages` | business_manager_id, fb_page_id, name, category, page_token_ciphertext, webhook_fields text[], webhook_subscribed_at, is_tracked, access_status. **Unique `fb_page_id` trong các Trang `is_tracked`** (toàn hệ thống). |
| `ad_accounts` | business_manager_id, fb_ad_account_id, name, currency, timezone_name, status, access_status |
| `page_assignments` | page_id, member_id, valid_from, valid_to (NULL = đang hiệu lực), assigned_by_member_id, reason. **`EXCLUDE USING gist (page_id WITH =, tstzrange(valid_from, valid_to) WITH &&)`**: một Trang không có hai người cùng lúc. Ràng buộc "1 nhân viên – 1 Trang" kiểm tra ở service theo cài đặt. |
| `sync_runs` | business_manager_id, kind, started_at, finished_at, status, error, usage (jsonb của `X-Business-Use-Case-Usage`) |

## Nhận dữ liệu (Bước 2)

| Bảng | Cột chính |
|---|---|
| `webhook_events` | `bigint` id, received_at, object, fb_page_id, dedupe_key (unique trong workspace), kind, payload jsonb, status (`processed`/`ignored`/`failed`), attempts, error, processed_at. Xóa sau 30 ngày. Worker chỉ ghi **sau khi** định tuyến được Trang sang workspace, nên `workspace_id` NOT NULL như mọi bảng khác. |
| `leadgen_submissions` | leadgen_id (**unique**), page_id, form_id, fb_ad_id, created_time, field_data (chỉ giữ trường cần), fetch_status (`fetched`/`pending`), lead_id |

Định tuyến webhook: worker không biết workspace trước khi đọc Trang, nhưng không được dùng tài khoản quản trị DB. Hàm `app_route_page(fb_page_id)` (`SECURITY DEFINER`, `search_path` cố định) chỉ trả về `workspace_id` của Trang đang theo dõi; tài khoản ứng dụng chỉ có quyền EXECUTE hàm này. Sự kiện của Trang không ai theo dõi bị bỏ, log chỉ ghi `fb_page_id`.

## Khách (Bước 2–3)

| Bảng | Cột chính |
|---|---|
| `contacts` | page_id, psid, first_seen_at, last_inbound_at. unique(page_id, psid). |
| `leads` (một đợt) | page_id, contact_id (NULL nếu chỉ từ form), episode_no, **owner_member_id** (NULL khi Trang chưa có người), source (`message`/`leadgen`), ad_id, campaign_id (*thêm ở Bước 7, khi có bảng quảng cáo*), fb_ad_id (bản gốc khi chưa đồng bộ QC), referral (jsonb), first_inbound_at, first_inbound_mid, first_reply_at, first_reply_mid, **response_business_seconds**, status (`new`/`contacted`/`callback`/`won`/`lost`), status_changed_at, callback_at, won_value_vnd, lost_reason (`price`/`out_of_area`/`no_answer`/`bought_elsewhere`/`other`), lost_note, called_at, phone, phone_source, phone_captured_at, result_due_at, result_at, last_inbound_at. CHECK: `won ⇒ won_value_vnd > 0`, `lost ⇒ lost_reason IS NOT NULL`, `callback ⇒ callback_at IS NOT NULL`. |
| `messages` | `bigint` id, page_id, contact_id, lead_id (**được NULL**: echo đến trước tin của khách, hoặc Trang nhắn trước), mid (**unique**), direction (`in`/`out`), is_echo, app_id, is_automated, sent_at, text (xóa sau 180 ngày), has_attachments, meta jsonb |
| `lead_phones` | lead_id, phone, source, message_id, detected_at. unique(lead_id, phone). |
| `lead_events` | `bigint` id, lead_id, type (`created`, `replied`, `phone_detected`, `called`, `status_changed`, `overdue`, `reminder_sent`, `reassigned`), actor_member_id, data jsonb, occurred_at |

Mở đợt mới: khóa dòng `contacts` (`SELECT … FOR UPDATE`) rồi mới quyết định, để hai sự kiện đến cùng lúc không tạo ra hai đợt.

## Điểm (Bước 4)

| Bảng | Cột chính |
|---|---|
| `score_formulas` | version, w_close_rate, w_response_speed, w_revenue, w_phone_rate, w_page_care, w_on_time (CHECK tổng = 100), speed_full_minutes (5), speed_zero_minutes (120), tier_a (85), tier_b (70), tier_c (50), min_leads (10), posts_per_week_target (5), effective_from, created_by_member_id |
| `score_snapshots` | member_id, formula_id, period_type (`week`/`rolling_7`/`rolling_30`/`month`), period_start, period_end, computed_at, lead_count, chỉ số thô (close_rate, median_response_seconds, revenue_vnd, phone_rate, posts_count, on_time_rate), 6 điểm thành phần numeric(5,2), total, tier, insufficient_data, rank, **is_final**. unique(workspace_id, member_id, period_type, period_start). Dòng `is_final` không bao giờ bị ghi đè. |

## Điện thoại nhân viên (Bước 5)

| Bảng | Cột chính |
|---|---|
| `notifications` | member_id, lead_id, type, title, body, created_at, read_at, sent_via |
| `push_subscriptions` | member_id, endpoint, p256dh, auth, created_at |

## Nhập Excel (Bước 6)

| Bảng | Cột chính |
|---|---|
| `import_jobs` | type, file_name, status, rows_total, rows_ok, rows_failed, report jsonb, created_by_member_id. Không lưu file gốc. |

## Quảng cáo, Trang, cảnh báo (Bước 7)

| Bảng | Cột chính |
|---|---|
| `campaigns` / `ad_sets` / `ads` | fb_id, ad_account_id, cấp cha, name, objective, status, daily_budget_minor; `ads.page_id` |
| `ad_insights_daily` | level, object_id, date, spend_minor, currency, **spend_vnd**, impressions, reach, clicks, results, messaging_starts, leads. unique(level, object_id, date). |
| `fx_rates` | date, currency, vnd_per_unit numeric. **Toàn cục.** |
| `page_posts` | page_id, fb_post_id (unique), created_time, type, excerpt, permalink, reactions, comments, shares, views |
| `page_insights_daily` | page_id, date, followers, new_follows, views, reach, engagements, video_views |
| `alert_rules` | type, enabled, params jsonb, channels |
| `alert_deliveries` | rule_id, target, payload, status, sent_at |
| `member_telegram` | member_id, chat_id |

## Ngoại lệ của quy tắc "workspace_id + RLS"

| Bảng | Lý do |
|---|---|
| `users`, `password_tokens`, `fx_rates` | Dữ liệu toàn cục, không thuộc workspace nào. |
| `auth_sessions` | Có `workspace_id` nhưng không bật RLS: phải tra theo token trước khi biết workspace. |
| `workspaces` | Bản thân nó là tenant; RLS theo `id`. |
