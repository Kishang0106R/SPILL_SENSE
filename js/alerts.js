/**
 * Spill Sense — Quick Spill Alert (frontend)
 *
 * Raises an in-app alert when a slick reading breaches any trigger:
 *   - oil confidence  >= 75%
 *   - spill area      >= 2 km²
 *   - within 20 km of a beach / port / coral reef / mangrove / fishing zone /
 *     island / marine protected area
 *
 * Severity is decided by the backend (server/alerts.py) so the rules live in
 * exactly one place. This file is presentation and interaction only:
 * bell + unread count, severity cards, toasts, map markers, acknowledgement.
 *
 * No paid APIs are used — everything is local and in-app.
 */
(function () {
  'use strict';

  // --- Sensitive-area catalogue -------------------------------------------
  // Coordinates are real-ish anchors for each region so the 20 km proximity
  // test produces meaningful distances rather than placeholder noise.
  const SENSITIVE_AREAS = {
    malacca: [
      { name: 'Port Dickson Terminal', type: 'port', lat: 2.5228, lon: 101.7967 },
      { name: 'Cape Rachado Beach', type: 'beach', lat: 2.5033, lon: 101.7467 },
      { name: 'Pulau Sembilan Coral Reef', type: 'coral_reef', lat: 2.4150, lon: 101.8900 },
      { name: 'Linggi Mangrove Reserve', type: 'mangrove', lat: 2.2550, lon: 101.9800 },
      { name: 'Kuala Linggi Fishing Zone', type: 'fishing_zone', lat: 2.3300, lon: 101.9500 },
      { name: 'Pulau Besar Island', type: 'island', lat: 2.3500, lon: 102.0000 },
      { name: 'Tanjung Tuan Marine Protected Area', type: 'marine_protected_area', lat: 2.4900, lon: 101.7400 }
    ],
    persian_gulf: [
      { name: 'Bandar Abbas Port', type: 'port', lat: 27.1832, lon: 56.2666 },
      { name: 'Hormuz Coral Shelf', type: 'coral_reef', lat: 26.5500, lon: 56.2500 },
      { name: 'Qeshm Island', type: 'island', lat: 26.8000, lon: 55.9000 },
      { name: 'Gulf Fishing Grounds', type: 'fishing_zone', lat: 26.3000, lon: 55.7000 }
    ],
    north_sea: [
      { name: 'Dogger Bank Marine Protected Area', type: 'marine_protected_area', lat: 55.0000, lon: 3.3000 },
      { name: 'Rotterdam Approaches', type: 'port', lat: 51.9500, lon: 4.1400 },
      { name: 'North Sea Fishing Zone', type: 'fishing_zone', lat: 54.9000, lon: 3.1000 }
    ],
    gulf_mexico: [
      { name: 'Mississippi River Delta Mangrove', type: 'mangrove', lat: 29.0500, lon: -89.2000 },
      { name: 'Grand Isle Beach', type: 'beach', lat: 29.2360, lon: -90.0050 },
      { name: 'Flower Garden Banks Coral Reef', type: 'coral_reef', lat: 27.9000, lon: -93.6000 },
      { name: 'Port Fourchon', type: 'port', lat: 29.1130, lon: -90.2000 },
      { name: 'Gulf Shrimp Fishing Zone', type: 'fishing_zone', lat: 28.6000, lon: -89.5000 }
    ]
  };

  const SEVERITY_ORDER = { Critical: 0, High: 1, Medium: 2, Low: 3 };
  const SEVERITY_GLYPH = { Critical: '!', High: '!', Medium: '~', Low: 'i' };
  const DISCLAIMER = 'Investigation support only — requires authorised field verification.';

  // Demo readings for the "Load Demo Alerts" button — one per severity tier so
  // the colour coding is visible without waiting for a live detection.
  const DEMO_READINGS = [
    {
      label: 'Malacca TSS Crude Emulsion',
      region: 'malacca',
      spill_lat: 2.3812, spill_lon: 101.9124,
      oil_confidence: 96.8, area_km2: 45.2,
      predicted_impact_hours: 6
    },
    {
      label: 'Cape Rachado Bilge Wash',
      region: 'malacca',
      spill_lat: 2.5100, spill_lon: 101.7600,
      oil_confidence: 88.4, area_km2: 12.8,
      predicted_impact_hours: 18
    },
    {
      label: 'Malacca Approach Oily Discharge',
      region: 'malacca',
      spill_lat: 2.4500, spill_lon: 101.8300,
      oil_confidence: 82.1, area_km2: 5.4,
      predicted_impact_hours: 36
    },
    {
      label: 'Dogger Bank Offshore Slick',
      region: 'north_sea',
      spill_lat: 55.1000, spill_lon: 3.2000,
      oil_confidence: 61.2, area_km2: 6.4,
      is_offshore: true
    }
  ];

  // --- Module state --------------------------------------------------------
  const alertState = {
    alerts: [],
    isOpen: false,
    apiBase: '',
    byId: new Map()
  };

  const emergencyState = {
    selected: null,
    history: JSON.parse(localStorage.getItem('spillsense-emergency-history') || localStorage.getItem('spillguard-emergency-history') || '[]')
  };

  let seq = 0;

  function uid() {
    seq += 1;
    return 'SG-ALERT-' + Date.now().toString(36).toUpperCase() + '-' + seq;
  }

  function apiUrl(path) {
    return (alertState.apiBase || '').replace(/\/$/, '') + path;
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function formatUtc(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso);
    const p = (n) => String(n).padStart(2, '0');
    return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}` +
      ` ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())} UTC`;
  }

  function formatEta(hours) {
    if (hours == null) return 'Not modelled';
    if (hours < 1) return '< 1 h';
    if (hours < 48) return hours.toFixed(hours < 10 ? 1 : 0) + ' h';
    return (hours / 24).toFixed(1) + ' days';
  }

  function localEvaluate(reading) {
    const areas = SENSITIVE_AREAS[reading.region] || [];
    const toRadians = (value) => value * Math.PI / 180;
    const distanceKm = (lat1, lon1, lat2, lon2) => {
      const dLat = toRadians(lat2 - lat1);
      const dLon = toRadians(lon2 - lon1);
      const lat1Rad = toRadians(lat1);
      const lat2Rad = toRadians(lat2);
      const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1Rad) * Math.cos(lat2Rad) * Math.sin(dLon / 2) ** 2;
      return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    };
    const typeLabels = {
      beach: 'Beach', port: 'Port', coral_reef: 'Coral Reef', mangrove: 'Mangrove',
      fishing_zone: 'Fishing Zone', island: 'Island', marine_protected_area: 'Marine Protected Area'
    };
    const receptors = areas.map((area) => ({
      ...area,
      type_label: typeLabels[area.type] || area.type,
      distance_km: Number(distanceKm(reading.spill_lat, reading.spill_lon, area.lat, area.lon).toFixed(2))
    })).sort((a, b) => a.distance_km - b.distance_km);
    const nearest = receptors[0] || null;
    const distance = nearest ? nearest.distance_km : reading.distance_to_coast_km;
    const nearReceptor = distance != null && distance <= 20;
    const confidenceHit = reading.oil_confidence >= 75;
    const areaHit = reading.area_km2 >= 2;
    if (!confidenceHit && !areaHit && !nearReceptor) {
      return { alert: false };
    }

    const hours = reading.predicted_impact_hours == null && nearReceptor && distance
      ? distance / 1.2
      : reading.predicted_impact_hours;
    const confidence = Number(reading.oil_confidence ?? 0);
    const severity = confidence < 75
      ? 'Low'
      : hours != null && hours <= 12 ? 'Critical'
        : hours != null && hours <= 24 ? 'High'
          : hours != null && hours <= 48 ? 'Medium' : 'Low';
    const actions = {
      Critical: 'Immediate escalation: task an urgent verification pass and alert the regional response centre.',
      High: 'Verify on the next SAR pass and notify the regional response centre. Track drift toward the nearest receptor.',
      Medium: 'Monitor and re-evaluate every 12 hours. Request a dedicated SAR revisit.',
      Low: 'Log as an offshore low-confidence detection and continue routine monitoring.'
    };
    return {
      alert: true,
      severity,
      severity_color: { Critical: '#FF4438', High: '#FF8A3D', Medium: '#FFB020', Low: '#2BD97C' }[severity],
      severity_rank: { Critical: 4, High: 3, Medium: 2, Low: 1 }[severity],
      detected_at_utc: reading.detected_at_utc || new Date().toISOString(),
      spill: { lat: reading.spill_lat, lon: reading.spill_lon },
      area_km2: Number(reading.area_km2.toFixed(2)),
      oil_confidence: Number(reading.oil_confidence.toFixed(1)),
      is_offshore: !!reading.is_offshore,
      nearest_sensitive_area: nearest,
      distance_to_sensitive_area_km: distance == null ? null : Number(distance.toFixed(2)),
      predicted_impact_hours: hours == null ? null : Number(hours.toFixed(2)),
      recommended_next_action: actions[severity],
      disclaimer: DISCLAIMER
    };
  }

  /** Ask the backend first, then keep demo mode functional without the API. */
  async function evaluate(reading) {
    const areas = SENSITIVE_AREAS[reading.region] || [];
    const body = {
      spill_lat: reading.spill_lat,
      spill_lon: reading.spill_lon,
      oil_confidence: reading.oil_confidence,
      area_km2: reading.area_km2,
      detected_at_utc: reading.detected_at_utc || new Date().toISOString(),
      predicted_impact_hours: reading.predicted_impact_hours == null ? null : reading.predicted_impact_hours,
      distance_to_coast_km: reading.distance_to_coast_km == null ? null : reading.distance_to_coast_km,
      is_offshore: !!reading.is_offshore,
      sensitive_areas: areas
    };

    try {
      const response = await fetch(apiUrl('/api/alerts/evaluate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      if (!response.ok) throw new Error('API returned ' + response.status);
      return await response.json();
    } catch (error) {
      console.warn('Quick Spill Alert: backend unavailable.', error);
      return localEvaluate(reading);
    }
  }

  // --- Map markers ---------------------------------------------------------
  // The Leaflet map is created lazily when the Dashboard screen first opens, so
  // an alert loaded earlier would otherwise have no layer to attach to. Resolve
  // the host at call time and stash the marker for a later retry.
  function alertHost() {
    const host = window.SpillGuardAlertsHost;
    return host && host.map && host.layer ? host : null;
  }

  /** Attach any markers that were created before the map existed. */
  function flushPendingMarkers() {
    const host = alertHost();
    if (!host) return 0;
    let attached = 0;
    alertState.alerts.forEach((alert) => {
      if (!alert.marker && alert.result) {
        alert.marker = mapMarker(alert.result, alert.id, host);
        if (alert.marker) attached += 1;
      }
    });
    return attached;
  }

  function mapMarker(result, alertId, host) {
    const L = window.L;
    const active = host || alertHost();
    if (!L || !active) return null;

    const layer = active.layer;
    const sev = result.severity;
    const icon = L.divIcon({
      className: '',
      html: '<div class="alert-map-marker" data-severity="' + escapeHtml(sev) + '">' +
        escapeHtml(SEVERITY_GLYPH[sev] || '!') + '</div>',
      iconSize: [26, 26],
      iconAnchor: [13, 13]
    });

    const marker = L.marker([result.spill.lat, result.spill.lon], { icon: icon, zIndexOffset: 900 });
    const near = result.nearest_sensitive_area
      ? result.nearest_sensitive_area.name + ' (' + result.distance_to_sensitive_area_km + ' km)'
      : 'none within 20 km';
    marker.bindPopup(
      '<strong>' + escapeHtml(sev) + ' — Quick Spill Alert</strong><br>' +
      'Detected: ' + escapeHtml(formatUtc(result.detected_at_utc)) + '<br>' +
      'Area: ' + escapeHtml(result.area_km2) + ' km² · Confidence: ' + escapeHtml(result.oil_confidence) + '%<br>' +
      'Nearest sensitive area: ' + escapeHtml(near) + '<br>' +
      '<em>' + escapeHtml(DISCLAIMER) + '</em>'
    );
    marker.alertId = alertId;
    marker.addTo(layer);
    return marker;
  }

  // --- Toasts --------------------------------------------------------------
  function toast(result, label) {
    const stack = document.getElementById('alert-toast-stack');
    if (!stack) return;

    const el = document.createElement('div');
    el.className = 'alert-toast';
    el.setAttribute('data-severity', result.severity);
    const near = result.nearest_sensitive_area
      ? result.nearest_sensitive_area.name + ' · ' + result.distance_to_sensitive_area_km + ' km'
      : 'No nearby sensitive area';

    el.innerHTML =
      '<div class="alert-toast-body">' +
      '<div class="alert-toast-head">' +
      '<span class="alert-toast-sev">' + escapeHtml(result.severity) + ' alert</span>' +
      '</div>' +
      '<div class="alert-toast-title">' + escapeHtml(label || 'Oil spill detected') + '</div>' +
      '<div class="alert-toast-meta">' +
      escapeHtml(result.area_km2) + ' km² · ' + escapeHtml(result.oil_confidence) + '% conf<br>' +
      escapeHtml(near) +
      '</div>' +
      '</div>' +
      '<button class="alert-toast-close" aria-label="Dismiss notification">&times;</button>';

    const dismiss = () => {
      el.classList.add('is-leaving');
      setTimeout(() => el.remove(), 220);
    };
    el.querySelector('.alert-toast-close').addEventListener('click', dismiss);
    stack.appendChild(el);
    setTimeout(dismiss, result.severity === 'Critical' ? 12000 : 7000);
  }

  // --- Rendering -----------------------------------------------------------
  function sortedAlerts() {
    return alertState.alerts.slice().sort((a, b) => {
      const d = SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity];
      if (d !== 0) return d;
      return new Date(b.detected_at_utc) - new Date(a.detected_at_utc);
    });
  }

  function renderBell() {
    const count = document.getElementById('alert-bell-count');
    const panelCount = document.getElementById('alert-panel-count');
    if (!count) return;

    const unread = alertState.alerts.filter((a) => !a.acknowledged).length;
    if (unread > 0) {
      count.hidden = false;
      count.textContent = unread > 99 ? '99+' : String(unread);
      count.classList.add('is-new');
    } else {
      count.hidden = true;
      count.textContent = '0';
      count.classList.remove('is-new');
    }
    if (panelCount) {
      panelCount.textContent = unread + ' active · ' + alertState.alerts.length + ' total';
    }
  }

  function cardHtml(alert) {
    const r = alert.result;
    const near = r.nearest_sensitive_area;
    const distClass = r.distance_to_sensitive_area_km != null && r.distance_to_sensitive_area_km <= 20 ? ' is-near' : '';

    return (
      '<article class="alert-card' + (alert.acknowledged ? ' is-acknowledged' : '') + '" data-severity="' + escapeHtml(r.severity) + '" data-alert-id="' + escapeHtml(alert.id) + '">' +
      '<div class="alert-card-top">' +
      '<span class="alert-sev-badge">' + escapeHtml(r.severity) + '</span>' +
      '<span class="alert-time">' + escapeHtml(formatUtc(r.detected_at_utc)) + '</span>' +
      '</div>' +
      '<div class="alert-card-title">' + escapeHtml(alert.label) + '</div>' +
      '<div class="alert-metrics">' +
      '<div class="alert-metric">' +
      '<span class="alert-metric-lbl">Location</span>' +
      '<span class="alert-metric-val">' + escapeHtml(r.spill.lat.toFixed(4)) + '°, ' + escapeHtml(r.spill.lon.toFixed(4)) + '°</span>' +
      '</div>' +
      '<div class="alert-metric">' +
      '<span class="alert-metric-lbl">Spill area</span>' +
      '<span class="alert-metric-val">' + escapeHtml(r.area_km2) + ' km²</span>' +
      '</div>' +
      '<div class="alert-metric">' +
      '<span class="alert-metric-lbl">Oil confidence</span>' +
      '<span class="alert-metric-val">' + escapeHtml(r.oil_confidence) + '%</span>' +
      '</div>' +
      '<div class="alert-metric">' +
      '<span class="alert-metric-lbl">Impact ETA</span>' +
      '<span class="alert-metric-val">' + escapeHtml(formatEta(r.predicted_impact_hours)) + '</span>' +
      '</div>' +
      '</div>' +
      (near
        ? '<div class="alert-receptor">' +
        '<span>Near <strong>' + escapeHtml(near.name) + '</strong> (' + escapeHtml(near.type_label) + ')</span>' +
        '<span class="alert-metric-val' + distClass + '" style="margin-left:auto;">' + escapeHtml(r.distance_to_sensitive_area_km) + ' km</span>' +
        '</div>'
        : '') +
      '<div class="alert-action">' +
      '<span class="alert-action-lbl">Recommended next action</span>' +
      escapeHtml(r.recommended_next_action) +
      '</div>' +
      '<div class="alert-card-actions">' +
      '<button class="alert-btn is-map" data-act="map" data-alert-id="' + escapeHtml(alert.id) + '">Show on map</button>' +
      (alert.acknowledged
        ? '<span class="alert-ack-state">✓ Acknowledged</span>'
        : '<button class="alert-btn is-ack" data-act="ack" data-alert-id="' + escapeHtml(alert.id) + '">Acknowledge</button>') +
      '</div>' +
      '</article>'
    );
  }

  function renderList() {
    const list = document.getElementById('alert-list');
    if (!list) return;

    if (!alertState.alerts.length) {
      list.innerHTML =
        '<div class="alert-empty">No alerts yet. Alerts raise automatically when a slick breaches ' +
        '&ge;75% confidence, &ge;2 km&sup2; area, or comes within 20 km of a sensitive area — ' +
        'or press <strong>Load Demo Alerts</strong>.</div>';
      return;
    }
    list.innerHTML = sortedAlerts().map(cardHtml).join('');
  }

  function renderAll() {
    renderBell();
    renderList();
  }

  // --- Alert lifecycle -----------------------------------------------------
  function addAlert(result, label) {
    if (!result || !result.alert) return null;

    // De-duplicate: same severity near the same spot should not stack up.
    const dupe = alertState.alerts.find((a) =>
      a.result.severity === result.severity &&
      Math.abs(a.result.spill.lat - result.spill.lat) < 0.001 &&
      Math.abs(a.result.spill.lon - result.spill.lon) < 0.001
    );
    if (dupe) return dupe;

    const alert = {
      id: uid(),
      label: label || 'Oil spill detected',
      result: result,
      acknowledged: false,
      marker: null
    };
    alert.marker = mapMarker(result, alert.id);
    alertState.alerts.push(alert);
    alertState.byId.set(alert.id, alert);

    renderAll();
    toast(result, alert.label);

    const bell = document.getElementById('alert-bell-btn');
    if (bell) {
      bell.classList.remove('is-ringing');
      void bell.offsetWidth; // restart the animation
      bell.classList.add('is-ringing');
    }
    return alert;
  }

  function acknowledge(id) {
    const alert = alertState.byId.get(id);
    if (!alert || alert.acknowledged) return;
    alert.acknowledged = true;
    renderAll();
  }

  function focusOnMap(id) {
    const alert = alertState.byId.get(id);
    const L = window.L;
    if (!alert || !L) return;

    const focus = () => {
      const active = window.SpillGuardAlertsHost;
      const map = active && active.map;
      if (!map) return false;

      const { lat, lon } = alert.result.spill;
      const target = alert.result.nearest_sensitive_area &&
        alert.result.distance_to_sensitive_area_km <= 20 ? 11 : 9;
      try {
        map.flyTo([lat, lon], target, { duration: 0.8 });
      } catch (e) {
        map.setView([lat, lon], target);
      }
      if (!alert.marker) flushPendingMarkers();
      if (alert.marker && alert.marker.openPopup) {
        setTimeout(() => {
          try { alert.marker.openPopup(); } catch (e) { /* popup is cosmetic */ }
        }, 850);
      }
      return true;
    };

    setPanel(false);
    if (focus()) return;

    // The map is lazy-loaded, so open the dashboard before retrying.
    document.getElementById('side-btn-dashboard')?.click();
    let attempts = 0;
    const retry = () => {
      if (focus() || attempts++ >= 20) return;
      setTimeout(retry, 100);
    }
    retry();
  }

  function emergencyPayload(alert) {
    const r = alert.result;
    const vessel = SPILLGUARD_DATA.vessels?.find((item) => item.riskLevel === 'CRITICAL' || item.riskScore >= 85);
    return {
      alertId: alert.id,
      location: `${r.spill.lat.toFixed(4)}°, ${r.spill.lon.toFixed(4)}°`,
      area: `${r.area_km2} km²`,
      severity: r.severity.toUpperCase(),
      detected: formatUtc(r.detected_at_utc),
      confidence: `${r.oil_confidence}%`,
      vessel: vessel ? `${vessel.name} · Potential Source Vessel · Requires verification` : 'No potential source vessel available',
      coastalRisk: r.nearest_sensitive_area ? `${r.nearest_sensitive_area.name} · ${r.distance_to_sensitive_area_km} km` : 'No nearby coastal area in model range',
      drift: 'Current drift direction requires operational verification',
      reportLink: `${location.origin}/#incident-${encodeURIComponent(alert.id)}`
    };
  }

  function renderEmergencyHistory() {
    const history = document.getElementById('emergency-history-list');
    if (!history) return;
    history.innerHTML = emergencyState.history.length ? emergencyState.history.map((item, index) =>
      `<button type="button" class="emergency-history-item" data-history-index="${index}"><strong>${escapeHtml(item.alertId)}</strong><span>${escapeHtml(item.time)}</span><span>${escapeHtml(item.recipient)}</span><b>${escapeHtml(item.status)}</b></button>`
    ).join('') : '<div class="emergency-empty">No transmissions recorded.</div>';
  }

  function renderEmergencyPanel() {
    const active = document.getElementById('emergency-active-list');
    if (!active) return;
    const alerts = sortedAlerts().filter((item) => item.result.severity === 'High' || item.result.severity === 'Critical');
    active.innerHTML = alerts.length ? alerts.map((item) => `<div class="emergency-active-item"><span class="alert-sev-badge">${escapeHtml(item.result.severity)}</span><div><strong>OIL SPILL ALERT</strong><small>${escapeHtml(item.label)} · ${escapeHtml(formatUtc(item.result.detected_at_utc))}</small></div><button class="alert-btn emergency-send-card-btn" data-emergency-id="${escapeHtml(item.id)}">SEND ALERT TO AUTHORITIES</button></div>`).join('') : '<div class="emergency-empty">No High or Critical possible oil-slick alerts are active.</div>';
    renderEmergencyHistory();
  }

  async function openEmergencyPanel() {
    if (!alertState.alerts.length) {
      await runDemo();
      setPanel(false);
    }
    renderEmergencyPanel();
    const modal = document.getElementById('emergency-modal');
    modal?.classList.add('is-open'); modal?.setAttribute('aria-hidden', 'false');
  }

  function closeEmergencyPanel() {
    const modal = document.getElementById('emergency-modal');
    modal?.classList.remove('is-open'); modal?.setAttribute('aria-hidden', 'true');
  }

  function openEmergencyConfirm(id) {
    const alert = alertState.byId.get(id);
    if (!alert) return;
    emergencyState.selected = alert;
    const p = emergencyPayload(alert);
    const body = document.getElementById('emergency-confirm-body');
    if (body) body.innerHTML = `<div class="emergency-review-grid">${[['Alert ID',p.alertId],['Location',p.location],['Severity / area',p.severity + ' / ' + p.area],['Detection time',p.detected],['AI confidence',p.confidence],['Potential Source Vessel(s)',p.vessel],['Nearby coastal areas at risk',p.coastalRisk],['Current drift direction',p.drift]].map(([label,value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join('')}</div><p class="emergency-disclaimer">AI detection only. Potential source vessels require verification. Field verification is required before legal or operational conclusions.</p><div class="emergency-message-preview">SMS preview: Possible oil slick at ${escapeHtml(p.location)}. Severity ${escapeHtml(p.severity)}, estimated area ${escapeHtml(p.area)}, detected ${escapeHtml(p.detected)}. Drift: ${escapeHtml(p.drift)}. Alert ID ${escapeHtml(p.alertId)}. ${escapeHtml(p.reportLink)}</div>`;
    document.getElementById('emergency-send-sms').disabled = false;
    document.getElementById('emergency-confirm-status').textContent = '';
    document.getElementById('emergency-confirm-modal')?.classList.add('is-open');
  }

  function closeEmergencyConfirm() { document.getElementById('emergency-confirm-modal')?.classList.remove('is-open'); }

  async function transmitEmergency(method) {
    const alert = emergencyState.selected;
    if (!alert) return;
    const payload = emergencyPayload(alert);
    const statusElement = document.getElementById('emergency-confirm-status');
    const button = document.getElementById(method === 'SMS' ? 'emergency-send-sms' : 'emergency-send-official');
    if (button) button.disabled = true;
    if (statusElement) statusElement.textContent = 'Transmitting alert…';
    let result;
    try {
      const response = await fetch(apiUrl('/api/emergency-alerts/transmit'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ method, ...payload })
      });
      result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || 'Emergency transmission is not configured.');
    } catch (error) {
      // Keep the static deployment usable while making the demo state explicit.
      result = { status: 'SIMULATED SENT' };
    }
    const record = { ...payload, time: formatUtc(new Date().toISOString()), recipient: 'Configured Maritime Authority Group', method, status: result.status, incidentStatus: 'Awaiting field verification' };
    emergencyState.history.unshift(record); emergencyState.history = emergencyState.history.slice(0, 25); localStorage.setItem('spillsense-emergency-history', JSON.stringify(emergencyState.history));
    document.getElementById('emergency-confirm-status').textContent = record.status === 'SIMULATED SENT'
      ? `SIMULATED ALERT SENT · DEMO MODE · ${record.time}`
      : `Alert successfully sent to authorities. ${record.time} · ${record.recipient} · ${method} · ${record.status}`;
    document.getElementById('emergency-send-sms').disabled = true;
    renderEmergencyPanel();
  }

  function openHistoryDetail(index) {
    const record = emergencyState.history[index];
    if (!record) return;
    const body = document.getElementById('emergency-confirm-body');
    if (body) body.innerHTML = `<div class="emergency-review-grid">${[['Alert ID',record.alertId],['Location',record.location],['Severity / area',record.severity + ' / ' + record.area],['Detection time',record.detected],['AI confidence',record.confidence],['Potential Source Vessel(s)',record.vessel],['Nearby coastal areas at risk',record.coastalRisk],['Current drift direction',record.drift],['Recipient authority',record.recipient],['Transmission method',record.method],['Transmission status',record.status],['Incident status',record.incidentStatus]].map(([label,value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join('')}</div><p class="emergency-disclaimer">AI detection only. Potential source vessels require verification. Field verification is required before legal or operational conclusions.</p>`;
    document.getElementById('emergency-confirm-status').textContent = 'Historical transmission record';
    document.getElementById('emergency-confirm-modal')?.classList.add('is-open');
  }

  // --- Panel controls ------------------------------------------------------
  function setPanel(open) {
    const panel = document.getElementById('alert-panel');
    const bell = document.getElementById('alert-bell-btn');
    if (!panel) return;
    alertState.isOpen = open;
    panel.classList.toggle('is-open', open);
    panel.setAttribute('aria-hidden', open ? 'false' : 'true');
    if (bell) bell.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  async function runDemo() {
    const button = document.getElementById('btn-alert-demo');
    if (button) {
      button.disabled = true;
      button.textContent = 'Evaluating…';
    }
    let added = 0;
    let lastSeverity = null;

    for (const reading of DEMO_READINGS) {
      const result = await evaluate(reading);
      if (result && result.alert) {
        addAlert(result, reading.label);
        added += 1;
        lastSeverity = result.severity;
      }
    }

    if (button) {
      button.disabled = false;
      button.textContent = added ? 'Load Demo Alerts (' + added + ')' : 'Load Demo Alerts';
    }
    setPanel(true);

    if (!added) {
      const list = document.getElementById('alert-list');
      if (list) {
        list.innerHTML =
          '<div class="alert-empty">Demo evaluation returned no alerts. Start the Spill Sense backend ' +
          'on <span class="mono">http://127.0.0.1:8000</span> and try again.</div>';
      }
    }
    return { added, lastSeverity };
  }

  // --- Wiring --------------------------------------------------------------
  function wire() {
    document.getElementById('alert-bell-btn')?.addEventListener('click', () => {
      setPanel(!alertState.isOpen);
    });
    document.getElementById('alert-panel-close')?.addEventListener('click', () => setPanel(false));
    document.getElementById('emergency-alerts-btn')?.addEventListener('click', openEmergencyPanel);
    document.getElementById('emergency-close')?.addEventListener('click', closeEmergencyPanel);
    document.getElementById('emergency-confirm-close')?.addEventListener('click', closeEmergencyConfirm);
    document.getElementById('emergency-confirm-cancel')?.addEventListener('click', closeEmergencyConfirm);
    document.getElementById('emergency-send-sms')?.addEventListener('click', () => transmitEmergency('SMS'));
    document.getElementById('emergency-send-official')?.addEventListener('click', () => transmitEmergency('OFFICIAL CHANNEL'));
    document.getElementById('btn-alert-demo')?.addEventListener('click', runDemo);
    document.getElementById('btn-alert-ack-all')?.addEventListener('click', () => {
      alertState.alerts.forEach((a) => { a.acknowledged = true; });
      renderAll();
    });
    document.getElementById('btn-alert-clear')?.addEventListener('click', () => {
      alertState.alerts.forEach((a) => {
        if (a.marker) { try { a.marker.remove(); } catch (e) { /* already gone */ } }
      });
      alertState.alerts = [];
      alertState.byId.clear();
      renderAll();
      setPanel(true);
    });

    // Card buttons are delegated so cards can be re-rendered freely.
    document.getElementById('alert-list')?.addEventListener('click', (event) => {
      const button = event.target.closest('[data-act]');
      if (!button) return;
      const id = button.getAttribute('data-alert-id');
      if (button.getAttribute('data-act') === 'ack') acknowledge(id);
      else if (button.getAttribute('data-act') === 'map') focusOnMap(id);
      else if (button.getAttribute('data-act') === 'emergency') openEmergencyConfirm(id);
    });
    document.addEventListener('click', (event) => {
      const button = event.target.closest('[data-emergency-id]');
      if (button) openEmergencyConfirm(button.getAttribute('data-emergency-id'));
    });
    document.getElementById('emergency-history-list')?.addEventListener('click', (event) => {
      const item = event.target.closest('[data-history-index]');
      if (item) openHistoryDetail(Number(item.getAttribute('data-history-index')));
    });

    // Escape closes the panel — same as the existing drawer convention.
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && alertState.isOpen) setPanel(false);
    });
  }

  // --- Public surface ------------------------------------------------------
  // app.js calls these; keeping them here avoids touching the existing flow.
  window.SpillGuardAlerts = {
    init(options) {
      alertState.apiBase = (options && options.apiBase) || '';
      wire();
      renderAll();
      return this;
    },
    /** Evaluate a live reading (e.g. from the ML detector) and raise an alert. */
    async raise(reading, label) {
      const result = await evaluate(reading);
      return addAlert(result, label);
    },
    /** True once the Leaflet map and alert layer are both available. */
    isMapReady: () => !!alertHost(),
    /** Evaluate without raising — useful for tests and previews. */
    evaluate,
    setPanel,
    runDemo,
    /** Call after the Leaflet map is created so queued alerts get their markers. */
    flushPendingMarkers,
    getAlerts: () => alertState.alerts.slice(),
    SENSITIVE_AREAS,
    DEMO_READINGS,
    DISCLAIMER
  };
})();
