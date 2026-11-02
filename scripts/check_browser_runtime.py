"""Offline build preflight: Chromium must launch as the application user."""
import asyncio

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            await page.set_content("<title>Buscadin browser runtime</title>")
            assert await page.title() == "Buscadin browser runtime"
            print("Chromium runtime ready")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
