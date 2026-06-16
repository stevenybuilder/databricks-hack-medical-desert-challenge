// Headless screenshots of the 3 CareGap tabs for visual QA.
import pw from '/Users/stevenyang/.npm/_npx/e41f203b7505f1fb/node_modules/playwright/index.js';
const { chromium } = pw;

const OUT = 'output/screenshots';
const URL = 'http://127.0.0.1:8501/';
const TABS = ['Map', 'Top care gaps', 'Copilot'];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1024 } });
await page.goto(URL, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForTimeout(4000); // let first render + data load settle

for (const tab of TABS) {
  try {
    // Streamlit segmented_control renders option labels as clickable buttons.
    const el = page.getByText(tab, { exact: true }).first();
    await el.click({ timeout: 8000 });
  } catch (e) {
    console.log(`click "${tab}" failed: ${e.message.split('\n')[0]}`);
  }
  await page.waitForTimeout(3500); // tab render (map/pydeck needs a beat)
  const safe = tab.toLowerCase().replace(/[^a-z0-9]+/g, '_');
  await page.screenshot({ path: `${OUT}/redesign_${safe}.png`, fullPage: true });
  console.log(`shot ${OUT}/redesign_${safe}.png`);
}
await browser.close();
