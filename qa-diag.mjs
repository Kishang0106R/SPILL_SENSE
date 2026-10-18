// Diagnose why window.SpillGuardAlerts is not defined.
export default async function run(page, ui) {
  const errors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push('console: ' + msg.text());
  });
  page.on('pageerror', (err) => errors.push('pageerror: ' + err.message));

  // Re-load the page fresh so we capture load-time errors.
  await page.goto('http://127.0.0.1:5500/index.html', { waitUntil: 'load' });
  await page.waitForTimeout(3000);

  const state = await page.evaluate(() => ({
    hasModule: !!window.SpillGuardAlerts,
    hasAlertsFn: typeof (window.SpillGuardAlerts && window.SpillGuardAlerts.init),
    hasL: !!window.L,
    hasData: !!window.SPILLGUARD_DATA,
    hasSplitData: !!window.SPILLGUARD_DATA_ALT
  }));

  return { errors, state };
}
