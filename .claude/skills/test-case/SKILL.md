---
name: test-case
description: Chạy toàn bộ ma trận test case thêm/sửa/xóa của dự án (thư mục "Test case/"), cập nhật file Excel test_cases.xlsx, và khi có chức năng thêm/sửa/xóa mới thì tự thêm test case mới cho nó. Dùng khi người dùng gõ /test-case, hoặc nói "chạy test case", "cập nhật file test", "kiểm tra CRUD", hoặc sau khi vừa thêm một chức năng thêm/sửa/xóa mới và muốn cập nhật bộ test.
argument-hint: "[không bắt buộc: 'load' để chạy thêm bài test tải, hoặc URL VPS để test tải"]
---

Thư mục `Test case/` ở gốc dự án chứa toàn bộ bộ test cho các chức năng
thêm/sửa/xóa (CRUD), tách riêng khỏi 10 bộ test hồi quy (`test_*.py`) mà
skill `kiem-tra` đã dùng - hai bộ phục vụ mục đích khác nhau và cả hai đều
cần chạy trước khi báo "đã xong".

Cấu trúc:
- `Test case/matrix.py` — danh sách toàn bộ test case (mã, nhóm chức năng,
  mô tả, kết quả mong đợi). Đây là NGUỒN DUY NHẤT của sự thật — file Excel
  chỉ là báo cáo được sinh ra từ đây.
- `Test case/crud_test_suite.py` — chạy thật từng test case bằng Flask
  test client (không cần bật server), tự dọn sạch dữ liệu test sau khi
  chạy xong (kể cả khi giữa chừng bị lỗi).
- `Test case/test_cases.xlsx` — báo cáo được ghi đè mỗi lần chạy, có cột
  Trạng thái (ĐẠT/LỖI/CHƯA CHẠY), chi tiết lỗi, và thời gian chạy gần nhất.
- `Test case/load_test.py` — bắn nhiều request GET (đọc, không sửa dữ liệu)
  vào một địa chỉ để kiểm tra khả năng chịu tải.

## Bước 1 — Nếu vừa có chức năng thêm/sửa/xóa MỚI, thêm test case cho nó trước

Kiểm tra xem lần trò chuyện gần đây (hoặc `git diff`/`git log` gần nhất) có
thêm route thêm/sửa/xóa nào mới không (ví dụ route mới trong
`blueprints/admin.py` hay `blueprints/public.py` có `methods=['POST']` và
làm thay đổi dữ liệu). Nếu có:

1. Thêm một `TestCase(...)` mới vào `MATRIX` trong `Test case/matrix.py`,
   đặt mã theo đúng nhóm đã có (SP=Sản phẩm, PH=Phòng, DH=Đơn hàng,
   GH=Giỏ hàng, CN=Công nợ, TK=Tài khoản, XT=Xác thực, QR=QR/Thanh toán,
   BC=Báo cáo, hoặc một nhóm mới nếu chức năng thuộc mảng hoàn toàn khác).
2. Viết một hàm kiểm tra thật trong `Test case/crud_test_suite.py`, theo
   đúng khuôn của các hàm đã có (`product_flows`, `room_flows`, ...): dùng
   Flask test client thật (`app.test_client()`), gọi đúng route vừa thêm
   với CSRF token qua hàm `post()` có sẵn, kiểm tra kết quả bằng cách đọc
   thẳng database qua `app.app_context()`, rồi gọi `rep.check('MÃ-XX', ok, chi_tiết)`.
3. Nhớ dọn dữ liệu vừa tạo trong hàm `cleanup()` ở cuối file - đừng để rác
   lại trong database thật.
4. Nếu chức năng mới có khả năng đụng foreign key mà chưa có cascade (giống
   lỗi đã gặp ở xóa sản phẩm/phòng/đơn hàng trước đây), nhớ kiểm tra cả
   đường thất bại (xóa khi có dữ liệu liên quan) chứ không chỉ đường thành
   công.

