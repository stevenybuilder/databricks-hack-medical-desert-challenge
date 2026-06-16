// Verify the two absorbed features render INSIDE the copilot chat.
import pw from '/Users/stevenyang/.npm/_npx/e41f203b7505f1fb/node_modules/playwright/index.js';
const { chromium } = pw;
const OUT = 'output/screenshots';
const URL = 'http://127.0.0.1:8501/';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });
await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
await page.waitForTimeout(4000);
await page.getByText('Copilot', { exact: true }).first().click();
await page.waitForTimeout(3000);

const shots = [
  ['What should I deploy here?', 'copilot_deploy'],
  ['What if I add clinics?', 'copilot_whatif'],
];
for (const [chip, name] of shots) {
  try {
    await page.getByText(chip, { exact: false }).first().click({ timeout: 8000 });
    await page.waitForTimeout(4000); // feature renders
    await page.screenshot({ path: `${OUT}/redesign_${name}.png`, fullPage: true });
    console.log(`shot ${OUT}/redesign_${name}.png`);
  } catch (e) {
    console.log(`chip "${chip}" failed: ${e.message.split('\n')[0]}`);
  }
}
await browser.close();
