import argparse
import concurrent.futures
import json
import statistics
import time
import urllib.error
import urllib.request


def request_once(url):
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
    except Exception:
        status = 0
    return status, (time.perf_counter() - started) * 1000


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def main():
    parser = argparse.ArgumentParser(description="机场运营系统只读 HTTP 负载测试")
    parser.add_argument("--url", default="http://127.0.0.1:5000", help="系统根地址")
    parser.add_argument("--requests", type=int, default=200, help="总请求数")
    parser.add_argument("--workers", type=int, default=20, help="并发工作线程数")
    parser.add_argument("--endpoint", default="/api/flights", help="待测 GET 接口")
    args = parser.parse_args()
    if args.requests < 1 or args.workers < 1:
        parser.error("requests 和 workers 必须为正整数")

    target = args.url.rstrip("/") + args.endpoint
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(request_once, [target] * args.requests))
    elapsed = time.perf_counter() - started
    latencies = [duration for _, duration in results]
    successes = sum(200 <= status < 300 for status, _ in results)
    failures = len(results) - successes
    report = {
        "endpoint": target,
        "requests": args.requests,
        "workers": args.workers,
        "successes": successes,
        "failures": failures,
        "elapsed_seconds": round(elapsed, 3),
        "requests_per_second": round(args.requests / elapsed, 2),
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 2),
            "p50": round(percentile(latencies, 0.50), 2),
            "p95": round(percentile(latencies, 0.95), 2),
            "max": round(max(latencies), 2),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

