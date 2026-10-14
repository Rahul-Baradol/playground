"""Measure how Stockroom's hot paths scale as data and traffic grow.

    python -m scripts.benchmark                     # run and print
    python -m scripts.benchmark --save before.json  # keep a baseline
    python -m scripts.benchmark --compare before.json

Each scenario runs at a SMALL and a LARGE scale. Healthy code should grow
roughly in line with the work it actually has to do for one request, not with
the size of the whole database or the number of other requests in flight.
"""

import argparse
import asyncio
import json
import statistics
import tempfile
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient`")

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from scripts.seed import seed  # noqa: E402

CARRIER_LATENCY_MS = 50
ARRIVAL_WINDOW_MS = 100

SCALES = {
    "small": {"products": 400, "orders": 2_000, "concurrent_checkouts": 4},
    "large": {"products": 1_600, "orders": 16_000, "concurrent_checkouts": 32},
}
QUICK_SCALES = {
    "small": {"products": 200, "orders": 1_000, "concurrent_checkouts": 4},
    "large": {"products": 800, "orders": 8_000, "concurrent_checkouts": 32},
}


def timed(fn, repeat: int) -> float:
    """Median wall time of `fn` in milliseconds."""
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return statistics.median(samples)


def check(resp, expected: int):
    assert resp.status_code == expected, resp.text
    return resp


def bench_reads(app, skus: list[str], order_ids: list[int], repeat: int) -> dict[str, float]:
    with TestClient(app) as client:
        client.get("/api/catalog/facets")  # warm-up
        return {
            "GET /api/products/{sku}": timed(
                lambda: check(client.get(f"/api/products/{skus[7]}"), 200), repeat * 5
            ),
            "GET /api/orders/{id}": timed(
                lambda: check(client.get(f"/api/orders/{order_ids[-1]}"), 200), repeat * 5
            ),
            "GET /api/catalog/facets": timed(
                lambda: check(client.get("/api/catalog/facets"), 200), repeat * 2
            ),
            "GET /api/reports/reorder": timed(
                lambda: check(client.get("/api/reports/reorder"), 200), repeat
            ),
        }


def bench_checkout_burst(app, skus: list[str], concurrent: int, repeat: int) -> float:
    """Median wall time (ms) for a burst of `concurrent` checkouts.

    The checkouts arrive evenly spread over ARRIVAL_WINDOW_MS, like a flash sale
    where many shoppers press "buy" within the same fraction of a second.
    """
    hot = skus[:64]
    with TestClient(app) as client:
        for sku in hot:
            check(client.post(f"/api/products/{sku}/movements",
                              json={"delta": 100_000, "reason": "receipt"}), 200)

    async def checkout(client: httpx.AsyncClient, i: int) -> httpx.Response:
        await asyncio.sleep(i * ARRIVAL_WINDOW_MS / concurrent / 1000)
        return await client.post("/api/orders", json={
            "customer_email": f"bench{i}@example.com",
            "postcode": "10115",
            "items": [{"sku": hot[i % len(hot)], "quantity": 1}],
        })

    async def burst(client: httpx.AsyncClient) -> None:
        responses = await asyncio.gather(*(checkout(client, i) for i in range(concurrent)))
        for resp in responses:
            check(resp, 201)

    async def run() -> float:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://bench") as client:
            await burst(client)  # warm-up
            samples = []
            for _ in range(repeat):
                start = time.perf_counter()
                await burst(client)
                samples.append((time.perf_counter() - start) * 1000)
            return statistics.median(samples)

    return asyncio.run(run())


def bench_scale(scale: dict, repeat: int) -> dict[str, float]:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "bench.db")
        data = seed(db_path, scale["products"], scale["orders"])
        app = create_app(Settings(db_path=db_path, carrier_latency_ms=CARRIER_LATENCY_MS))

        results = bench_reads(app, data.skus, data.order_ids, repeat)
        results["POST /api/orders burst [batch ms]"] = bench_checkout_burst(
            app, data.skus, scale["concurrent_checkouts"], repeat
        )
        return results


def run(quick: bool) -> dict:
    scales = QUICK_SCALES if quick else SCALES
    repeat = 3 if quick else 5
    results: dict[str, dict[str, float]] = {}

    for name, scale in scales.items():
        print(f"  seeding + benchmarking {name}: {scale['products']:,} products, "
              f"{scale['orders']:,} orders, {scale['concurrent_checkouts']} concurrent "
              f"checkouts ...", flush=True)
        for scenario, ms in bench_scale(scale, repeat).items():
            results.setdefault(scenario, {})[name] = ms
    return results


def print_table(results: dict, baseline: dict | None = None) -> None:
    header = f"{'scenario':<36} {'small':>10} {'large':>10} {'growth':>8}"
    if baseline:
        header += f" {'vs baseline (large)':>21}"
    print("\n" + header)
    print("-" * len(header))
    for scenario, r in results.items():
        growth = r["large"] / r["small"] if r["small"] else float("inf")
        line = f"{scenario:<36} {r['small']:>10.2f} {r['large']:>10.2f} {growth:>7.1f}x"
        if baseline and scenario in baseline:
            speedup = baseline[scenario]["large"] / r["large"] if r["large"] else float("inf")
            line += f" {speedup:>19.1f}x faster"
        print(line)
    print("\nTimes are median milliseconds per request, except the burst row, which is the")
    print(f"wall time for a batch of checkouts arriving within {ARRIVAL_WINDOW_MS} ms to all finish.")
    print("LARGE has 4x the products, 8x the order history and 8x the concurrent checkouts")
    print(f"of SMALL. The mock carrier takes {CARRIER_LATENCY_MS} ms per quote at both scales.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="smaller data, faster run")
    parser.add_argument("--save", metavar="FILE", help="write results as JSON")
    parser.add_argument("--compare", metavar="FILE", help="compare against saved JSON")
    args = parser.parse_args()

    baseline = json.loads(Path(args.compare).read_text()) if args.compare else None
    print("Running Stockroom benchmark")
    results = run(args.quick)
    print_table(results, baseline)

    if args.save:
        Path(args.save).write_text(json.dumps(results, indent=2))
        print(f"\nSaved results to {args.save}")


if __name__ == "__main__":
    main()
