"""Bắn nhiều request thật vào một địa chỉ (mặc định 1000) để xem VPS chịu
tải có ổn không - chỉ gọi các trang ĐỌC (GET), không tạo đơn hàng hay sửa
dữ liệu thật, nên an toàn để chạy thẳng vào trang đang chạy thật (production).

Cách dùng:
    ../venv/bin/python load_test.py                          # 1000 request vào localhost:8000
    ../venv/bin/python load_test.py --url https://www.calaci.com.vn
    ../venv/bin/python load_test.py --url https://www.calaci.com.vn -n 1000 -c 20

    -n / --requests     tổng số request (mặc định 1000)
    -c / --concurrency  số luồng bắn song song cùng lúc (mặc định 20 - vừa
                         đủ để mô phỏng nhiều khách vào cùng lúc, không đủ
                         mạnh để làm sập một VPS bình thường)
"""

import argparse
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    print('Cần cài thư viện requests: pip3 install requests')
    sys.exit(1)

# Chỉ những trang khách hàng thực sự xem, không đụng gì tới dữ liệu -
# lặp lại nhiều trang khác nhau để giống lưu lượng thật hơn là spam 1 URL.
DEFAULT_PATHS = [
    '/', '/customer', '/products', '/products?type=food', '/rooms',
]


def hit(session, base_url, path, timeout):
    url = base_url.rstrip('/') + path
    t0 = time.monotonic()
    try:
        r = session.get(url, timeout=timeout)
        return path, r.status_code, time.monotonic() - t0, None
    except requests.RequestException as e:
        return path, None, time.monotonic() - t0, str(e)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--url', default='http://127.0.0.1:8000',
                    help='địa chỉ cần kiểm tra, ví dụ https://www.calaci.com.vn')
    ap.add_argument('-n', '--requests', type=int, default=1000)
    ap.add_argument('-c', '--concurrency', type=int, default=20)
    ap.add_argument('--timeout', type=float, default=15.0)
    args = ap.parse_args()

    paths = [DEFAULT_PATHS[i % len(DEFAULT_PATHS)] for i in range(args.requests)]

    print(f'Bắn {args.requests} request vào {args.url} '
         f'({args.concurrency} luồng song song, timeout {args.timeout}s)...')
    print('Các trang test:', ', '.join(DEFAULT_PATHS))
    print()

    session = requests.Session()
    latencies = []
    status_counts = {}
    errors = []
    t_start = time.monotonic()

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(hit, session, args.url, p, args.timeout) for p in paths]
        done = 0
        for fut in as_completed(futures):
            path, status, elapsed, err = fut.result()
            done += 1
            latencies.append(elapsed)
            if err:
                errors.append((path, err))
            else:
                status_counts[status] = status_counts.get(status, 0) + 1
            if done % 100 == 0 or done == args.requests:
                print(f'  ... {done}/{args.requests}')

    total_time = time.monotonic() - t_start
    latencies.sort()

    def pct(p):
        if not latencies:
            return 0
        idx = min(len(latencies) - 1, int(len(latencies) * p / 100))
        return latencies[idx]

    print()
    print('=== KẾT QUẢ ===')
    print(f'Tổng thời gian: {total_time:.1f}s  '
         f'({args.requests / total_time:.1f} request/giây)')
    print(f'Mã trạng thái HTTP:')
    for code in sorted(status_counts, key=lambda x: (x is None, x)):
        print(f'  {code}: {status_counts[code]}')
    if errors:
        print(f'Lỗi kết nối/timeout: {len(errors)}')
        by_msg = {}
        for _, e in errors:
            by_msg[e] = by_msg.get(e, 0) + 1
        for msg, count in sorted(by_msg.items(), key=lambda x: -x[1])[:5]:
            print(f'  x{count}  {msg}')
    print(f'Thời gian phản hồi: trung bình {statistics.mean(latencies)*1000:.0f}ms  '
         f'trung vị {pct(50)*1000:.0f}ms  '
         f'p95 {pct(95)*1000:.0f}ms  '
         f'p99 {pct(99)*1000:.0f}ms  '
         f'chậm nhất {max(latencies)*1000:.0f}ms')

    ok_2xx = sum(v for k, v in status_counts.items() if k and 200 <= k < 300)
    ok_rate = ok_2xx / args.requests * 100
    print()
    if ok_rate >= 99 and pct(95) < 3 and not errors:
        print(f'KẾT LUẬN: VPS chạy ổn - {ok_rate:.1f}% request thành công, '
             f'95% request trả lời dưới {pct(95)*1000:.0f}ms.')
    elif ok_rate >= 95:
        print(f'KẾT LUẬN: VPS chịu được tải nhưng có dấu hiệu chậm/lỗi rải rác '
             f'({ok_rate:.1f}% thành công) - nên theo dõi thêm, cân nhắc tăng '
             f'số worker trong gunicorn.conf.py nếu lượng khách thật tăng.')
    else:
        print(f'KẾT LUẬN: VPS đang gặp khó khăn khi tải cao - chỉ '
             f'{ok_rate:.1f}% request thành công. Cần kiểm tra RAM/CPU của VPS '
             f'và số worker gunicorn đang chạy.')

    return 0 if ok_rate >= 95 else 1


if __name__ == '__main__':
    sys.exit(main())
