# Phân quyền

Nguồn sự thật duy nhất: `backend/app/core/rbac.py`. Bảng kỳ vọng viết lại độc lập trong `backend/tests/unit/test_rbac.py`; sửa một bên mà quên bên kia thì test fail.

## Hai lớp kiểm tra

1. **Quyền hành động.** Mỗi endpoint khai báo `Depends(require(Perm.X))`. Mặc định là từ chối: `test_route_protection.py` làm fail mọi route không nằm trong danh sách công khai mà thiếu kiểm tra đăng nhập hoặc thiếu `require(...)`.
2. **Phạm vi dữ liệu.** Service áp phạm vi ngay trong câu truy vấn, không lấy hết rồi mới lọc:
   - `all`: toàn workspace.
   - `team`: các nhóm người này dẫn dắt hoặc đang thuộc về, cộng bản thân.
   - `own`: chỉ dữ liệu của chính mình (khách có `owner_member_id` là mình). Với bảng xếp hạng, `own` nghĩa là xem điểm của mình cùng tên và hạng của top 10 (quyết định #9).

Bên dưới hai lớp này còn **Row-Level Security** của Postgres: mỗi request chỉ đặt `app.workspace_id`, nên kể cả khi code quên lọc thì cũng không đọc được workspace khác.

## Ma trận

| Quyền | Chủ sở hữu | Quản lý | Trưởng nhóm | Nhân viên | Chỉ xem |
|---|:-:|:-:|:-:|:-:|:-:|
| `bm.connect` (dán mã truy cập) | all | – | – | – | – |
| `score_formula.edit`, `billing.manage`, `settings.manage` | all | – | – | – | – |
| `bm.view`, `page.assign`, `team.manage`, `member.manage`, `lead.reassign` | all | all | – | – | – |
| `team.view`, `member.view` | all | all | team | – | all |
| `lead.view` | all | all | team | own | all |
| `lead.update` | all | all | own | own | – |
| `lead.phone.view` | all | all | team | own | – |
| `reminder.send` | all | all | team | – | – |
| `ads.cost.view` | all | all | – | – | all |
| `leaderboard.view` | all | all | team | own | all |
| `report.view` | all | all | team | – | all |

Vì sao `lead.update` của Trưởng nhóm là `own`: Trưởng nhóm có thể phụ trách Trang (quyết định #14) nên tự cập nhật khách của mình, nhưng không sửa kết quả thay nhân viên trong nhóm.

## Quy tắc về vai trò

- Chủ sở hữu được cấp mọi vai trò. Quản lý chỉ được cấp Trưởng nhóm, Nhân viên, Chỉ xem, và không sửa được người đang là Chủ sở hữu hay Quản lý.
- Không ai tự đổi vai trò hay trạng thái của chính mình.
- Không được hạ quyền hoặc khóa chủ sở hữu cuối cùng còn hoạt động.
- Khóa tài khoản thì mọi phiên của người đó bị thu hồi ngay.
- Tài khoản mới tạo bị bắt đổi mật khẩu: trước khi đổi, mọi API (trừ `/api/me`, đổi mật khẩu, đăng xuất) trả `403 password_change_required`.

## Che số điện thoại

Người thiếu `lead.phone.view` (hoặc ngoài phạm vi của quyền đó) chỉ nhận số đã che (`09•• ••• 218`, hàm `app.services.phone.mask_phone`). Việc che làm ở serializer phía backend từ Bước 3; frontend không tự che.
