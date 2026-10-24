#!/usr/bin/env python3
"""Small bounded smoke/load check for a staging portal, never production by default."""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx


async def run(url: str, *, requests: int, concurrency: int) -> tuple[int, list[float]]:
    semaphore = asyncio.Semaphore(concurrency)
    statuses: list[int] = []
    latencies: list[float] = []

    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        async def one() -> None:
            async with semaphore:
                started = time.perf_counter()
                response = await client.get(url)
                latencies.append(time.perf_counter() - started)
                statuses.append(response.status_code)

        await asyncio.gather(*(one() for _ in range(requests)))
    return statuses.count(200), latencies


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke/load check limitado do portal")
    parser.add_argument("url", help="URL de staging, por exemplo https://staging.example/healthz")
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.requests <= 1000 or not 1 <= args.concurrency <= 50:
        parser.error("requests deve ser 1..1000 e concurrency 1..50")
    successful, latencies = asyncio.run(run(args.url, requests=args.requests, concurrency=args.concurrency))
    print(f"requests={len(latencies)} successful={successful} failed={len(latencies) - successful}")
    print(f"p50_ms={statistics.median(latencies) * 1000:.1f} max_ms={max(latencies) * 1000:.1f}")
    if successful != len(latencies):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
