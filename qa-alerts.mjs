// QA: exercise the Quick Spill Alert feature end-to-end in the real page.
export default async function run(page, ui) {
  const out = {};

  // Get into the dashboard, where the topbar bell lives.
  const nav = await ui.snapshot();
  const dashRef = nav.match(/@(e\d+) button "4\. Dashboard"/)?.[1];
  if (!dashRef) return { error: 'Dashboard nav button not found', nav };
  await ui.click(dashRef);
  // Wait for the Leaflet map itself, not a fixed delay — the alerts layer is
  // only created once the map exists.
  await page.waitForFunction(() => !!(window.SpillGuardAlertsHost && window.SpillGuardAlertsHost.map), null, { timeout: 30000 });
  await page.waitForTimeout(2000);

  out.beforeClick = await page.evaluate(() => ({
    bellPresent: !!document.getElementById('alert-bell-btn'),
    panelPresent: !!document.getElementById('alert-panel'),
    unreadHidden: document.getElementById('alert-bell-count')?.hidden,
    panelOpen: document.getElementById('alert-panel')?.classList.contains('is-open'),
    disclaimer: document.getElementById('alert-disclaimer')?.textContent,
    alertsModuleLoaded: !!window.SpillGuardAlerts,
    mapReady: !!(window.SpillGuardAlertsHost && window.SpillGuardAlertsHost.map),
    layers: Object.keys((window.SpillGuardAlertsHost && { l: 1 }) || {})
  }));

  // Open the panel first — it slides in from off-screen, so its controls are not
  // clickable until the transition finishes.
  const bell = await ui.snapshot();
  const bellRef = bell.match(/@(e\d+) button "Quick Spill Alerts"/)?.[1];
  if (!bellRef) return { error: 'bell button not found', out, bell };
  await ui.click(bellRef);
  await page.waitForTimeout(1200);

  out.afterOpen = await page.evaluate(() => ({
    panelOpen: document.getElementById('alert-panel')?.classList.contains('is-open'),
    ariaHidden: document.getElementById('alert-panel')?.getAttribute('aria-hidden')
  }));

  // Load the demo alerts (this calls POST /api/alerts/evaluate for each reading).
  const panel = await ui.snapshot();
  const demoRef = panel.match(/@(e\d+) button "Load Demo Alerts"/)?.[1];
  if (!demoRef) return { error: 'Load Demo Alerts button not found', out, panel };
  await ui.click(demoRef);
  await page.waitForTimeout(7000);

  out.afterDemo = await page.evaluate(() => {
    const cards = Array.from(document.querySelectorAll('.alert-card'));
    const alerts = (window.SpillGuardAlerts && window.SpillGuardAlerts.getAlerts()) || [];
    return {
      unreadCount: document.getElementById('alert-bell-count')?.textContent,
      unreadHidden: document.getElementById('alert-bell-count')?.hidden,
      panelOpen: document.getElementById('alert-panel')?.classList.contains('is-open'),
      panelCount: document.getElementById('alert-panel-count')?.textContent,
      cardCount: cards.length,
      severities: cards.map(c => c.getAttribute('data-severity')),
      toasts: document.querySelectorAll('.alert-toast').length,
      mapMarkers: document.querySelectorAll('.alert-map-marker').length,
      demoButtonLabel: document.getElementById('btn-alert-demo')?.textContent,
      alertsModuleLoaded: !!window.SpillGuardAlerts,
      mapHostReady: !!(window.SpillGuardAlertsHost && window.SpillGuardAlertsHost.map),
      markersOnLayer: (function () {
        const host = window.SpillGuardAlertsHost;
        if (!host || !host.layer) return 'no layer';
        let n = 0;
        host.layer.eachLayer(() => { n += 1; });
        return n;
      })(),
      sample: alerts.length ? {
        severity: alerts[0].result.severity,
        detected: alerts[0].result.detected_at_utc,
        lat: alerts[0].result.spill.lat,
        lon: alerts[0].result.spill.lon,
        area: alerts[0].result.area_km2,
        conf: alerts[0].result.oil_confidence,
        nearest: alerts[0].result.nearest_sensitive_area
          ? alerts[0].result.nearest_sensitive_area.name + ' @ ' + alerts[0].result.distance_to_sensitive_area_km + ' km'
          : null,
        action: alerts[0].result.recommended_next_action.slice(0, 60),
        disclaimer: alerts[0].result.disclaimer
      } : null
    };
  });

  // Acknowledge the first alert and confirm the state flips.
  const firstAck = await page.$('[data-act="ack"]');
  if (firstAck) {
    await firstAck.click();
    await page.waitForTimeout(800);
    out.afterAck = await page.evaluate(() => ({
      ackStates: document.querySelectorAll('.alert-ack-state').length,
      acknowledgedCards: document.querySelectorAll('.alert-card.is-acknowledged').length,
      unreadCount: document.getElementById('alert-bell-count')?.textContent
    }));
  } else {
    out.afterAck = { error: 'no acknowledge button found' };
  }

  // "Show on map" should move the Leaflet view toward the spill.
  const before = await page.evaluate(() => {
    const host = window.SpillGuardAlertsHost;
    if (!host || !host.map) return null;
    const c = host.map.getCenter();
    return { lat: c.lat, lon: c.lng, zoom: host.map.getZoom() };
  });

  if (!before) {
    out.mapMove = { error: 'map host not available', mapHost: await page.evaluate(() => !!window.SpillGuardAlertsHost) };
    return out;
  }

  const mapBtn = await page.$('[data-act="map"]');
  if (mapBtn) {
    await mapBtn.click();
    await page.waitForTimeout(2600);
  }
  out.mapMove = await page.evaluate((prev) => {
    const host = window.SpillGuardAlertsHost;
    const c = host.map.getCenter();
    const now = { lat: c.lat, lon: c.lng, zoom: host.map.getZoom() };
    return {
      from: prev,
      to: now,
      moved: Math.abs(now.lat - prev.lat) > 0.001 || Math.abs(now.lon - prev.lon) > 0.001
    };
  }, before);

  return out;
}
