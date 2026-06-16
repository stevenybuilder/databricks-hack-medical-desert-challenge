// Confirm selecting the worst district (NaN centroid -> state fallback) recenters the map.
import pw from '/Users/stevenyang/.npm/_npx/e41f203b7505f1fb/node_modules/playwright/index.js';
const { chromium } = pw;
const OUT = 'output/screenshots';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
await page.goto('http://127.0.0.1:8501/', { waitUntil: 'domcontentloaded', timeout: 60000 });
await page.waitForTimeout(5500);
// Click the first "Select" button in the district rail (worst district = Uttar Dinajpur, NaN centroid)
const buttons = page.getByRole('button', { name: /select/i });
const n = await buttons.count();
console.log('select buttons found:', n);
if (n > 0) {
  await buttons.first().click();
  await page.waitForTimeout(4000);
  await page.screenshot({ path: `${OUT}/v2_jump_worst.png`, fullPage: true });
  console.log('v2_jump_worst captured');
}
await browser.close();
