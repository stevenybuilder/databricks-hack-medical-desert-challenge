// Capture the specific problem areas for the UX/Product director audit.
import pw from '/Users/stevenyang/.npm/_npx/e41f203b7505f1fb/node_modules/playwright/index.js';
const { chromium } = pw;
const OUT = 'output/screenshots';
const URL = 'http://127.0.0.1:8501/';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
await page.waitForTimeout(5000);

// 1. Map tab full page (header text overload + facility/district detail w/ JSON at bottom)
await page.screenshot({ path: `${OUT}/audit_map_full.png`, fullPage: true });
console.log('audit_map_full');

// 2. Click "Jump to worst district" pill and capture result (user says it doesn't work)
try {
  await page.getByText('Jump to worst district', { exact: false }).first().click({ timeout: 6000 });
  await page.waitForTimeout(3500);
  await page.screenshot({ path: `${OUT}/audit_map_after_jump.png`, fullPage: true });
  console.log('audit_map_after_jump');
} catch (e) { console.log('jump click failed:', e.message.split('\n')[0]); }

// 3. Copilot -> "Where are the worst gaps — and are they real?" (the 0-confidence table)
try {
  await page.getByText('Copilot', { exact: true }).first().click({ timeout: 6000 });
  await page.waitForTimeout(2500);
  await page.getByText('Where are the worst gaps', { exact: false }).first().click({ timeout: 6000 });
  await page.waitForTimeout(4000);
  await page.screenshot({ path: `${OUT}/audit_copilot_deserts.png`, fullPage: true });
  console.log('audit_copilot_deserts');
} catch (e) { console.log('deserts chip failed:', e.message.split('\n')[0]); }

await browser.close();
