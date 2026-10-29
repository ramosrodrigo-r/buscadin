"""Explicit live diagnostic; no database writes or publication.

uv run python scripts/check_company_sources.py --source all --limit 1
"""
import argparse
import asyncio
from dataclasses import asdict
import json

from buscadin_bot.sources.company_crawler import CompanyCrawler, SOURCES
from buscadin_bot.services.classifier import classify_eligibility


async def run(args):
    for name in SOURCES if args.source == "all" else [args.source]:
        crawler = CompanyCrawler(name, max_new=args.limit, max_pages=args.pages)
        try:
            async with asyncio.timeout(600):
                jobs = await crawler.fetch_jobs()
            print(json.dumps({**asdict(crawler.report), "jobs": [
                {"id": j.source_job_id, "title": j.title, "url": j.source_url,
                 "eligibility": classify_eligibility(j)[0], "description_length": len(j.description)}
                for j in jobs]}, ensure_ascii=False), flush=True)
        except Exception as error:
            print(json.dumps({**asdict(crawler.report), "error": type(error).__name__, "message": str(error)[:250]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["all", *SOURCES], default="all")
    parser.add_argument("--limit", type=int, choices=range(1, 31), default=1)
    parser.add_argument("--pages", type=int, choices=range(1, 6), default=1)
    asyncio.run(run(parser.parse_args()))
