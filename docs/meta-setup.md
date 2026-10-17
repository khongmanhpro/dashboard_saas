# Cài đặt phía Meta

Làm sau khi VPS đã chạy (`docs/deploy.md`). Tất cả các bước do **chủ sở hữu** làm trong Meta: tạo mã, dán mã. Tên menu của Meta thay đổi thường xuyên; chỗ nào khác thì tìm mục có ý nghĩa tương tự.

> Đối chiếu tài liệu Meta ngày 17/10/2026. Các chỗ ghi **(chưa thử)** chưa được kiểm tra với Meta thật, phải xác nhận khi làm.

## 0. Ba điều phải biết trước

1. **Chỉ chuyển Live có thể chưa đủ để nhận tin của khách thật.** Theo tài liệu Webhooks của Meta, quyền mức *Standard* chỉ nhận tin từ người có vai trò trong ứng dụng (quản trị viên, nhà phát triển, người thử). Muốn nhận tin từ khách bình thường thì cần mức *Advanced*, và mức này phải qua **App Review**. Trang tổng quan Messenger lại ghi App Review "không bắt buộc nếu chỉ gửi và nhận tin cho Trang của chính mình". Hai trang đang nói khác nhau, nên phải thử thật (mục 6).
2. **Người dùng hệ thống chỉ tạo mã được cho ứng dụng thuộc cùng BM.** BM khác không tạo được người dùng hệ thống "Dashboard" cho ứng dụng của FISSOLUTION. Cách làm với nhiều BM xem mục 8.
3. **Xác minh doanh nghiệp FISSOLUTION phải xong.** Meta yêu cầu xác minh khi ứng dụng có người dùng không có vai trò, và khi xin quyền mức Advanced.

## 1. Ứng dụng Meta

