# Thiết kế giao diện — 14 màn hình

Đây là bản tham chiếu giao diện cho Claude Code. Các file **không chạy độc lập**: chúng cần trình hiển thị của Claude Design (`support.js`, không có trong thư mục này). Hãy đọc chúng như bản đặc tả, không mở bằng trình duyệt.

## Cách đọc một file `.dc.html`

- **Phần HTML trong `<x-dc>`:** bố cục và style của màn hình. Style viết inline, dùng làm chuẩn cho khoảng cách, cỡ chữ, màu sắc.
- **`{{ten}}`:** chỗ điền dữ liệu. Giá trị lấy từ `renderVals()` trong thẻ `<script type="text/x-dc">` ở cuối file.
- **`<sc-for list="{{x}}" as="y">`:** lặp danh sách, tương đương `x.map(y => …)` trong React.
- **`<sc-if value="{{x}}">`:** hiển thị khi `x` đúng.
- **`class Component … renderVals()`:** dữ liệu mẫu, trạng thái (`this.state`) và các thao tác như đổi tab, mở hộp thoại, chọn kết quả. Đây chính là mô tả hành vi tương tác cần làm lại bằng React.
- **`data-props`:** kích thước xem trước và các tùy chọn bật/tắt khi thiết kế. Không cần làm lại.

Mọi tên người, tên khách, số điện thoại và con số đều là **dữ liệu mẫu**. Không đưa vào dữ liệu seed như thật.

## Danh sách màn hình

| # | File | Màn hình | Làm ở bước |
|---|---|---|---|
| 1 | `Main.dc.html` | Tổng quan (sếp) | 7 |
| 2 | `Pages.dc.html` | Danh sách Fanpage | 7 |
| 3 | `PageDetail.dc.html` | Chi tiết Trang | 7 |
| 4 | `Ads.dc.html` | Quảng cáo | 7 |
| 5 | `Inbox.dc.html` | Inbox & bình luận — **giai đoạn sau, chưa làm** | — |
| 6 | `Connect.dc.html` | Kết nối Facebook cho khách hàng SaaS mới — **giai đoạn sau** | — |
| 7 | `Settings.dc.html` | Cài đặt: công thức điểm, quy tắc, nhóm, vai trò, cảnh báo, gói cước | 4 (công thức điểm), phần còn lại dần dần |
| 8 | `Mobile.dc.html` | Điện thoại — sếp | 7 |
| 9 | `Staff.dc.html` | Nhân viên — bảng xếp hạng, nhập Excel | 4 (nhập Excel ở bước 6) |
| 10 | `StaffDetail.dc.html` | Hồ sơ nhân viên | 4 |
| 11 | `Leads.dc.html` | Khách hàng (dạng cột và dạng bảng) | 3 |
| 12 | `LeadDetail.dc.html` | Hồ sơ khách, cập nhật kết quả | 3 |
| 13 | `BMs.dc.html` | Kết nối nhiều BM, Trang chưa có người phụ trách | 6 |
| 14 | `MobileStaff.dc.html` | Ứng dụng điện thoại cho nhân viên (PWA) | 5 |

`canvas.json` ghi vị trí và tiêu đề các màn hình trên canvas thiết kế. Không cần cho việc code.

## Design token

| Token | Giá trị |
|---|---|
| Font | Be Vietnam Pro (400/500/600/700) |
| Màu chính | `#1F63B8` (hover `#174C8E`), nền chọn `#EAF2FC` |
| Màu nhấn | `#EB6834` (badge số lượng) |
| Nền trang | `#F5F6F8` |
| Thẻ | nền `#FFFFFF`, viền `#E4E7EC`, bo góc 12px |
| Chữ | chính `#101828`, phụ `#475467`, mờ `#667085` |
| Hạng A / B / C / D | `#1C5CAB` / `#2A78D6` / `#86B6EF` / `#CDE2FB` |
| Trạng thái tốt | nền `#E7F4EC`, chữ `#1F5F33` |
| Trạng thái xấu | nền `#FCEBEA`, chữ `#9B2A22` |
| Cảnh báo | nền `#FFF4E0`, chữ `#8A5300` |
| Ô bấm tối thiểu | cao 40px (máy tính), 44–48px (điện thoại) |

Menu bên trái giống nhau trên mọi màn hình máy tính: Tổng quan, Nhân viên, Khách hàng, Fanpage, Quảng cáo, Inbox (nhãn "Sau"), rồi một đường phân cách, Kết nối BM, Cài đặt. Nên làm thành một component dùng chung.
