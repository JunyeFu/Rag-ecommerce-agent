// Deterministic format rendering of project-owned QA illustrations, no model call.
import { chromium } from 'playwright';
import { readFile, mkdir } from 'node:fs/promises';
import path from 'node:path';

const out = path.resolve('output/final-media');
await mkdir(out, { recursive: true });
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 640, height: 480 }, deviceScaleFactor: 1 });
  for (const name of ['phone', 'non-3c']) {
    const svg = await readFile(`evals/v3/media/${name}.svg`, 'utf8');
    await page.setContent(`<style>body{margin:0}</style>${svg}`);
    await page.screenshot({ path: path.join(out, `${name}.png`) });
  }
} finally {
  await browser.close();
}
