/* eslint-disable @typescript-eslint/no-require-imports */
// Captures the README screenshots from a running demo stack (scripts/dev.sh + scripts/seed_demo.py).
// Usage: node frontend/scripts/screenshots.cjs <out-dir> <report-id>
const { chromium, devices } = require('playwright');
const B = 'http://127.0.0.1:3000', out = process.argv[2], rid = process.argv[3];
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  p.on('pageerror', e => console.log('PAGEERROR', String(e).slice(0, 200)));
  const shot = async (path, name, prep) => {
    await p.goto(B + path, { waitUntil: 'networkidle' });
    await p.waitForTimeout(1500);
    if (prep) await prep();
    await p.screenshot({ path: `${out}/${name}.png` });
    console.log('ok', name);
  };
  await shot('/', '01-terminal');
  await shot('/company/1', '02-company-overview');
  await shot('/company/1/financials', '03-financial-statements');
  await shot('/company/1/time-machine', '04-filing-time-machine');
  await shot('/company/1/forensics', '05-forensic-accounting');
  await shot('/company/1/supply-chain', '06-supply-chain', async () => {
    await p.getByText('Formosa Precision Foundry Co., Ltd.').first().click(); await p.waitForTimeout(600); });
  await shot('/company/1/valuation', '07-valuation-lab', async () => {
    await p.getByLabel(/Discount rate \(WACC\)/).fill('0.09');
    await p.getByRole('button', { name: 'Run valuation' }).click();
    await p.getByText('Base value / share').waitFor(); await p.waitForTimeout(800); });
  await shot('/company/1/reverse-dcf', '08-reverse-dcf', async () => {
    await p.getByLabel(/Discount rate \(WACC\)/).fill('0.09');
    await p.getByRole('button', { name: 'Run valuation' }).click();
    await p.getByText('Market EV to explain').waitFor({ timeout: 60000 }); await p.waitForTimeout(1000); });
  await shot('/company/1/research', '09-investigation', async () => { await p.getByText('Findings', { exact: true }).first().evaluate(e => e.scrollIntoView({ block: 'start' })); await p.mouse.wheel(0, -60); await p.waitForTimeout(500); });
  await shot('/company/1/thesis', '10-thesis-challenger', async () => { await p.getByText('Strongest first').first().evaluate(e => e.scrollIntoView({ block: 'start' })); await p.mouse.wheel(0, -60); await p.waitForTimeout(500); });
  await shot('/company/1/chat', '11-research-chat');
  await shot('/company/1/sentiment', '12-sentiment');
  await shot('/compare?ids=1,2,3,4', '13-compare');
  await shot(`/reports/${rid}`, '14-report');
  await shot('/settings', '15-data-sources');
  await shot('/company/1/supply-chain', '16-evidence-drawer', async () => {
    await p.getByRole('button', { name: /Open evidence E\d+/ }).first().click(); await p.waitForTimeout(1200); });
  const m = await b.newPage({ ...devices['Pixel 7'] });
  await m.goto(B + '/company/1', { waitUntil: 'networkidle' }); await m.waitForTimeout(1500);
  await m.screenshot({ path: `${out}/17-mobile.png` });
  await b.close();
})();
