// Capture an external design reference for visual study.
import pw from '/Users/stevenyang/.npm/_npx/e41f203b7505f1fb/node_modules/playwright/index.js';
const { chromium } = pw;
const OUT = 'output/screenshots';
const URL = 'https://vfmatch.org/explore';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1024 } });
await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
await page.waitForTimeout(5000); // let client-rendered content settle

// Above-the-fold (first impression) and full page.
await page.screenshot({ path: `${OUT}/ref_vfmatch_fold.png` });
console.log(`shot ${OUT}/ref_vfmatch_fold.png`);
await page.screenshot({ path: `${OUT}/ref_vfmatch_full.png`, fullPage: true });
console.log(`shot ${OUT}/ref_vfmatch_full.png`);

console.log('title:', await page.title());
await browser.close();