Vào [developers.facebook.com/apps](https://developers.facebook.com/apps):

1. Ứng dụng loại **Business**, thuộc BM **FISSOLUTION**. Nếu ứng dụng đang thuộc tài khoản cá nhân thì vào Cài đặt → Nâng cao để chuyển về BM.
2. Thêm sản phẩm: **Messenger**, **Webhooks**, **Marketing API**.
3. **Cài đặt → Cơ bản:**
   - Tên hiển thị, biểu tượng 1024×1024 (dùng `docs/brand/`), danh mục **Business and pages**.
   - **URL chính sách quyền riêng tư:** `https://<tên miền>/privacy`.
   - **URL hướng dẫn xóa dữ liệu** (chọn loại "Data deletion instructions URL", không phải callback): `https://<tên miền>/data-deletion`. Cách xử lý yêu cầu xóa: README mục "Xử lý yêu cầu xóa dữ liệu của khách".
   - Miền ứng dụng: tên miền của hệ thống (ví dụ `app.vidu.vn`).
4. Chép **App ID** vào `META_APP_ID` và **App Secret** vào `META_APP_SECRET` trong `.env` trên VPS. Chép **phiên bản Graph API** ứng dụng đang dùng (ví dụ `v23.0`) vào `META_GRAPH_VERSION`. Sau đó chạy `scripts/deploy.sh`.

## 2. Webhook

Trong ứng dụng → Webhooks (hoặc Messenger → Cài đặt → Webhooks) → đối tượng **Page**:

| Ô | Giá trị |
|---|---|
| Callback URL | `https://<tên miền>/webhooks/meta` |
| Verify token | Giá trị `META_WEBHOOK_VERIFY_TOKEN` trong `.env` (`grep META_WEBHOOK_VERIFY_TOKEN .env`) |
| Trường đăng ký | `messages`, `message_echoes`, `messaging_referrals`, `leadgen`, `feed` |

Bấm Xác minh và lưu. Meta gọi `GET /webhooks/meta`, hệ thống trả lại `hub.challenge` khi mã khớp. Không cần đăng ký webhook cho từng Trang ở đây: màn hình **Kết nối BM** tự làm việc này.

## 3. Chuyển ứng dụng sang Live

Ứng dụng → **Publish** (Xuất bản). Meta sẽ báo các mục còn thiếu ở Cài đặt cơ bản.

## 4. Người dùng hệ thống "Dashboard"

Trong BM FISSOLUTION, vào [business.facebook.com/settings](https://business.facebook.com/settings) → Người dùng → **Người dùng hệ thống**:

1. **Thêm** → tên `Dashboard`, vai trò **Nhân viên** (không chọn Quản trị viên).
2. **Gán tài sản → Ứng dụng:** chọn ứng dụng ở mục 1.
3. **Gán tài sản → Trang:** chọn từng Trang. Bật **quyền một phần**, chỉ những quyền sau. **Không bật "Toàn quyền kiểm soát"** (CLAUDE.md mục 5):

| Quyền trên Trang (tên trong Meta) | Vì sao cần |
|---|---|
| Tin nhắn (Messages) | Nhận tin của khách (`pages_messaging`) |
| Hoạt động cộng đồng (Community activity) | Đăng ký webhook cho Trang (Meta yêu cầu quyền MODERATE) |
| Thông tin chi tiết (Insights) | Số liệu Trang, bài đăng |
| Khách hàng tiềm năng (Leads) | Lấy form khách hàng tiềm năng (`leads_retrieval`) |

   **Không bật:** Nội dung (đăng bài), Quảng cáo, Nội dung người sáng tạo, Quản lý người sáng tạo. Hệ thống chỉ đọc; chi phí quảng cáo lấy từ tài khoản quảng cáo, không cần quyền Quảng cáo trên Trang. Nếu lấy form khách hàng tiềm năng bị lỗi quyền thì mới thêm Quảng cáo **(chưa thử)**.
4. **Gán tài sản → Tài khoản quảng cáo:** chỉ **Xem hiệu quả** (View performance).
5. **Tạo mã:**
   - Chọn ứng dụng.
   - Thời hạn **Không bao giờ**.
   - Đánh dấu đúng 9 quyền: `pages_show_list`, `pages_read_engagement`, `read_insights`, `pages_read_user_content`, `pages_messaging`, `pages_manage_metadata`, `leads_retrieval`, `ads_read`, `business_management`.
6. Chép mã và **dán thẳng vào màn hình Kết nối BM** của hệ thống. Không dán vào chat, email hay tài liệu. Meta chỉ hiện mã một lần; mất thì tạo mã mới.

## 5. Quyền xem form khách hàng tiềm năng

Cài đặt doanh nghiệp → Tích hợp → **Quyền truy cập khách hàng tiềm năng** (Leads Access). Với từng Trang, cho phép ứng dụng và người dùng `Dashboard`.

Meta chỉ cho cài mục này với **Trang do BM sở hữu**. Trang "thuộc sở hữu cá nhân" hoặc chưa bật quản lý quyền này thì bỏ qua bước này: khi đó người có quyền "Khách hàng tiềm năng" trên Trang vẫn đọc được form **(chưa thử)**.

## 6. Kết nối và thử

1. Đăng nhập hệ thống bằng chủ sở hữu → **Kết nối BM** → dán mã. Hệ thống kiểm tra quyền, liệt kê Trang và tài khoản quảng cáo, rồi đăng ký webhook cho từng Trang. Màn hình báo thiếu quyền nào thì quay lại mục 4.
2. **Thử với người có vai trò:** chủ sở hữu (là quản trị viên ứng dụng) nhắn vào một Trang. Khách phải hiện ở màn hình Khách hàng trong vài giây.
3. **Thử với khách thật:** dùng một nick **không** có vai trò gì trong ứng dụng, nhắn vào Trang.
   - Hiện khách: không cần App Review, làm tiếp mục 7.
   - Không hiện, trong khi bước 2 chạy được: cần **Advanced Access**, xem mục 6a.
4. Trả lời khách từ Meta Business Suite: thời gian trả lời phải được tính (qua `message_echoes`).

### 6a. Xin Advanced Access (nếu bước 3 không qua)

Ứng dụng → **App Review → Permissions and Features** → xin Advanced Access cho `pages_messaging` trước, rồi các quyền còn lại trong danh sách ở mục 4 nếu Meta yêu cầu. Mỗi quyền cần:
- Mô tả ngắn cách dùng: ví dụ "Đo thời gian nhân viên trả lời tin nhắn của khách trên các Trang của doanh nghiệp. Hệ thống chỉ đọc, không gửi tin thay nhân viên."
- Video quay màn hình: khách nhắn vào Trang → khách hiện trong hệ thống → nhân viên trả lời → thời gian trả lời được ghi.
- Tài khoản thử cho người duyệt của Meta: tạo một tài khoản vai trò "Chỉ xem" trên hệ thống.

Việc này mất vài ngày đến vài tuần. Trong lúc chờ, chạy thử được với các nick có vai trò trong ứng dụng.

## 7. Telegram (không bắt buộc)

README mục "Bật cảnh báo Telegram thật".

## 8. Nhiều BM

Người dùng hệ thống ở BM khác **không** được gán ứng dụng của FISSOLUTION (Meta chỉ cho gán khi người dùng hệ thống và ứng dụng thuộc cùng một BM). Đề xuất, **cần sếp duyệt trước khi làm**:

- Ở mỗi BM khác, vào Cài đặt doanh nghiệp → Đối tác → **chia sẻ Trang và tài khoản quảng cáo cho BM FISSOLUTION**.
- Trong BM FISSOLUTION, gán các tài sản đó cho `Dashboard` như mục 4, rồi bấm **Kiểm tra lại** trên màn hình Kết nối BM, hoặc chờ lần kiểm tra tự động 6 giờ một lần. Trang mới tự hiện và tự được đăng ký webhook, không cần mã mới **(chưa thử với Trang được chia sẻ từ BM đối tác)**.

Thiết kế cũ (mỗi BM một người dùng hệ thống, mỗi BM một mã) không làm được với một ứng dụng duy nhất. Màn hình Kết nối BM vẫn dùng được: chỉ có một kết nối, nhưng chứa Trang của nhiều BM.

## 9. Khi mã bị lộ

Cài đặt doanh nghiệp → Người dùng hệ thống → `Dashboard` → **Thu hồi mã**. Tạo mã mới theo mục 4 rồi dán lại vào Kết nối BM.

## Nguồn

- [Webhooks for Messenger Platform](https://developers.facebook.com/documentation/business-messaging/messenger-platform/webhooks)
- [Overview for the Messenger Platform](https://developers.facebook.com/documentation/business-messaging/messenger-platform/overview)
- [System Users overview](https://developers.facebook.com/docs/marketing-api/system-users/overview)
- [Marketing API authentication](https://developers.facebook.com/documentation/ads-commerce/marketing-api/get-started/authentication)
