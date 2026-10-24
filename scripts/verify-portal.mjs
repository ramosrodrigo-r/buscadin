// Requires Playwright installed by the caller; no network or installation here.
// node scripts/verify-portal.mjs [absolute path to playwright/index.mjs]
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const { chromium } = await import(process.argv[2] ? pathToFileURL(path.resolve(process.argv[2])).href : 'playwright');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../.preview/portal');
const mapping = { '/': 'index.html', '/vagas': 'catalogue.html', '/vagas/anotacao-de-videos-1': 'detail.html', '/vagas/avaliador-de-respostas-2': 'unknown.html', '/sobre': 'about.html', '/contato': 'contact.html' };
const results = [];

async function intercept(page) {
  await page.route('**/*', async route => {
    const requestPath = new URL(route.request().url()).pathname;
    const file = mapping[requestPath] || (requestPath.startsWith('/static/') ? requestPath.slice(1) : null);
    if (!file) return route.fulfill({ status: 404, body: 'Local fixture not found' });
    const contentType = file.endsWith('.css') ? 'text/css' : file.endsWith('.js') ? 'text/javascript' : file.endsWith('.svg') ? 'image/svg+xml' : file.endsWith('.woff2') ? 'font/woff2' : file.endsWith('.jpg') ? 'image/jpeg' : 'text/html';
    await route.fulfill({ contentType, body: await fs.readFile(path.join(root, file)) });
  });
}

const browser = await chromium.launch({ headless: true });
try {
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }, { width: 320, height: 700 }]) {
    const page = await browser.newPage({ viewport });
    await intercept(page);
    for (const [name, url] of [['home', '/'], ['catalogue', '/vagas'], ['detail', '/vagas/anotacao-de-videos-1'], ['unknown', '/vagas/avaliador-de-respostas-2']]) {
      await page.goto('https://preview.local' + url);
      await page.evaluate(() => document.fonts.ready);
      const result = await page.evaluate(() => ({ overflow: document.documentElement.scrollWidth > innerWidth, heading: document.querySelector('h1')?.textContent, fontLoaded: document.fonts.check('16px Inter') }));
      assert.equal(result.overflow, false, `${name} overflow at ${viewport.width}`);
      assert.equal(result.fontLoaded, true);
      const contrasts = await page.evaluate(() => {
        const canvas = document.createElement('canvas');
        canvas.width = canvas.height = 1;
        const ctx = canvas.getContext('2d');
        const luminance = color => {
          ctx.clearRect(0, 0, 1, 1);
          ctx.fillStyle = color;
          ctx.fillRect(0, 0, 1, 1);
          const [r, g, b] = [...ctx.getImageData(0, 0, 1, 1).data].slice(0, 3).map(value => {
            const c = value / 255;
            return c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4;
          });
          return .2126 * r + .7152 * g + .0722 * b;
        };
        const body = getComputedStyle(document.body);
        const samples = ['body', '.company', '.job-meta', '.eligibility', '.notice', '.button', '.source'].flatMap(selector => {
          const element = document.querySelector(selector);
          if (!element) return [];
          const style = getComputedStyle(element);
          const bg = style.backgroundColor === 'rgba(0, 0, 0, 0)' ? body.backgroundColor : style.backgroundColor;
          const values = [luminance(style.color), luminance(bg)].sort((a, b) => b - a);
          return [{ selector, ratio: (values[0] + .05) / (values[1] + .05) }];
        });
        return samples;
      });
      for (const sample of contrasts) assert.ok(sample.ratio >= 4.5, `${sample.selector} contrast ${sample.ratio}`);
      if (name === 'catalogue' && viewport.width <= 680) {
        assert.equal(await page.locator('.filters').evaluate(element => element.open), false);
        await page.locator('.filters summary').click();
        assert.equal(await page.locator('.filters').evaluate(element => element.open), true);
        await page.locator('.filters summary').click();
      }
      if (name === 'unknown') {
        const notice = await page.locator('.notice').boundingBox();
        const action = await page.locator('.apply .button').boundingBox();
        assert.ok(notice.y < action.y, 'Eligibility warning must precede the CTA');
      }
      await page.screenshot({ path: path.join(root, `${name}-${viewport.width}.png`), fullPage: true });
      if (name === 'home') {
        await page.keyboard.press('Tab');
        assert.equal(await page.evaluate(() => document.activeElement.className), 'skip');
        assert.equal(await page.locator('.skip').evaluate(element => getComputedStyle(element).outlineStyle), 'solid');
      }
      results.push({ page: name, width: viewport.width, ...result, contrasts });
    }
    await page.close();
  }
  const withoutJs = await browser.newPage({ viewport: { width: 390, height: 844 }, javaScriptEnabled: false });
  await intercept(withoutJs);
  await withoutJs.goto('https://preview.local/vagas');
  assert.equal(await withoutJs.locator('.job').count(), 3);
  assert.equal(await withoutJs.locator('form[method="get"]').count(), 2);
  await withoutJs.close();
  await fs.writeFile(path.join(root, 'browser-results.json'), JSON.stringify({ results, withoutJavaScript: 'content and forms present', network: 'all requests fulfilled from local fixtures' }, null, 2));
  console.log(JSON.stringify({ checks: results.length, overflow: false, withoutJavaScript: true, report: path.join(root, 'browser-results.json') }));
} finally {
  await browser.close();
}
