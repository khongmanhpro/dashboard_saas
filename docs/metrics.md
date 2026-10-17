# Định nghĩa chỉ số

Nguồn tính duy nhất: `backend/app/services/metrics.py` (decisions.md mục J). Mọi màn hình gọi chung
module này; không màn nào tự đếm riêng.

## Kỳ và tập khách

- **Múi giờ:** giờ của workspace, mặc định Asia/Ho_Chi_Minh (= Asia/Saigon). Thời gian lưu UTC.
- **Kỳ:** các ngày trọn theo giờ địa phương, nửa mở `[00:00 ngày đầu, 00:00 ngày sau ngày cuối)`, cắt
  tới thời điểm hiện tại. "Hôm nay" = từ 00:00 hôm nay. "7 ngày" = hôm nay và 6 ngày trước. "30 ngày"
  tương tự. "Tuần" = Thứ Hai – Chủ Nhật (kỳ điểm chính thức). Kỳ trước = cùng độ dài, liền trước.
- **Một khách** = một đợt của cặp (Trang, PSID). Khách nhắn lại trong 30 ngày vẫn là đợt cũ, không
  tính lại. Im lặng hơn 30 ngày rồi nhắn lại thì mở đợt mới và được tính là khách mới ở kỳ của đợt mới.
- **Khách của kỳ:** đợt có **tin đầu tiên** nằm trong kỳ. Đợt từ form đã gộp vào đợt nhắn tin không
  tính riêng.
- **Người phụ trách của khách:** người phụ trách Trang lúc khách nhắn tin đầu tiên, cố định về sau.
  Trang lúc đó chưa có ai thì khách thuộc nhóm "Chưa có người phụ trách" và không tính điểm cho ai.
- **Lọc theo nhóm / phạm vi vai trò:** lọc theo người phụ trách của **khách** (không theo người đang
  phụ trách Trang). Khách chưa có người phụ trách chỉ có khi xem toàn workspace, không lọc nhóm.

## Chỉ số khách

| Chỉ số | Định nghĩa |
|---|---|
| Khách mới | Số khách của kỳ. |
| Đã trả lời | Trang đã trả lời tin đầu tiên (không tính tin tự động), **hoặc** nhân viên đã đánh dấu "Đã gọi", **hoặc** trạng thái khác "Mới". |
| Chưa trả lời | Khách mới − Đã trả lời. |
| Có SĐT (phễu) | Đã trả lời **và** có SĐT. |
| Chưa lấy SĐT | Đã trả lời − Có SĐT (phễu). |
| Đã gọi (phễu) | Có SĐT (phễu) **và** đã đánh dấu "Đã gọi". |
| Có SĐT chưa gọi | Có SĐT (phễu) − Đã gọi. |
| Chốt / Hủy / Hẹn lại | Trạng thái hiện tại của khách. |
| Đang chờ | Trạng thái "Mới" hoặc "Đã liên hệ". Chốt + Hủy + Hẹn lại + Đang chờ = Khách mới. |
| Có số điện thoại (%) | Khách có SĐT (kể cả chưa được trả lời, khách form) ÷ Khách mới. Đây cũng là tiêu chí điểm. |
| Tỉ lệ chốt | Chốt ÷ Khách mới. |
| Doanh thu | Tổng giá trị đơn của các khách Chốt trong tập khách của kỳ. |
| Thời gian trả lời | **Trung vị** số giây trong giờ làm việc từ tin đầu tiên của khách tới tin trả lời đầu tiên. Chỉ khách nhắn tin (khách form không đo). Khách chưa được trả lời đã chờ ≥ 120 phút tính bằng 120 phút; chờ ít hơn thì chưa tính. |
| Quá hạn 48 giờ (trong kỳ) | Khách của kỳ chưa có kết quả và đã qua hạn 48 giờ. |
| Bài đăng | Bài có thời điểm đăng trong kỳ. Fanpage đếm theo Trang, điểm Chăm Trang đếm theo người phụ trách lúc đăng; cùng kỳ thì Trang không đổi người cho cùng số. |
| Quá hạn 48 giờ (thẻ cảnh báo Tổng quan) | Như trên nhưng **mọi thời điểm**, không giới hạn kỳ. |

## Điểm

- Công thức và trọng số: CLAUDE.md mục 3, decisions.md mục A, F, I. Tính trên đúng tập khách ở trên,
  nhóm theo người phụ trách.
- Kỳ chưa chốt tính trực tiếp mỗi lần xem; tuần đã chốt đọc từ `score_snapshots` (không tính lại).
- Quy đổi về 0–100 (decisions.md mục K): mọi tiêu chí trừ Chăm Trang theo **ngưỡng tuyệt đối** sửa được
  trong Cài đặt: tới ngưỡng "0 điểm" là 0, từ ngưỡng "100 điểm" là 100, ở giữa theo tỉ lệ. Mặc định:
  Tốc độ 120 → 5 phút, Chốt 5% → 30%, Doanh thu 0 → 20 triệu/tuần (quy theo số ngày đã qua của kỳ),
  % có SĐT 30% → 80%, Đúng hạn 50% → 95%. Chăm Trang theo mục tiêu bài.

## Ràng buộc luôn đúng (có test)

Với cùng kỳ và cùng nhóm:

- Tổng các dòng ở /staff (gồm dòng "Chưa có người phụ trách") = tổng các Trang ở /pages = Tổng quan,
  cho Khách mới, Chốt, Doanh thu.
- Chưa trả lời = Khách mới − Đã trả lời; Chưa lấy SĐT = Đã trả lời − Có SĐT; Có SĐT chưa gọi = Có SĐT
  − Đã gọi; Chốt + Hủy + Hẹn lại + Đang chờ = Khách mới.
- Điểm của một người giống nhau ở Tổng quan, /staff, /staff/:id, /pages khi cùng kỳ.
