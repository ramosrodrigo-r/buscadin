"""Fail-closed runtime evidence of Chromium's inner sandbox on Linux."""
import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright


def process_status(path):
    return dict(line.split(':', 1) for line in path.read_text().splitlines() if ':' in line)


async def verify_browser_sandbox():
    if os.geteuid() == 0:
        raise RuntimeError('Crawler must run as a non-root user')
    outer_filters = int(process_status(Path('/proc/self/status'))['Seccomp_filters'].strip())
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(chromium_sandbox=True)
        try:
            page = await browser.new_page()
            await page.set_content('<title>Sandbox probe</title>')
            await page.evaluate('document.title')
            for _ in range(10):
                for path in Path('/proc').glob('[0-9]*/status'):
                    try:
                        status = process_status(path)
                        if ('chrome' in status.get('Name', '').lower()
                                and len(status.get('NSpid', '').split()) >= 2
                                and status.get('Seccomp', '').strip() == '2'
                                and int(status.get('Seccomp_filters', '0')) > outer_filters
                                and status.get('NoNewPrivs', '').strip() == '1'
                                and int(status.get('CapEff', '1'), 16) == 0):
                            return {'chromium_sandbox': True, 'pid_namespaces': True,
                                    'renderer_seccomp': True, 'renderer_capabilities': 0}
                    except (OSError, ValueError):
                        continue
                await asyncio.sleep(0.1)
            raise RuntimeError('Chromium renderer sandbox could not be verified')
        finally:
            await browser.close()
