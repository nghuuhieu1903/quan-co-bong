---
name: kiem-tra
description: Chạy toàn bộ 10 bộ kiểm thử của dự án quán cà phê (test_smoke_routes, test_csrf, test_flows, test_security, test_seo, test_seo_admin, test_payments, test_qr, test_pwa, test_reminders), rồi dựng thử server thật và soi vài trang bằng trình duyệt không giao diện để chắc chắn không có lỗi hiển thị. Dùng lệnh này trước khi báo với người dùng là một việc sửa/thêm code đã xong, hoặc bất cứ khi nào người dùng muốn "kiểm tra toàn bộ", "kiểm tra kỹ", hoặc hỏi web có chạy ổn không trước khi đưa lên VPS.
---

Đây là bước kiểm tra bắt buộc trước khi báo "đã xong" cho bất kỳ thay đổi code nào trong dự án này. Không được bỏ qua bước nào, không được tự suy luận "chắc vẫn chạy được" — phải chạy thật và đọc kết quả thật.

## Bước 1 — Chạy toàn bộ 10 bộ kiểm thử

Chạy đúng 10 file này bằng Python trong virtualenv của dự án (không dùng `python` hệ thống):

```
test_smoke_routes.py  test_csrf.py       test_flows.py    test_security.py  test_seo.py
test_seo_admin.py     test_payments.py   test_qr.py       test_pwa.py       test_reminders.py
```

```bash
cd <thư mục dự án>
for t in test_smoke_routes test_csrf test_flows test_security test_seo test_seo_admin test_payments test_qr test_pwa test_reminders; do
  o=$(./venv/bin/python $t.py 2>&1)
  printf "%-18s %s\n" "$t" "$(echo "$o" | grep -E 'passed|OK - all|REGRESSIONS' | tail -1)"
done
```

Bỏ qua `test_add_product_upload.py` và `test_dashboard_render.py` — đây là hai script debug cũ từ trước, dùng cổng 5000 đã lỗi thời và kiểm tra một dòng chữ JS không còn tồn tại. Chạy chúng chỉ báo lỗi giả, không phải lỗi thật. Nếu người dùng hỏi vì sao không chạy, giải thích đúng lý do này thay vì chạy đại rồi báo cáo kết quả sai.

Nếu bất kỳ suite nào có dòng `REGRESSIONS` hoặc không phải `X/X`: chạy lại đúng file đó với đầu ra đầy đủ (`./venv/bin/python test_xxx.py 2>&1`), tìm dòng `FAIL`, đọc kỹ rồi sửa lỗi trong code — **không được sửa bài test để nó "pass" trừ khi hành vi cũ thật sự đã đổi theo đúng ý người dùng**. Sau khi sửa, quay lại chạy đủ cả 10 suite từ đầu, vì một chỗ sửa có thể làm hỏng chỗ khác.

## Bước 2 — Dựng server thật và soi bằng trình duyệt

Chỉ làm bước này sau khi cả 10 suite ở Bước 1 đã xanh hết.

```bash
lsof -ti:8000 | xargs kill -9 2>/dev/null; sleep 1
FLASK_RUN_PORT=8000 ./venv/bin/python app.py > /tmp/srv_kiemtra.log 2>&1 &
sleep 5
cat /tmp/srv_kiemtra.log | grep -i "error\|traceback" && echo "CÓ LỖI KHI KHỞI ĐỘNG" || echo "khởi động sạch"
```

Kiểm tra mã trạng thái HTTP của các trang cốt lõi (thêm/bớt route tùy việc vừa sửa động tới đâu):

```bash
for u in / /customer /products "/products?type=food" /cart /rooms /admin/login; do
  printf "  %-24s %s\n" "$u" "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000$u)"
done
```

Nếu việc vừa sửa đụng tới khu vực quản trị, đăng nhập admin (`admin` / `admin123`) rồi kiểm tra thêm các trang admin liên quan.

Nếu việc vừa sửa đụng tới giao diện (CSS, bố cục, animation, responsive...), chụp ảnh màn hình thật bằng Chrome không giao diện để nhìn bằng mắt chứ không chỉ tin mã trạng thái 200 — dùng đúng cách đã học trong dự án này:

- `--screenshot` một mình sẽ chụp **quá sớm**, trước khi JavaScript kịp chạy xong (thêm giỏ hàng, đóng splash, v.v.) — không dùng riêng lẻ cho các luồng có bước tương tác.
- `--virtual-time-budget` làm **đứng luồng nền và service worker** — không dùng nếu trang có polling, service worker (PWA), hoặc setTimeout dài.
- Cách chắc ăn cho các luồng có thao tác (thêm giỏ, đăng nhập, điền form): mở Chrome với `--remote-debugging-port`, điều khiển qua giao thức DevTools (`Page.navigate` → chờ thật bằng `time.sleep()` → `Runtime.evaluate` để bấm nút/điền form → chờ tiếp → `Page.captureScreenshot`), y hệt cách đã dùng để xác nhận nút "Cài đặt ứng dụng" và bảng giỏ hàng trong dự án này. Viết script Python tạm vào thư mục scratchpad, không lưu vào repo.
- Dọn sạch mọi tiến trình Chrome (`pkill -f "remote-debugging-port"`) và thư mục `--user-data-dir` tạm sau khi xong.

Đọc ảnh chụp bằng công cụ Read (nó hiển thị ảnh trực tiếp) — không chỉ tin "đã chụp xong", phải thực sự nhìn ảnh trước khi kết luận.

## Bước 3 — Dọn dẹp

- Kill server thử vừa mở (`lsof -ti:8000 | xargs kill -9`).
- Xóa mọi đơn hàng / dữ liệu thử đã tạo trong lúc kiểm tra (kể cả tồn kho đã trừ phải cộng lại) — không được để rác trong cơ sở dữ liệu thật của người dùng.
- Xóa file HTML/script tạm đã tạo trong `static/` nếu có dùng để dựng trang thử.

## Kết luận

Chỉ nói "đã kiểm tra xong, an toàn" khi **cả 3 bước trên đều sạch**: 10/10 suite xanh, server khởi động không lỗi, các trang cốt lõi trả 200, và (nếu có sửa giao diện) ảnh chụp cho thấy đúng như mong đợi.

Nếu có bất kỳ chỗ nào không đạt, báo thẳng chỗ nào hỏng, không làm tròn thành "về cơ bản là ổn". Nếu phải sửa lỗi và lặp lại, nói rõ đã lặp lại bao nhiêu vòng.
