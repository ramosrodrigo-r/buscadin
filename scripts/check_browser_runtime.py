"""Offline check inside the deployed, restricted crawler container."""
import asyncio
import json

from buscadin_bot.sources.browser_runtime import verify_browser_sandbox

if __name__ == '__main__':
    print(json.dumps(asyncio.run(verify_browser_sandbox())))
