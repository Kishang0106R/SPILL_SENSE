// Drive the real page in a persistent session, like a user would.
export default async function run(page, ui) {
  const out = {};

  // Let the splash finish and the dashboard shell settle.
  await page.waitForTimeout(9000);

  out.globals = await page.evaluate(() => ({
    hasL: !!window.L,
    hasData: !!window.SPILLGUARD_DATA,
    hasAlerts: !!window.SpillGuardAlerts,
    splashVisible: !!document.querySelector('#screen-splash.active-screen')
  }));

  const snap = await ui.snapshot();
  const dashRef = snap.match(/@(e\d+) button "4\. Dashboard"/)?.[1];
  if (!dashRef) return { error: 'dashboard nav not found', out, snap: snap.slice(0, 800) };

  await ui.click(dashRef);
  await page.waitForTimeout(5000);

  out.afterDash = await page.evaluate(() => ({
    hasL: !!window.L,
    hasAlerts: !!window.SpillGuardAlerts,
    mapHost: !!window.SpillGuardAlertsHost,
    bell: !!document.getElementById('alert-bell-btn')
  }));

  return out;
}
