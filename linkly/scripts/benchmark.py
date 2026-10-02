"""Measure how Linkly's hot paths scale as data grows.

    python -m scripts.benchmark                     # run and print
    python -m scripts.benchmark --save before.json  # keep a baseline
    python -m scripts.benchmark --compare before.json

Each scenario runs at a SMALL and a LARGE data size. Healthy code should grow
roughly in line with the work it actually has to do, not with total table size.
"""

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.rate_limit import SlidingWindowRateLimiter
from scripts.seed import seed

SCALES = {
    "small": {"links": 500, "clicks": 25_000},
    "large": {"links": 2_000, "clicks": 200_000},
}
QUICK_SCALES = {
    "small": {"links": 200, "clicks": 10_000},
    "large": {"links": 800, "clicks": 80_000},
}


def timed(fn, repeat: int) -> float:
    """Median wall time of `fn` in milliseconds."""
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return statistics.median(samples)


def bench_api(scale: dict, repeat: int) -> dict[str, float]:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "bench.db")
        codes = seed(db_path, scale["links"], scale["clicks"])
        settings = Settings(db_path=db_path, rate_limit_requests=10**9)

        with TestClient(create_app(settings), follow_redirects=False) as client:
            def check(resp, expected):
                assert resp.status_code == expected, resp.text

            client.get("/api/links")  # warm-up

            results = {
                "GET /api/links?limit=200": timed(
                    lambda: check(client.get("/api/links", params={"limit": 200}), 200), repeat
                ),
                "GET /api/links/{code}/stats": timed(
                    lambda: check(client.get(f"/api/links/{codes[0]}/stats"), 200), repeat
                ),
                "GET /{code} (redirect, cached)": timed(
                    lambda: check(client.get(f"/{codes[1]}"), 307), repeat * 5
                ),
            }
            victims = iter(codes[-repeat:])
            results["DELETE /api/links/{code}"] = timed(
                lambda: check(client.delete(f"/api/links/{next(victims)}"), 204), repeat
            )
        return results


def bench_rate_limiter(hours: float) -> float:
    """Microseconds per allow() call for one well-behaved client after `hours` of traffic.

    The client sends 1 request/second, well under the 120/minute limit.
    """
    clock_now = [0.0]
    limiter = SlidingWindowRateLimiter(120, 60, clock=lambda: clock_now[0])
    for _ in range(int(hours * 3600)):
        clock_now[0] += 1.0
        limiter.allow("10.0.0.1")

    calls = 2_000
    start = time.perf_counter()
    for _ in range(calls):
        clock_now[0] += 1.0
        limiter.allow("10.0.0.1")
    return (time.perf_counter() - start) / calls * 1e6


def run(quick: bool) -> dict:
    scales = QUICK_SCALES if quick else SCALES
    repeat = 5 if quick else 10
    results: dict[str, dict[str, float]] = {}

    for name, scale in scales.items():
        print(f"  seeding + benchmarking {name}: {scale['links']:,} links, "
              f"{scale['clicks']:,} clicks ...", flush=True)
        for scenario, ms in bench_api(scale, repeat).items():
            results.setdefault(scenario, {})[name] = ms

    print("  benchmarking rate limiter ...", flush=True)
    small_h, large_h = (0.5, 2) if quick else (1, 8)
    results["rate_limiter.allow() [us]"] = {
        "small": bench_rate_limiter(small_h),
        "large": bench_rate_limiter(large_h),
    }
    return results


def print_table(results: dict, baseline: dict | None = None) -> None:
    header = f"{'scenario':<34} {'small':>10} {'large':>10} {'growth':>8}"
    if baseline:
        header += f" {'vs baseline (large)':>21}"
    print("\n" + header)
    print("-" * len(header))
    for scenario, r in results.items():
        growth = r["large"] / r["small"] if r["small"] else float("inf")
        line = f"{scenario:<34} {r['small']:>10.2f} {r['large']:>10.2f} {growth:>7.1f}x"
        if baseline and scenario in baseline:
            speedup = baseline[scenario]["large"] / r["large"] if r["large"] else float("inf")
            line += f" {speedup:>19.1f}x faster"
        print(line)
    print("\nTimes are median milliseconds unless the scenario says otherwise.")
    print("LARGE has 4x the links and 8x the clicks of SMALL "
          "(rate limiter: 8x the traffic history).")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="smaller data, faster run")
    parser.add_argument("--save", metavar="FILE", help="write results as JSON")
    parser.add_argument("--compare", metavar="FILE", help="compare against saved JSON")
    args = parser.parse_args()

    baseline = json.loads(Path(args.compare).read_text()) if args.compare else None
    print("Running Linkly benchmark")
    results = run(args.quick)
    print_table(results, baseline)

    if args.save:
        Path(args.save).write_text(json.dumps(results, indent=2))
        print(f"\nSaved results to {args.save}")


if __name__ == "__main__":
    main()
