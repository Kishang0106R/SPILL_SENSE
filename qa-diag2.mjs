// Capture every console message and page error from the very first byte,
// then report what the page's own scripts actually did.
export default async function run(page, ui) {
  const logs = [];
  const failed = [];

  page.on('console', (m) => logs.push(m.type() + ': ' + m.text()));
  page.on('pageerror', (e) => logs.push('PAGEERROR: ' + e.message));
  page.on('requestfailed', (r) => failed.push(r.url() + ' :: ' + (r.failure() || {}).errorText));

  await page.goto('http://127.0.0.1:5500/index.html', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(12000);

  const probe = await page.evaluate(() => {
    const s = Array.from(document.scripts);
    return {
      readyState: document.readyState,
      scriptCount: s.length,
      srcs: s.map((x) => x.getAttribute('src')),
      splashProgress: document.querySelector('.splash-progress-pct')?.textContent
        || document.querySelector('[id*="splash"]')?.textContent?.slice(0, 80)
        || null,
      hasL: !!window.L,
      hasData: !!window.SPILLGUARD_DATA,
      hasAlerts: !!window.SpillGuardAlerts,
      // Does the DOM even contain the dashboard shell?
      hasAppShell: !!document.querySelector('.app-topbar'),
      hasBell: !!document.getElementById('alert-bell-btn'),
      bodyLen: document.body.innerHTML.length
    };
  });

  return { probe, logs: logs.slice(0, 40), failed };
}
