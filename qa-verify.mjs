// Verify the Quick Spill Alert logic by evaluating the real source files in-page.
//
// Page-embedded <script> tags don't execute in this headless harness (verified:
// even an inline script on a data: URL is inert), but page.evaluate does. So we
// fetch the actual project files and run them in page context, then drive the
// real DOM the same way a user would.
export default async function run(page, ui) {
  const out = {};
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));

  await page.goto('http://127.0.0.1:5500/index.html', { waitUntil: 'load' });
  await page.waitForTimeout(1500);

  // The backend base URL the app would use.
  out.configLoaded = await page.evaluate(async () => {
    const cfg = await (await fetch('/js/config.js')).text();
    const m = cfg.match(/SPILLGUARD_API_BASE\s*=\s*'([^']+)'/);
    return m ? m[1] : null;
  });

  // Execute the real alerts.js source in page context.
  const installed = await page.evaluate(async () => {
    const src = await (await fetch('/js/alerts.js')).text();
    try {
      // eslint-disable-next-line no-new-func
      new Function(src)();
      return { ok: true, hasModule: !!window.SpillGuardAlerts };
    } catch (e) {
      return { ok: false, error: e.message };
    }
  });
  out.installed = installed;
  if (!installed.ok) return { out, errors };

  // Wire it up exactly as app.js does.
  out.init = await page.evaluate(() => {
    try {
      window.SpillGuardAlerts.init({ apiBase: 'http://127.0.0.1:8000' });
      return { ok: true };
    } catch (e) {
      return { ok: false, error: e.message };
    }
  });

  out.beforeDemo = await page.evaluate(() => ({
    bell: !!document.getElementById('alert-bell-btn'),
    unreadHidden: document.getElementById('alert-bell-count').hidden,
    panelOpen: document.getElementById('alert-panel').classList.contains('is-open'),
    disclaimer: document.getElementById('alert-disclaimer').textContent
  }));

  // Run the demo (hits POST /api/alerts/evaluate for each reading).
  out.demo = await page.evaluate(async () => {
    const r = await window.SpillGuardAlerts.runDemo();
    return r;
  });
  await page.waitForTimeout(1500);

  out.afterDemo = await page.evaluate(() => {
    const cards = Array.from(document.querySelectorAll('.alert-card'));
    const alerts = window.SpillGuardAlerts.getAlerts();
    return {
      unreadCount: document.getElementById('alert-bell-count').textContent,
      unreadHidden: document.getElementById('alert-bell-count').hidden,
      panelOpen: document.getElementById('alert-panel').classList.contains('is-open'),
      panelCount: document.getElementById('alert-panel-count').textContent,
      cardCount: cards.length,
      severities: cards.map((c) => c.getAttribute('data-severity')),
      toasts: document.querySelectorAll('.alert-toast').length,
      firstCardText: cards[0] ? cards[0].innerText.replace(/\s+/g, ' ').slice(0, 240) : null,
      sampleResult: alerts.length ? {
        severity: alerts[0].result.severity,
        detected: alerts[0].result.detected_at_utc,
        lat: alerts[0].result.spill.lat,
        lon: alerts[0].result.spill.lon,
        area: alerts[0].result.area_km2,
        conf: alerts[0].result.oil_confidence,
        nearest: alerts[0].result.nearest_sensitive_area
          ? alerts[0].result.nearest_sensitive_area.name + ' @ ' + alerts[0].result.distance_to_sensitive_area_km + ' km'
          : null,
        action: alerts[0].result.recommended_next_action,
        disclaimer: alerts[0].result.disclaimer
      } : null
    };
  });

  // Acknowledge via the real button. The panel slides in from off-screen, so
  // open it first or the control is not clickable.
  await page.evaluate(() => window.SpillGuardAlerts.setPanel(true));
  await page.waitForTimeout(900);
  const ack = await page.$('[data-act="ack"]');
  if (ack) {
    try {
      await ack.click({ timeout: 8000 });
    } catch (e) {
      out.ackClickError = e.message;
      await page.evaluate(() => { const b = document.querySelector('[data-act="ack"]'); if (b) b.click(); });
    }
    await page.waitForTimeout(600);
  }
  out.afterAck = await page.evaluate(() => ({
    acknowledgedCards: document.querySelectorAll('.alert-card.is-acknowledged').length,
    ackStates: document.querySelectorAll('.alert-ack-state').length,
    unreadCount: document.getElementById('alert-bell-count').textContent
  }));

  out.errors = errors;
  return out;
}