// Verify the round-2 enhancements rendered correctly.
import pw from '/Users/stevenyang/.npm/_npx/e41f203b7505f1fb/node_modules/playwright/index.js';
const { chromium } = pw;
const OUT = 'output/screenshots';
const URL = 'http://127.0.0.1:8501/';
const wait = (p, ms) => p.waitForTimeout(ms);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
await wait(page, 5000);

// 1. Map: collapsed header + left district rail + map
await page.screenshot({ path: `${OUT}/v2_map.png`, fullPage: true });
console.log('v2_map');

// 2. Click "Jump to worst district" -> map should visibly recenter now
try {
  await page.getByText('Jump to worst district', { exact: false }).first().click({ timeout: 6000 });
  await wait(page, 3500);
  await page.screenshot({ path: `${OUT}/v2_map_after_jump.png`, fullPage: true });
  console.log('v2_map_after_jump');
} catch (e) { console.log('jump failed:', e.message.split('\n')[0]); }

// 3. Copilot -> worst-gaps chip -> two-signal table (no more 0.00)
try {
  await page.getByText('Copilot', { exact: true }).first().click({ timeout: 6000 });
  await wait(page, 2500);
  await page.getByText('Where are the worst gaps', { exact: false }).first().click({ timeout: 6000 });
  await wait(page, 4000);
  await page.screenshot({ path: `${OUT}/v2_copilot_deserts.png`, fullPage: true });
  console.log('v2_copilot_deserts');
} catch (e) { console.log('deserts failed:', e.message.split('\n')[0]); }

// 4. Top care gaps tab + My Plan sub-view
try {
  await page.getByText('Top care gaps', { exact: true }).first().click({ timeout: 6000 });
  await wait(page, 3000);
  await page.screenshot({ path: `${OUT}/v2_gaps.png`, fullPage: true });
  console.log('v2_gaps');
  await page.getByText('My Plan', { exact: false }).first().click({ timeout: 6000 });
  await wait(page, 2500);
  await page.screenshot({ path: `${OUT}/v2_gaps_myplan.png`, fullPage: true });
  console.log('v2_gaps_myplan');
} catch (e) { console.log('gaps failed:', e.message.split('\n')[0]); }

await browser.close();