Nếu không có gì mới cần thêm, bỏ qua bước này, chạy thẳng Bước 2.

## Bước 2 — Chạy bộ test CRUD, cập nhật Excel

```bash
cd "Test case"
../venv/bin/python crud_test_suite.py
```

Đọc kỹ đầu ra: mỗi dòng PASS/FAIL kèm mã test case. Nếu có FAIL:
- Đọc traceback/chi tiết lỗi in ra.
- Nếu là lỗi thật trong code sản phẩm (route trả sai, dữ liệu không đúng),
  sửa code rồi chạy lại.
- Nếu là lỗi trong chính kịch bản test (ví dụ giả lập sai form field),
  sửa `crud_test_suite.py`.
- **Không được** tự ý sửa `matrix.py` để bài test "đạt" trừ khi hành vi
  mong đợi thật sự đã thay đổi theo đúng ý người dùng.

File `Test case/test_cases.xlsx` được ghi lại sau mỗi lần chạy, kể cả khi
có lỗi giữa chừng (những test case chưa chạy tới sẽ ghi "CHƯA CHẠY").

## Bước 3 — Chạy 10 bộ test hồi quy còn lại (bắt buộc, không được bỏ qua)

Bộ CRUD ở trên chỉ tập trung vào thêm/sửa/xóa - vẫn cần chạy đủ 10 bộ
`test_*.py` ở gốc dự án để không bỏ sót phần khác (CSRF, bảo mật, SEO, QR,
PWA, nhắc hẹn...). Dùng đúng quy trình đã có trong skill `kiem-tra`:

```bash
cd ..
for t in test_smoke_routes test_csrf test_flows test_security test_seo test_seo_admin test_payments test_qr test_pwa test_reminders; do
  o=$(./venv/bin/python $t.py 2>&1)
  printf "%-18s %s\n" "$t" "$(echo "$o" | grep -E 'passed|OK - all|REGRESSIONS' | tail -1)"
done
```

## Bước 4 — Test tải (chỉ khi được yêu cầu, ví dụ người dùng gõ

`/test-case load` hoặc nói "bắn 1000 request", "test VPS", "kiểm tra tải")

```bash
cd "Test case"
../venv/bin/python load_test.py --url <địa_chỉ> -n 1000 -c 20
```

- Mặc định `--url http://127.0.0.1:8000` (local). Nếu người dùng muốn test
  VPS/production thật, dùng đúng địa chỉ họ đưa (ví dụ
  `https://www.calaci.com.vn`).
- **Bắt buộc hỏi xác nhận trước khi bắn vào địa chỉ production thật** nếu
  người dùng chưa nói rõ đang là giờ vắng khách hay đông khách - việc này
  ảnh hưởng tới khách thật đang dùng trang, không được tự ý chạy.
- Công cụ chỉ gọi các trang đọc (GET `/`, `/customer`, `/products`,
  `/rooms`...), không tạo đơn hàng hay sửa dữ liệu, nên an toàn về mặt dữ
  liệu - rủi ro duy nhất là làm chậm trang cho khách thật nếu chạy lúc
  đông khách.
- Đọc kết quả: tỷ lệ thành công, độ trễ p95/p99, và dòng KẾT LUẬN cuối cùng
  - báo lại nguyên văn cho người dùng, đừng tự diễn giải thêm.

## Kết luận

Chỉ báo "đã kiểm tra xong" khi: bộ CRUD trong `Test case/` toàn ĐẠT (hoặc
đã sửa xong các LỖI phát hiện được), 10 bộ test hồi quy đều xanh, và (nếu
có chạy) bài test tải đã có kết luận rõ ràng. Nếu phải sửa lỗi và lặp lại,
nói rõ đã lặp lại bao nhiêu vòng và lỗi gốc là gì - đừng làm tròn thành
"về cơ bản là ổn".
