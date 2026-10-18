/**
 * Spill Sense — Application Logic & Interactive Prototype Controller
 */

document.addEventListener('DOMContentLoaded', async () => {
  const apiUrl = (path) => `${(window.SPILLGUARD_API_BASE || '').replace(/\/$/, '')}${path}`;

  // The static fixture remains as an offline fallback when the API is unavailable.
  try {
    const response = await fetch(apiUrl('/api/bootstrap'));
    if (!response.ok) throw new Error(`API returned ${response.status}`);
    const serverData = await response.json();
    Object.assign(SPILLGUARD_DATA, serverData);
  } catch (error) {
    console.warn('Spill Sense API unavailable; using bundled demo data.', error);
  }

  // =========================================================================
  // STATE MANAGEMENT & ROUTER
  // =========================================================================
  const state = {
    currentScreen: 'screen-splash',
    currentRegion: 'malacca',
    regionRequestId: 0,
    selectedSpill: SPILLGUARD_DATA.spills[0],
    selectedVesselFilter: 'all',
    masterVessels: Array.isArray(SPILLGUARD_DATA.vessels) ? [...SPILLGUARD_DATA.vessels] : [],
    masterSpills: Array.isArray(SPILLGUARD_DATA.spills) ? [...SPILLGUARD_DATA.spills] : [],
    isPlayingScrubber: false,
    scrubberInterval: null,
    scrubberSpeed: 1,
    driftAnimationId: null,
    isLeafletInit: false,
    map: null,
    analysisData: {
      rankings: [],
      darkWarnings: [],
      drift: null,
      matchResults: [],
      originZone: null
    },
    layers: {
      slicks: null,
      ais: null,
      drift: null,
      eez: null,
      corridor: null,
      waypoints: null,
      poiFeatures: null,
      liveVessels: null,
      ml: null,
      alerts: null
    },
    liveVesselInterval: null
  };

  state.masterVessels = Array.isArray(SPILLGUARD_DATA.vessels) ? [...SPILLGUARD_DATA.vessels] : [];
  state.masterSpills = Array.isArray(SPILLGUARD_DATA.spills) ? [...SPILLGUARD_DATA.spills] : [];

  const screens = [
    'screen-splash',
    'screen-landing',
    'screen-login',
    'screen-dashboard',
    'screen-investigation',
    'screen-vessels',
    'screen-analytics'
  ];

  const appShellScreens = [
    'screen-dashboard',
    'screen-investigation',
    'screen-vessels',
    'screen-analytics'
  ];

  function navigateTo(screenId) {
    if (!screens.includes(screenId)) return;
    state.currentScreen = screenId;

    // Update Quick Nav Active State
    document.querySelectorAll('.proto-btn').forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-target') === screenId);
    });

    const isAppShell = appShellScreens.includes(screenId);
    const appShellWrapper = document.getElementById('app-shell-wrapper');

    // Handle App Shell Visibility
    if (isAppShell) {
      // Hide public standalone screens
      document.querySelectorAll('#screen-splash, #screen-landing, #screen-login').forEach(el => {
        el.classList.remove('active-screen');
        el.style.display = '';
      });

      appShellWrapper.style.display = 'flex';

      // Switch sub-screens in app shell
      appShellScreens.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
          if (id === screenId) {
            el.classList.add('active-screen');
            el.style.display = '';
          } else {
            el.classList.remove('active-screen');
            el.style.display = '';
          }
        }
      });

      // Update Sidebar Active Icons
      document.querySelectorAll('.sidebar-btn').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-app-view') === screenId);
      });

      // If opening dashboard, invalidate Leaflet map size
      if (screenId === 'screen-dashboard') {
        setTimeout(() => {
          if (state.map) {
            state.map.invalidateSize();
            // refresh region UI on dashboard open
            updateRegionUI(state.currentRegion);
          } else {
            initLeafletMap();
            // after initialization, render region-specific data
            setTimeout(() => updateRegionUI(state.currentRegion), 450);
          }
        }, 100);
      }

      // If opening investigation, start drift simulation canvas
      if (screenId === 'screen-investigation') {
        setTimeout(() => {
          initDriftSimulation();
        }, 100);
      }

    } else {
      // Standalone screen
      appShellWrapper.style.display = 'none';
      screens.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
          if (id === screenId) {
            el.classList.add('active-screen');
            el.style.display = '';
          } else {
            el.classList.remove('active-screen');
            el.style.display = '';
          }
        }
      });
    }

    window.scrollTo(0, 0);
  }

  // Bind Proto Nav Buttons
  document.querySelectorAll('.proto-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.getAttribute('data-target');
      navigateTo(target);
    });
  });

  // Bind Sidebar Buttons
  document.querySelectorAll('.sidebar-btn[data-app-view]').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.getAttribute('data-app-view');
      navigateTo(target);
    });
  });

  document.getElementById('sidebar-logo-btn')?.addEventListener('click', () => {
    navigateTo('screen-dashboard');
  });


  // =========================================================================
  // SCREEN 1: SPLASH SCREEN LOGIC
  // =========================================================================
  const splashProgress = document.getElementById('splash-progress-bar');
  const splashStatusText = document.getElementById('splash-status-text');
  const splashPercentText = document.getElementById('splash-percent-text');
  const btnSkipSplash = document.getElementById('btn-skip-splash');

  const splashSteps = [
    { pct: 15, text: "Syncing Sentinel-1 SAR telemetry..." },
    { pct: 38, text: "Calibrating VV/VH polarimetric filters..." },
    { pct: 64, text: "Streaming global AIS Class-A/B beacons..." },
    { pct: 88, text: "Initializing hydrodynamic drift model..." },
    { pct: 100, text: "Spill Sense Defense Network v4.8: ONLINE" }
  ];

  let stepIdx = 0;
  function runSplashSequence() {
    if (state.currentScreen !== 'screen-splash') return;

    if (stepIdx < splashSteps.length) {
      const step = splashSteps[stepIdx];
      if (splashProgress) splashProgress.style.width = step.pct + '%';
      if (splashStatusText) splashStatusText.textContent = step.text;
      if (splashPercentText) splashPercentText.textContent = step.pct + '%';
      stepIdx++;
      setTimeout(runSplashSequence, 750);
    } else {
      setTimeout(() => {
        if (state.currentScreen === 'screen-splash') {
          navigateTo('screen-landing');
        }
      }, 600);
    }
  }

  setTimeout(runSplashSequence, 400);

  btnSkipSplash?.addEventListener('click', () => {
    navigateTo('screen-landing');
  });


  // =========================================================================
  // SCREEN 2: LANDING PAGE ACTIONS
  // =========================================================================
  document.getElementById('landing-login-btn')?.addEventListener('click', () => {
    navigateTo('screen-login');
  });

  document.getElementById('landing-launch-btn')?.addEventListener('click', () => {
    navigateTo('screen-dashboard');
  });

  document.getElementById('hero-demo-cta')?.addEventListener('click', () => {
    navigateTo('screen-login');
  });

  document.getElementById('hero-how-cta')?.addEventListener('click', () => {
    const el = document.getElementById('how-it-works');
    if (el) el.scrollIntoView({ behavior: 'smooth' });
  });


  // =========================================================================
  // SCREEN 3: LOGIN PAGE ACTIONS
  // =========================================================================
  const roleChips = document.querySelectorAll('.role-chip');
  roleChips.forEach(chip => {
    chip.addEventListener('click', () => {
      roleChips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
    });
  });

  const btnDemoLogin = document.getElementById('btn-demo-login');
  btnDemoLogin?.addEventListener('click', () => {
    btnDemoLogin.innerHTML = `
      <span class="pulse-cyan-dot"></span>
      <span>Authenticating USCG Credentials...</span>
    `;
    setTimeout(() => {
      navigateTo('screen-dashboard');
      btnDemoLogin.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3"/></svg>
        <span>Login with Demo Account</span>
      `;
    }, 600);
  });

  document.getElementById('btn-topbar-logout')?.addEventListener('click', () => {
    navigateTo('screen-login');
  });


  // =========================================================================
  // LIVE CLOCK
  // =========================================================================
  function updateLiveClock() {
    const clockEl = document.getElementById('live-utc-clock');
    if (!clockEl) return;
    const now = new Date();
    const utcString = now.toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
    clockEl.textContent = utcString;
  }
  setInterval(updateLiveClock, 1000);
  updateLiveClock();


  // =========================================================================
  // SCREEN 4: MAIN DASHBOARD & LEAFLET DARK INTERACTIVE MAP
  // =========================================================================
  function initLeafletMap() {
    if (state.isLeafletInit || !window.L) return;
    const mapEl = document.getElementById('leaflet-map');
    if (!mapEl) return;

    // Ensure container has a rendered height; sometimes flex parents are not sized
    // immediately which causes Leaflet to render an empty map. Force a sensible
    // temporary height if clientHeight is zero.
    if (mapEl.clientHeight === 0) {
      mapEl.style.minHeight = '60vh';
    }

    const reg = SPILLGUARD_DATA.regions[state.currentRegion] || {
      center: [2.5228, 101.7967],
      zoom: 10
    };

    state.map = L.map('leaflet-map', {
      center: reg.center,
      zoom: reg.zoom,
      zoomControl: true,
      attributionControl: false,
      scrollWheelZoom: true,
      preferCanvas: true
    });
    if (reg.bounds) state.map.fitBounds(reg.bounds, { padding: [24, 24] });

    // Prefer MapTiler hybrid tiles, then Mapbox, then the CARTO fallback.
    try {
      const mapTilerKey = (window.MAPTILER_KEY || '').trim();
      const mapboxToken = (window.MAPBOX_TOKEN || '').trim();
      if (mapTilerKey) {
        L.tileLayer(`https://api.maptiler.com/maps/hybrid-v4/256/{z}/{x}/{y}.jpg?key=${encodeURIComponent(mapTilerKey)}`, {
          tileSize: 256,
          maxZoom: 20,
          attribution: '&copy; MapTiler &copy; OpenStreetMap contributors'
        }).addTo(state.map);
      } else if (mapboxToken) {
        const style = window.MAPBOX_STYLE || 'mapbox/dark-v10';
        const url = `https://api.mapbox.com/styles/v1/${style}/tiles/{z}/{x}/{y}@2x?access_token=${mapboxToken}`;
        L.tileLayer(url, {
          tileSize: 512,
          zoomOffset: -1,
          maxZoom: 20,
          attribution: '© Mapbox © OpenStreetMap'
        }).addTo(state.map);
      } else {
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
          subdomains: 'abcd',
          maxZoom: 20,
          attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
        }).addTo(state.map);
      }
    } catch (e) {
      // If anything fails, fallback to CARTO
      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        subdomains: 'abcd',
        maxZoom: 20,
        attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
      }).addTo(state.map);
      console.warn('Map tiles failed, falling back to CARTO:', e);
    }

    state.layers.slicks = L.layerGroup().addTo(state.map);
    state.layers.ais = L.layerGroup().addTo(state.map);
    state.layers.drift = L.layerGroup().addTo(state.map);
    state.layers.corridor = L.layerGroup().addTo(state.map);
    state.layers.waypoints = L.layerGroup().addTo(state.map);
    state.layers.poiFeatures = L.layerGroup().addTo(state.map);
    state.layers.liveVessels = L.layerGroup().addTo(state.map);

    // Quick Spill Alert markers live on their own layer so the existing toggles
    // are untouched.
    state.layers.alerts = L.layerGroup().addTo(state.map);
    if (window.SpillGuardAlerts) {
      window.SpillGuardAlertsHost = { map: state.map, layer: state.layers.alerts };
      // Alerts raised before the map existed are queued without markers — give
      // them theirs now that the layer is live.
      window.SpillGuardAlerts.flushPendingMarkers();
    }
    renderMapData();
    renderMaritimeCorridor();
    startLiveVesselFeed();
    state.isLeafletInit = true;

    // Give Leaflet a moment to finish tile requests and layout, then invalidate
    // size to ensure tiles are visible and controls are positioned correctly.
    setTimeout(() => {
      try {
        if (state.map) state.map.invalidateSize();
      } catch (e) {
        console.warn('Leaflet invalidateSize failed', e);
      }
    }, 350);
  }

  function renderMapData() {
    // Accept optional filtered arrays when provided by updateRegionUI
    const spillsToUse = arguments[0] || SPILLGUARD_DATA.spills || [];
    const vesselsToUse = arguments[1] || SPILLGUARD_DATA.vessels || [];
    if (!state.map) return;
    state.layers.slicks.clearLayers();
    state.layers.ais.clearLayers();
    state.layers.drift.clearLayers();

    spillsToUse.forEach(spill => {
      const polygon = L.polygon(spill.slickPolygon || [], {
        color: '#EF4444',
        weight: 2,
        opacity: 1,
        dashArray: '6 6',
        fillColor: '#EF4444',
        fillOpacity: 0.3
      }).addTo(state.layers.slicks);

      polygon.on('click', () => openSpillDrawer(spill));
    });

    vesselsToUse.forEach((vessel, index) => {
      const lat = Array.isArray(vessel.coords) ? vessel.coords[0] : (vessel.lat || null);
      const lng = Array.isArray(vessel.coords) ? vessel.coords[1] : (vessel.lon || null);
      if (lat === null || lng === null) return;

      const vesselMarker = L.circleMarker([lat, lng], {
        radius: 7,
        color: '#F59E0B',
        weight: 2,
        opacity: 1,
        dashArray: '5 5',
        fillColor: '#FFFFFF',
        fillOpacity: 1
      }).addTo(state.layers.ais);

      vesselMarker.bindPopup(`
        <div style="color:#0b1220; font-size:12px; line-height:1.5;">
          <strong>${vessel.name || `Vessel ${index + 1}`}</strong><br>
          Timestamp: ${vessel.lastAisPing || 'N/A'}<br>
          Status: ${vessel.isDarkVessel ? 'Dark vessel alert' : 'AIS online'}
        </div>
      `);

      if (Array.isArray(vessel.trackHistory) && vessel.trackHistory.length > 1) {
        L.polyline(vessel.trackHistory, {
          color: '#FF4438',
          weight: 2,
          opacity: 0.95,
          dashArray: '8 8'
        }).addTo(state.layers.ais);

        if (window.L && typeof L.polylineDecorator === 'function') {
          L.polylineDecorator(vessel.trackHistory, {
            patterns: [{
              offset: '20%',
              repeat: '36px',
              symbol: L.Symbol.arrowHead({
                pixelSize: 10,
                headAngle: 55,
                polygon: false,
                pathOptions: {
                  stroke: true,
                  color: '#FF4438',
                  weight: 2,
                  opacity: 1,
                  fill: false
                }
              })
            }]
          }).addTo(state.layers.ais);
        }
      }
    });

    const primarySpill = (spillsToUse && spillsToUse[0]) || {};
    const basePoint = Array.isArray(primarySpill.coords) ? primarySpill.coords : (SPILLGUARD_DATA.regions[state.currentRegion]?.center || [2.5228, 101.7967]);
    const predictedDrift = [
      basePoint,
      [basePoint[0] + 0.06, basePoint[1] - 0.04],
      [basePoint[0] + 0.11, basePoint[1] - 0.01]
    ];

    L.polyline(predictedDrift, {
      color: '#22D3EE',
      weight: 3,
      opacity: 1,
      smoothFactor: 1
    }).addTo(state.layers.drift);

    const defaultTrack = (vesselsToUse && vesselsToUse[0] && Array.isArray(vesselsToUse[0].trackHistory))
      ? vesselsToUse[0].trackHistory
      : vesselsToUse && vesselsToUse[0] && Array.isArray(vesselsToUse[0].coords)
        ? [basePoint, vesselsToUse[0].coords]
        : [basePoint];

    if (defaultTrack.length > 1) {
      const vesselTrack = L.polyline(defaultTrack, {
        color: '#FF4438',
        weight: 2,
        opacity: 0.95,
        dashArray: '8 8'
      }).addTo(state.layers.drift);

      if (window.L && typeof L.polylineDecorator === 'function') {
        L.polylineDecorator(defaultTrack, {
          patterns: [{
            offset: '20%',
            repeat: '36px',
            symbol: L.Symbol.arrowHead({
              pixelSize: 11,
              headAngle: 55,
              polygon: false,
              pathOptions: {
                stroke: true,
                color: '#FF4438',
                weight: 2,
                opacity: 1,
                fill: false
              }
            })
          }]
        }).addTo(state.layers.drift);
      }

      vesselTrack.bindPopup(
        '<div style="color:#0b1220; font-size:12px; line-height:1.5;">' +
        '<strong>Vessel track</strong><br>' +
        'Heading history and route corridor' +
        '</div>'
      );
    }

    if (state.analysisData.drift) renderDriftForecast(state.analysisData.drift);
    state.map.invalidateSize();
  }

  // =========================================================================
  // MARITIME CORRIDOR, WAYPOINTS, POLYGON ZONE, LABELS & POI FEATURES
  // =========================================================================
  function renderMaritimeCorridor() {
    if (!state.map) return;

    const region = SPILLGUARD_DATA.regions[state.currentRegion];
    const overlays = region && region.overlays;
    if (!overlays || !Array.isArray(overlays.corridor)) {
      console.warn(`Missing overlay configuration for region: ${state.currentRegion}`);
      return;
    }

    // Clear previous corridor / POI layers
    state.layers.corridor.clearLayers();
    state.layers.waypoints.clearLayers();
    state.layers.poiFeatures.clearLayers();

    // ---- 1. Red Dashed Maritime Corridor (shipping lane polyline) ----
    const corridorCoords = overlays.corridor;

    const corridor = L.polyline(corridorCoords, {
      color: '#FF4438',
      weight: 3.5,
      opacity: 0.92,
      dashArray: '12 8',
      lineCap: 'round',
      lineJoin: 'round',
      className: 'maritime-corridor-line'
    }).addTo(state.layers.corridor);

    corridor.bindPopup(
      '<div style="color:#0b1220;font-size:12px;line-height:1.5;">' +
      '<strong style="color:#FF4438;">Maritime Corridor</strong><br>' +
      `${region.name} monitored shipping lane<br>` +
      '<span style="font-family:monospace;font-size:11px;">Traffic Separation Scheme</span></div>'
    );

    // ---- 2. Red Polygonal Priority Monitoring Zone ----
    const priorityZone = L.polygon(overlays.priorityZone || [], {
      color: '#FF4438',
      weight: 2.5,
      opacity: 0.9,
      fillColor: '#FF4438',
      fillOpacity: 0.12,
      dashArray: '6 4',
      className: 'priority-zone-polygon'
    }).addTo(state.layers.poiFeatures);

    priorityZone.bindPopup(
      '<div style="color:#0b1220;font-size:12px;line-height:1.5;">' +
      '<strong style="color:#FF4438;">⚠ Priority Monitoring Zone</strong><br>' +
      `${region.name} critical maritime area<br>` +
      '<span style="font-family:monospace;font-size:11px;">High vessel traffic density</span></div>'
    );

    // ---- 3. Cyan Intersecting Line (Point of Interest / SAR intercept) ----
    const cyanLine = L.polyline(overlays.sarVector || [], {
      color: '#00D4FF',
      weight: 3,
      opacity: 0.85,
      dashArray: '4 6',
      className: 'poi-intercept-line'
    }).addTo(state.layers.poiFeatures);

    // Add a pulsing circle at the intersection point
    const intersectPoint = overlays.sarIntercept;
    L.circleMarker(intersectPoint, {
      radius: 10,
      color: '#00D4FF',
      weight: 2,
      opacity: 1,
      fillColor: '#00D4FF',
      fillOpacity: 0.25,
      className: 'poi-intercept-marker'
    }).addTo(state.layers.poiFeatures)
      .bindPopup(
        '<div style="color:#0b1220;font-size:12px;line-height:1.5;">' +
        '<strong style="color:#00838f;">SAR Intercept Point</strong><br>' +
        'Corridor–Slick intersection detected<br>' +
        '<span style="font-family:monospace;font-size:11px;">02°23\'06"N, 101°52\'48"E</span></div>'
      );

    cyanLine.bindTooltip('SAR Intercept Vector', {
      permanent: false,
      direction: 'center',
      className: 'sg-poi-tooltip'
    });

  }


  // =========================================================================
  // LIVE VESSEL POSITION FEED (30-second auto-refresh)
  // Uses the Digi-Traffic / Finnish AIS open API as a reliable public source.
  // Fallback: simulated data if the API is unreachable.
  // =========================================================================
  function buildVesselApiUrl() {
    const region = SPILLGUARD_DATA.regions[state.currentRegion];
    const feed = region && region.liveFeed;
    if (!feed) return null;
    // Fetch vessels updated in the last 5 minutes
    const fiveMinAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    return `https://meri.digitraffic.fi/api/ais/v1/locations?latitude=${feed.lat}&longitude=${feed.lon}&radius=${feed.radius}&from=${encodeURIComponent(fiveMinAgo)}`;
  }

  // Simulated vessel positions for the selected region when live AIS is unavailable.
  function getSimulatedVessels() {
    const base = getEntitiesForRegion(state.currentRegion).vessels || [];

    // Add slight random drift to simulate movement
    return base.map(v => {
      const lat = Array.isArray(v.coords) ? v.coords[0] : v.lat;
      const lon = Array.isArray(v.coords) ? v.coords[1] : v.lon;
      return {
        ...v,
        lat: lat + (Math.random() - 0.5) * 0.01,
        lon: lon + (Math.random() - 0.5) * 0.01,
        speed: Math.round((v.speed + (Math.random() - 0.5) * 2) * 10) / 10
      };
    });
  }

  async function fetchLiveVesselPositions() {
    if (!state.map || !state.layers.liveVessels) return;

    const regionAtRequest = state.currentRegion;
    let vessels = [];

    try {
      const vesselApiUrl = buildVesselApiUrl();
      if (!vesselApiUrl) throw new Error('No vessel feed configured for region');
      const resp = await fetch(vesselApiUrl, {
        signal: AbortSignal.timeout(8000)
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();

      // Digi-Traffic returns { features: [...] } in GeoJSON
      if (data && Array.isArray(data.features)) {
        vessels = data.features.slice(0, 30).map(f => ({
          mmsi: f.mmsi || f.properties?.mmsi || 0,
          name: f.properties?.name || `Vessel ${f.mmsi || '?'}`,
          lat: f.geometry?.coordinates?.[1] ?? 0,
          lon: f.geometry?.coordinates?.[0] ?? 0,
          speed: f.properties?.sog ?? 0,
          heading: f.properties?.cog ?? 0
        }));
      }
    } catch (err) {
      console.warn('Live vessel API unavailable, using simulated data:', err.message);
    }

    // Fallback to simulation if API returned nothing
    if (!vessels.length) {
      vessels = getSimulatedVessels();
    }

    if (regionAtRequest === state.currentRegion) updateLiveVesselMarkers(vessels);
  }

  function updateLiveVesselMarkers(vessels) {
    state.layers.liveVessels.clearLayers();

    vessels.forEach(v => {
      if (!v.lat || !v.lon) return;

      // Ship-shaped SVG icon
      const vesselIcon = L.divIcon({
        className: 'sg-live-vessel-icon',
        html: `<div class="sg-vessel-dot" style="transform:rotate(${v.heading || 0}deg);" title="${v.name || 'Vessel'}">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2L6 18H18L12 2Z" fill="#00D4FF" fill-opacity="0.9" stroke="#FFFFFF" stroke-width="1.5" stroke-linejoin="round"/>
            <rect x="10" y="16" width="4" height="4" rx="1" fill="#00D4FF" stroke="#FFFFFF" stroke-width="0.8"/>
          </svg>
        </div>`,
        iconSize: [18, 18],
        iconAnchor: [9, 9]
      });

      const marker = L.marker([v.lat, v.lon], { icon: vesselIcon }).addTo(state.layers.liveVessels);

      marker.bindPopup(
        `<div style="color:#0b1220;font-size:12px;line-height:1.6;min-width:160px;">
          <strong>${v.name || 'Unknown Vessel'}</strong><br>
          <span style="font-family:monospace;font-size:11px;">MMSI: ${v.mmsi}</span><br>
          Speed: ${v.speed} kt &nbsp;|&nbsp; Heading: ${v.heading}°<br>
          <span style="color:#888;font-size:10px;">Live AIS • Updated ${new Date().toLocaleTimeString()}</span>
        </div>`
      );
    });
  }

  function startLiveVesselFeed() {
    // Clear any existing interval
    if (state.liveVesselInterval) {
      clearInterval(state.liveVesselInterval);
    }

    // Initial fetch
    fetchLiveVesselPositions();

    // Refresh every 30 seconds
    state.liveVesselInterval = setInterval(fetchLiveVesselPositions, 30000);
    console.log('Spill Sense: Live vessel feed started (30s interval)');
  }

  // Layer Toggle Controls
  document.getElementById('layer-toggle-slicks')?.addEventListener('click', function() {
    this.classList.toggle('active');
    if (this.classList.contains('active')) state.layers.slicks.addTo(state.map);
    else state.map.removeLayer(state.layers.slicks);
  });

  document.getElementById('layer-toggle-ais')?.addEventListener('click', function() {
    this.classList.toggle('active');
    if (this.classList.contains('active')) state.layers.ais.addTo(state.map);
    else state.map.removeLayer(state.layers.ais);
  });

  document.getElementById('layer-toggle-drift')?.addEventListener('click', function() {
    this.classList.toggle('active');
    if (this.classList.contains('active')) state.layers.drift.addTo(state.map);
    else state.map.removeLayer(state.layers.drift);
  });

  // Maritime Corridor toggle (includes waypoints layer)
  document.getElementById('layer-toggle-corridor')?.addEventListener('click', function() {
    this.classList.toggle('active');
    if (this.classList.contains('active')) {
      state.layers.corridor.addTo(state.map);
      state.layers.waypoints.addTo(state.map);
    } else {
      state.map.removeLayer(state.layers.corridor);
      state.map.removeLayer(state.layers.waypoints);
    }
  });

  // POI Features toggle (polygon zone, cyan line, labels)
  document.getElementById('layer-toggle-poi')?.addEventListener('click', function() {
    this.classList.toggle('active');
    if (this.classList.contains('active')) state.layers.poiFeatures.addTo(state.map);
    else state.map.removeLayer(state.layers.poiFeatures);
  });

  // Live Vessels toggle
  document.getElementById('layer-toggle-live-vessels')?.addEventListener('click', function() {
    this.classList.toggle('active');
    if (this.classList.contains('active')) {
      state.layers.liveVessels.addTo(state.map);
      startLiveVesselFeed();
    } else {
      state.map.removeLayer(state.layers.liveVessels);
      if (state.liveVesselInterval) {
        clearInterval(state.liveVesselInterval);
        state.liveVesselInterval = null;
      }
    }
  });

  // Quick Spill Alert — wire the bell, panel, toasts and map markers.
  if (window.SpillGuardAlerts) {
    window.SpillGuardAlerts.init({ apiBase: window.SPILLGUARD_API_BASE || '' });
  }

  // Region Selector
  document.getElementById('region-selector')?.addEventListener('change', async (e) => {
    const val = e.target.value;
    const reg = SPILLGUARD_DATA.regions[val];
    if (!reg || !validateRegionConfig(val, reg)) {
      console.warn(`Unknown or invalid region selected: ${val}`);
      return;
    }
    state.currentRegion = val;
    syncRegionHeader(val);
    const requestId = ++state.regionRequestId;
    state.analysisData.drift = null;
    state.analysisData.originZone = null;
    updateRegionUI(val);

    try {
      const resp = await fetch(apiUrl(`/api/regions/${val}`), { cache: 'no-store' });
      if (resp.ok && requestId === state.regionRequestId && state.currentRegion === val) {
        const regionData = await resp.json();
        if (Array.isArray(regionData.spills)) SPILLGUARD_DATA.regionSpills[val] = regionData.spills;
        if (Array.isArray(regionData.vessels)) SPILLGUARD_DATA.regionVessels[val] = regionData.vessels;
        updateRegionUI(val);
      }
    } catch (err) {
      console.warn('Region fetch failed, using local demo data.', err);
    }
  });

  // Haversine distance (km)
  function haversineKm([lat1, lon1], [lat2, lon2]) {
    const toRad = v => v * Math.PI / 180;
    const R = 6371; // km
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon/2) * Math.sin(dLon/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return R * c;
  }

  function getEntitiesForRegion(regionKey, radiusKm = 200) {
    // Prefer explicit per-region datasets if provided in data.js
    if (SPILLGUARD_DATA.regionSpills && SPILLGUARD_DATA.regionSpills[regionKey]) {
      const spills = SPILLGUARD_DATA.regionSpills[regionKey] || [];
      const vessels = SPILLGUARD_DATA.regionVessels && SPILLGUARD_DATA.regionVessels[regionKey]
        ? SPILLGUARD_DATA.regionVessels[regionKey].map(v => ({ ...v, coords: [v.coords ? v.coords[0] : v.lat, v.coords ? v.coords[1] : v.lon] }))
        : [];
      return { spills, vessels };
    }

    const reg = SPILLGUARD_DATA.regions[regionKey];
    if (!reg) return { spills: SPILLGUARD_DATA.spills, vessels: SPILLGUARD_DATA.vessels };
    const center = reg.center;
    const spills = (SPILLGUARD_DATA.spills || []).filter(s => {
      if (!s.coords) return false;
      const d = haversineKm(center, s.coords);
      return d <= radiusKm;
    });
    const vessels = (SPILLGUARD_DATA.vessels || []).filter(v => {
      if (!v.coords) return false;
      const d = haversineKm(center, v.coords);
      return d <= radiusKm;
    });
    return { spills, vessels };
  }

  function validateRegionConfig(regionKey, region) {
    const [lat, lon] = region.center || [];
    const validCoordinate = Number.isFinite(lat) && Number.isFinite(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
    const validOverlays = region.overlays && Array.isArray(region.overlays.corridor) && Array.isArray(region.overlays.sarVector);
    if (!validCoordinate || !validOverlays) {
      console.warn(`Invalid geographic configuration for region: ${regionKey}`);
      return false;
    }
    return true;
  }

  function setTextIfExists(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value ?? '';
  }

  function syncRegionHeader(regionKey) {
    const region = SPILLGUARD_DATA.regions[regionKey];
    const locationEl = document.getElementById('priority-location-txt');
    if (region && locationEl) {
      locationEl.textContent = region.name;
    }
  }

  function applyIncidentCard(primary, regionKey) {
    const region = SPILLGUARD_DATA.regions[regionKey];
    const incidentIdEl = document.getElementById('priority-incident-id');
    const locationEl = document.getElementById('priority-location-txt');
    const miniVals = document.querySelectorAll('.priority-mini-val');

    if (!primary) {
      if (incidentIdEl) incidentIdEl.textContent = 'No incidents';
      if (locationEl) locationEl.textContent = region ? region.name : 'No active region';
      if (miniVals) miniVals.forEach((el, idx) => { el.textContent = idx === 0 ? '0 km²' : '—'; });
      return;
    }

    if (incidentIdEl) incidentIdEl.textContent = (primary.id ? `#${primary.id}` : 'Incident') + (primary.title ? `: ${primary.title}` : '');
    if (locationEl) {
      locationEl.textContent = region && region.name ? region.name : (primary.locationDesc || primary.title || 'Selected region');
    }

    if (miniVals && miniVals.length >= 4) {
      miniVals[0].textContent = primary.areaKm2 ? `${primary.areaKm2} km²` : '—';
      miniVals[1].textContent = primary.volumeBbls ? `${Number(primary.volumeBbls).toLocaleString()} bbls` : '—';
      miniVals[2].textContent = primary.confidence ? `${primary.confidence}%` : '—';
      miniVals[3].textContent = primary.primarySuspect ? primary.primarySuspect.name : '—';
    }
  }

  function updateRegionUI(regionKey) {
    const region = SPILLGUARD_DATA.regions[regionKey];
    if (!region || !validateRegionConfig(regionKey, region)) return;
    const { spills, vessels } = getEntitiesForRegion(regionKey);
    const activeSpills = Array.isArray(spills) ? spills : [];
    const activeVessels = Array.isArray(vessels) ? vessels : [];

    // Preserve the canonical vessel/spill catalog for the table and filter UI.
    // Region updates should only affect the live map and cards, not the master table data.
    if (!state.masterVessels.length && Array.isArray(SPILLGUARD_DATA.vessels)) {
      state.masterVessels = [...SPILLGUARD_DATA.vessels];
    }
    if (!state.masterSpills.length && Array.isArray(SPILLGUARD_DATA.spills)) {
      state.masterSpills = [...SPILLGUARD_DATA.spills];
    }

    syncRegionHeader(regionKey);

    if (state.layers.liveVessels) state.layers.liveVessels.clearLayers();
    const primary = activeSpills[0];

    applyIncidentCard(primary, regionKey);

    // Update detail drawer if open or select primary
    if (primary) {
      state.selectedSpill = primary;
      const inspectButton = document.getElementById('btn-inspect-priority');
      if (inspectButton) {
        inspectButton.dataset.spillId = primary.id || '';
        inspectButton.dataset.region = regionKey;
      }
      renderSpillAnalysis(primary);
      setTextIfExists('drawer-spill-id', '#' + primary.id);
      setTextIfExists('drawer-spill-title', primary.title || 'Selected spill');
      setTextIfExists('drawer-sensor-tag', primary.sensor || '');
      setTextIfExists('drawer-spec-area', primary.areaKm2 ? primary.areaKm2 + ' km²' : '');
      setTextIfExists('drawer-spec-volume', primary.volumeBbls ? primary.volumeBbls.toLocaleString() + ' bbls' : '');
      setTextIfExists('drawer-spec-conf', primary.confidence ? primary.confidence + '%' : '');
      setTextIfExists('drawer-spec-type', primary.slickType || primary.slick_type || 'Hydrocarbon oil residue');
      setTextIfExists('drawer-suspect-name', primary.primarySuspect ? `${primary.primarySuspect.name} (${primary.primarySuspect.confidence}% Match)` : '');
    } else {
      setTextIfExists('drawer-spill-id', 'No spill');
      setTextIfExists('drawer-spill-title', 'No active spill');
      setTextIfExists('drawer-sensor-tag', '');
      setTextIfExists('drawer-spec-area', '');
      setTextIfExists('drawer-spec-volume', '');
      setTextIfExists('drawer-spec-conf', '');
      setTextIfExists('drawer-spec-type', 'Hydrocarbon oil residue');
      setTextIfExists('drawer-suspect-name', '');
    }

    // Re-render map with region-scoped entities only.
    if (state.map) {
      renderMapData(activeSpills, activeVessels);
      renderMaritimeCorridor();
      if (region.bounds) state.map.fitBounds(region.bounds, { padding: [24, 24], maxZoom: region.zoom });
      else state.map.flyTo(region.center, region.zoom, { duration: 1.2 });
      if (state.layers.liveVessels && state.map.hasLayer(state.layers.liveVessels)) fetchLiveVesselPositions();
    }
  }

  // Detail Drawer Logic
  const detailDrawer = document.getElementById('map-detail-drawer');
  const btnCloseDrawer = document.getElementById('btn-close-drawer');
  const btnDrawerInvestigate = document.getElementById('btn-drawer-investigate');
  const btnInspectPriority = document.getElementById('btn-inspect-priority');

  const EARTH_RADIUS_KM = 6371.0088;

  function geoJsonRingForSpill(spill) {
    const geometry = spill?.geojson?.geometry || spill?.geometry || (spill?.type === 'Feature' ? spill.geometry : null);
    if (geometry?.type === 'Polygon' && Array.isArray(geometry.coordinates?.[0])) {
      return geometry.coordinates[0].map(([lon, lat]) => [lon, lat]);
    }

    const polygon = spill?.slickPolygon;
    if (!Array.isArray(polygon)) return null;
    return polygon.map(point => {
      if (!Array.isArray(point) || point.length < 2) return null;
      const [first, second] = point;
      // Bundled fixtures use [lat, lon]; GeoJSON uses [lon, lat].
      return Math.abs(first) > 90 || Math.abs(second) <= 90
        ? [first, second]
        : [second, first];
    });
  }

  function projectGeoJsonRing(ring, latitude) {
    const latitudeRad = latitude * Math.PI / 180;
    return ring.map(([lon, lat]) => ({
      x: EARTH_RADIUS_KM * lon * Math.PI / 180 * Math.cos(latitudeRad),
      y: EARTH_RADIUS_KM * lat * Math.PI / 180
    }));
  }

  function haversinePoints(a, b) {
    const toRad = value => value * Math.PI / 180;
    const dLat = toRad(b[1] - a[1]);
    const dLon = toRad(b[0] - a[0]);
    const latA = toRad(a[1]);
    const latB = toRad(b[1]);
    const value = Math.sin(dLat / 2) ** 2 + Math.cos(latA) * Math.cos(latB) * Math.sin(dLon / 2) ** 2;
    return 2 * EARTH_RADIUS_KM * Math.atan2(Math.sqrt(value), Math.sqrt(1 - value));
  }

  function confidenceLabel(confidence) {
    if (!Number.isFinite(confidence)) return 'Unrated';
    if (confidence >= 90) return 'Very high confidence';
    if (confidence >= 75) return 'High confidence';
    if (confidence >= 50) return 'Moderate confidence';
    return 'Low confidence';
  }

  function analyzeSpill(spill) {
    const fallback = spill || SPILLGUARD_DATA.spills?.[0];
    const fallbackCoords = fallback?.coords || SPILLGUARD_DATA.regions[state.currentRegion]?.center || [2.3812, 101.9124];
    const ring = geoJsonRingForSpill(fallback) || [
      [fallbackCoords[1] - 0.02, fallbackCoords[0] - 0.02],
      [fallbackCoords[1] + 0.02, fallbackCoords[0] - 0.02],
      [fallbackCoords[1] + 0.02, fallbackCoords[0] + 0.02],
      [fallbackCoords[1] - 0.02, fallbackCoords[0] + 0.02]
    ];

    const uniqueRing = ring.filter(point => point && point.every(Number.isFinite));
    if (uniqueRing.length < 3) return { valid: false, message: 'Invalid spill polygon: at least three coordinate pairs are required.' };
    const closedRing = uniqueRing.length > 1 && uniqueRing[0][0] === uniqueRing.at(-1)[0] && uniqueRing[0][1] === uniqueRing.at(-1)[1]
      ? uniqueRing.slice(0, -1)
      : uniqueRing;
    if (closedRing.length < 3) return { valid: false, message: 'Invalid spill polygon: the ring has too few unique points.' };

    const meanLat = closedRing.reduce((sum, point) => sum + point[1], 0) / closedRing.length;
    const projected = projectGeoJsonRing(closedRing, meanLat);
    let twiceArea = 0;
    let centroidX = 0;
    let centroidY = 0;
    for (let index = 0; index < projected.length; index += 1) {
      const current = projected[index];
      const next = projected[(index + 1) % projected.length];
      const cross = current.x * next.y - next.x * current.y;
      twiceArea += cross;
      centroidX += (current.x + next.x) * cross;
      centroidY += (current.y + next.y) * cross;
    }

    const areaKm2 = Math.abs(twiceArea / 2);
    if (!Number.isFinite(areaKm2) || areaKm2 < 0.0001) {
      return { valid: false, message: 'Spill polygon is too small to analyze reliably.' };
    }

    const signedArea = twiceArea / 2;
    const center = signedArea ? { x: centroidX / (6 * signedArea), y: centroidY / (6 * signedArea) } : projected[0];
    const centroid = [center.x / (EARTH_RADIUS_KM * Math.PI / 180 * Math.cos(meanLat * Math.PI / 180)), center.y / (EARTH_RADIUS_KM * Math.PI / 180)];
    const lons = closedRing.map(point => point[0]);
    const lats = closedRing.map(point => point[1]);
    const bbox = { west: Math.min(...lons), south: Math.min(...lats), east: Math.max(...lons), north: Math.max(...lats) };
    const perimeterKm = closedRing.reduce((sum, point, index) => sum + haversinePoints(point, closedRing[(index + 1) % closedRing.length]), 0);

    const meanX = projected.reduce((sum, point) => sum + point.x, 0) / projected.length;
    const meanY = projected.reduce((sum, point) => sum + point.y, 0) / projected.length;
    let xx = 0; let xy = 0; let yy = 0;
    projected.forEach(point => { xx += (point.x - meanX) ** 2; xy += (point.x - meanX) * (point.y - meanY); yy += (point.y - meanY) ** 2; });
    const angle = 0.5 * Math.atan2(2 * xy, xx - yy);
    const axis = { x: Math.cos(angle), y: Math.sin(angle) };
    const crossAxis = { x: -axis.y, y: axis.x };
    const primary = projected.map(point => point.x * axis.x + point.y * axis.y);
    const secondary = projected.map(point => point.x * crossAxis.x + point.y * crossAxis.y);
    const lengthKm = Math.max(...primary) - Math.min(...primary);
    const widthKm = Math.max(...secondary) - Math.min(...secondary);
    const orientationDeg = (Math.atan2(axis.x, axis.y) * 180 / Math.PI + 360) % 180;

    const region = SPILLGUARD_DATA.regions[state.currentRegion];
    const sensitiveRing = region?.overlays?.priorityZone;
    let sensitiveZone = 'No demo sensitive zone configured';
    let sensitiveDistanceKm = null;
    if (Array.isArray(sensitiveRing) && sensitiveRing.length >= 3) {
      sensitiveDistanceKm = Math.min(...closedRing.flatMap(spillPoint => sensitiveRing.map(zonePoint => haversineKm(spillPoint, zonePoint))));
      sensitiveZone = 'Priority monitoring zone';
    }

    return {
      valid: true,
      spill: fallback,
      geojson: { type: 'Feature', properties: { id: fallback?.id || 'demo-spill', title: fallback?.title || 'Demo spill' }, geometry: { type: 'Polygon', coordinates: [[...closedRing, closedRing[0]]] } },
      areaKm2,
      perimeterKm,
      centroid: { lat: centroid[1], lon: centroid[0] },
      bbox,
      lengthKm,
      widthKm,
      orientationDeg,
      sensitiveZone,
      sensitiveDistanceKm,
      confidence: Number(fallback?.confidence)
    };
  }

  function formatMetric(value, suffix = '') {
    return Number.isFinite(value) ? `${value.toFixed(2)}${suffix}` : '—';
  }

  function renderSpillAnalysis(spill) {
    const status = document.getElementById('spill-analysis-status');
    const metrics = document.getElementById('spill-analysis-metrics');
    const badge = document.getElementById('spill-analysis-confidence');
    const analysis = analyzeSpill(spill);
    state.analysisData.spillAnalysis = analysis;
    if (!status || !metrics || !badge) return;
    if (!analysis.valid) {
      status.textContent = analysis.message;
      metrics.innerHTML = '';
      badge.textContent = 'Invalid geometry';
      return;
    }
    badge.textContent = confidenceLabel(analysis.confidence);
    status.textContent = 'Computed from the selected SpillEvent polygon.';
    metrics.innerHTML = [
      ['Area', formatMetric(analysis.areaKm2, ' km²')],
      ['Perimeter', formatMetric(analysis.perimeterKm, ' km')],
      ['Centroid', `${analysis.centroid.lat.toFixed(5)}°, ${analysis.centroid.lon.toFixed(5)}°`],
      ['Bounding box', `${analysis.bbox.south.toFixed(3)}° to ${analysis.bbox.north.toFixed(3)}° / ${analysis.bbox.west.toFixed(3)}° to ${analysis.bbox.east.toFixed(3)}°`],
      ['Approx. length × width', `${formatMetric(analysis.lengthKm, ' km')} × ${formatMetric(analysis.widthKm, ' km')}`],
      ['Main orientation', `${analysis.orientationDeg.toFixed(1)}°`],
      [`Nearest ${analysis.sensitiveZone}`, analysis.sensitiveDistanceKm === null ? 'Unavailable' : formatMetric(analysis.sensitiveDistanceKm, ' km')]
    ].map(([label, value]) => `<tr><td>${label}</td><td>${value}</td></tr>`).join('');
  }

  function openSpillDrawer(spill) {
    state.selectedSpill = spill;
    document.getElementById('drawer-spill-id').textContent = '#' + spill.id;
    document.getElementById('drawer-spill-title').textContent = spill.title;
    document.getElementById('drawer-sensor-tag').textContent = spill.sensor;
    document.getElementById('drawer-spec-area').textContent = spill.areaKm2 + ' km²';
    document.getElementById('drawer-spec-volume').textContent = spill.volumeBbls.toLocaleString() + ' bbls';
    document.getElementById('drawer-spec-conf').textContent = spill.confidence + '%';
    document.getElementById('drawer-spec-type').textContent = spill.slickType || spill.slick_type || 'Hydrocarbon oil residue';
    document.getElementById('drawer-suspect-name').textContent = `${spill.primarySuspect.name} (${spill.primarySuspect.confidence}% Match)`;
    renderSpillAnalysis(spill);
    populateDriftInputs(spill);
    
    detailDrawer?.classList.add('drawer-open');
  }

  btnCloseDrawer?.addEventListener('click', () => {
    detailDrawer?.classList.remove('drawer-open');
  });

  btnDrawerInvestigate?.addEventListener('click', () => {
    navigateTo('screen-investigation');
  });

  btnInspectPriority?.addEventListener('click', () => {
    const activeRegionKey = btnInspectPriority.dataset.region || state.currentRegion || 'malacca';
    const regionalSpills = SPILLGUARD_DATA.regionSpills?.[activeRegionKey] || SPILLGUARD_DATA.spills || [];
    const preferredSpillId = btnInspectPriority.dataset.spillId || state.selectedSpill?.id;
    const activeSpill = regionalSpills.find(spill => spill.id === preferredSpillId)
      || regionalSpills[0]
      || state.selectedSpill
      || SPILLGUARD_DATA.spills[0];

    if (!activeSpill) return;

    state.selectedSpill = activeSpill;
    openSpillDrawer(activeSpill);
    if (state.map) {
      state.map.flyTo(activeSpill.coords, 10, { duration: 0.8 });
    }
  });

  // Alerts sidebar button: open critical slick alert queue (demo: open first critical spill)
  document.getElementById('side-btn-alerts')?.addEventListener('click', () => {
    // Ensure the app shell (dashboard) is visible first
    navigateTo('screen-dashboard');

    const critical = (SPILLGUARD_DATA.spills || []).find(s => s.severity === 'critical');

    // Wait briefly for dashboard/map to become visible and for Leaflet to initialize
    setTimeout(() => {
      if (critical) {
        state.selectedSpill = critical;
        openSpillDrawer(critical);
        if (state.map) state.map.flyTo(critical.coords, 10, { duration: 0.8 });
        // mark sidebar button active
        document.querySelectorAll('.sidebar-btn').forEach(b => b.classList.remove('active'));
        document.getElementById('side-btn-alerts')?.classList.add('active');
      } else {
        // no critical spills: open drawer with message
        if (detailDrawer) {
          detailDrawer.classList.add('drawer-open');
          document.getElementById('drawer-spill-id').textContent = 'No Active Alerts';
          document.getElementById('drawer-spill-title').textContent = 'Critical Slick Queue';
          const db = document.querySelector('.drawer-body');
          if (db) db.innerHTML = '<div style="color:var(--text-muted);">No critical slicks at this time.</div>';
        }
      }
    }, 300);
  });

  // SAR-AIS Correlation UI handlers
  document.getElementById('btn-run-correlation')?.addEventListener('click', async () => {
    const statusEl = document.getElementById('correlation-status');
    const tbody = document.querySelector('#correlation-results tbody');
    if (statusEl) statusEl.textContent = 'Running...';
    if (tbody) tbody.innerHTML = '';

    const primary = SPILLGUARD_DATA.spills[0];
    const payload = {
      sar_time: primary.detectedAt,
      sar_lat: primary.coords[0],
      sar_lon: primary.coords[1],
      sar_heading: null,
      sar_length_m: null,
      ais_records: (SPILLGUARD_DATA.vessels || []).map(v => ({
        mmsi: v.mmsi,
        vessel_name: v.name,
        lat: v.coords[0],
        lon: v.coords[1],
        timestamp: v.lastAisPing || new Date().toISOString(),
        speed_knots: v.speed,
        heading: v.heading,
        vessel_type: v.type,
        length_m: v.length ? parseFloat(String(v.length).replace(/[^0-9.]/g, '')) || null : null
      }))
    };

    try {
      const resp = await fetch(apiUrl('/api/sar-ais/correlate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await resp.json();
      if (data && data.results) {
        data.results.forEach(r => {
          const tr = document.createElement('tr');
          tr.innerHTML = `<td style="padding:6px">${r.mmsi}</td><td style="padding:6px; text-align:right">${r.score}</td><td style="padding:6px; text-align:right">${r.distance_km}</td>`;
          tbody.appendChild(tr);
        });
        if (statusEl) statusEl.textContent = data.status === 'matched' ? 'Matched' : 'No match';
      } else {
        if (statusEl) statusEl.textContent = 'No AIS data';
      }
    } catch (err) {
      console.error(err);
      if (statusEl) statusEl.textContent = 'Error';
    }
  });

  document.getElementById('btn-demo-correlation')?.addEventListener('click', () => {
    // quick demo: populate demo AIS positions slightly offset and run
    const primary = SPILLGUARD_DATA.spills[0];
    SPILLGUARD_DATA.vessels.forEach((v, i) => {
      v.coords = [primary.coords[0] + (i + 1) * 0.01, primary.coords[1] - (i + 1) * 0.01];
    });
    document.getElementById('btn-run-correlation')?.click();
  });

  // Bottom Timeline Scrubber
  const slider = document.getElementById('timeline-slider');
  const scrubberTimestamp = document.getElementById('scrubber-timestamp');
  const btnScrubPlay = document.getElementById('btn-scrub-play');

  const timelineLabels = [
    "T-24h: 2026-09-15 04:12 UTC (Clear)",
    "T-18h: 2026-09-15 10:12 UTC (Pre-Discharge)",
    "T-12h: 2026-09-15 16:12 UTC (ICEYE Pass)",
    "T-6h: 2026-09-15 22:12 UTC (DISCHARGE CENTROID)",
    "LIVE: 2026-09-16 04:12 UTC (Sentinel-1A SAR)"
  ];

  slider?.addEventListener('input', (e) => {
    const val = parseInt(e.target.value, 10);
    const labelIdx = Math.min(Math.floor((val / 100) * timelineLabels.length), timelineLabels.length - 1);
    if (scrubberTimestamp) {
      scrubberTimestamp.textContent = timelineLabels[labelIdx];
    }
  });

  btnScrubPlay?.addEventListener('click', () => {
    state.isPlayingScrubber = !state.isPlayingScrubber;
    const icon = document.getElementById('play-icon');
    if (state.isPlayingScrubber) {
      icon.innerHTML = '<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>';
      state.scrubberInterval = setInterval(() => {
        let cur = parseInt(slider.value, 10);
        cur += 2;
        if (cur > 100) cur = 0;
        slider.value = cur;
        slider.dispatchEvent(new Event('input'));
      }, 100);
    } else {
      icon.innerHTML = '<polygon points="5 3 19 12 5 21 5 3"/>';
      clearInterval(state.scrubberInterval);
    }
  });


  // =========================================================================
  // SCREEN 5: SPILL INVESTIGATION & DRIFT SIMULATION ENGINE
  // =========================================================================
  document.getElementById('btn-back-to-dashboard')?.addEventListener('click', () => {
    navigateTo('screen-dashboard');
  });

  function populateDriftInputs(spill = state.selectedSpill || SPILLGUARD_DATA.spills?.[0]) {
    if (!spill) return;
    const latInput = document.getElementById('drift-spill-lat');
    const lonInput = document.getElementById('drift-spill-lon');
    const timeInput = document.getElementById('drift-sar-time');
    if (latInput) latInput.value = spill.coords?.[0] ?? '';
    if (lonInput) lonInput.value = spill.coords?.[1] ?? '';
    if (timeInput && !timeInput.value) timeInput.value = new Date().toISOString().slice(0, 16);
  }

  function driftInputs() {
    const value = id => document.getElementById(id)?.value;
    const sarTime = value('drift-sar-time');
    return {
      spill_lat: Number(value('drift-spill-lat')),
      spill_lon: Number(value('drift-spill-lon')),
      sar_time: sarTime ? `${sarTime}:00Z` : null,
      current_speed_mps: Number(value('drift-current-speed')),
      current_direction_degrees: Number(value('drift-current-direction')),
      wind_speed_mps: Number(value('drift-wind-speed') || 0),
      wind_direction_degrees: Number(value('drift-wind-direction') || 0),
      hours: Number(value('drift-hours')),
      uncertainty_km: Number(value('drift-uncertainty'))
    };
  }

  function addDriftArrows(coordinates, color) {
    if (!state.map || coordinates.length < 2) return;
    const latLngs = coordinates.map(([lon, lat]) => [lat, lon]);
    L.polyline(latLngs, { color, weight: 3, opacity: 0.95, dashArray: color === '#F59E0B' ? '8 6' : null }).addTo(state.layers.drift);
    if (typeof L.polylineDecorator === 'function') {
      L.polylineDecorator(latLngs, {
        patterns: [{ offset: '12%', repeat: '48px', symbol: L.Symbol.arrowHead({
          pixelSize: 10, polygon: false, pathOptions: { color, fill: false, stroke: true, weight: 2 }
        }) }]
      }).addTo(state.layers.drift);
    }
  }

  function renderDriftForecast(data) {
    if (!state.map || !state.layers.drift) return;
    state.layers.drift.clearLayers();
    if (!data) return;
    addDriftArrows(data.forward_path?.geometry?.coordinates || [], '#2563EB');
    addDriftArrows(data.backward_path?.geometry?.coordinates || [], '#F59E0B');
    if (data.origin_zone) {
      L.geoJSON(data.origin_zone, {
        style: { color: '#F59E0B', weight: 2, fillColor: '#F59E0B', fillOpacity: 0.2, dashArray: '5 4' }
      }).bindPopup('Possible source area: uncertainty zone, not an exact source point.').addTo(state.layers.drift);
    }
    (data.hourly_locations || []).filter(item => [6, 12, 24, 48].includes(item.hour)).forEach(item => {
      const point = item.forward;
      L.circleMarker([point.lat, point.lon], { radius: 5, color: '#60A5FA', fillColor: '#2563EB', fillOpacity: 0.9, weight: 1 })
        .bindTooltip(`Forward ${item.hour}h`, { direction: 'top' }).addTo(state.layers.drift);
    });
  }

  async function requestDriftForecast() {
    const status = document.getElementById('drift-control-status');
    const summary = document.getElementById('drift-result-summary');
    const payload = driftInputs();
    if (!Number.isFinite(payload.spill_lat) || !Number.isFinite(payload.spill_lon) || !Number.isFinite(payload.current_speed_mps) || !Number.isFinite(payload.uncertainty_km)) {
      if (summary) summary.textContent = 'Enter valid coordinates, current speed, and uncertainty.';
      return;
    }
    if (status) status.textContent = 'RUNNING';
    try {
      const response = await fetch(apiUrl('/api/drift'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      if (!response.ok) throw new Error(`API returned ${response.status}`);
      const data = await response.json();
      state.analysisData.drift = data;
      state.analysisData.originZone = data.origin_zone;
      renderDriftForecast(data);
      const origin = data.backward_source_location;
      if (summary) summary.textContent = `Source zone centered near ${origin.lat.toFixed(4)}°, ${origin.lon.toFixed(4)}° (${payload.uncertainty_km.toFixed(1)} km radius). ${data.warning}`;
      document.getElementById('drift-hourly-list').innerHTML = (data.hourly_locations || []).filter(item => [6, 12, 24, 48].includes(item.hour)).map(item => `<div class="drift-hourly-row"><span>${item.hour}h forecast</span><span>${item.forward.lat.toFixed(3)}°, ${item.forward.lon.toFixed(3)}°</span></div>`).join('');
      if (status) status.textContent = 'COMPLETE';
    } catch (error) {
      if (status) status.textContent = 'OFFLINE';
      if (summary) summary.textContent = `Drift forecast failed: ${error.message}`;
    }
  }

  document.getElementById('btn-predict-forward-drift')?.addEventListener('click', requestDriftForecast);
  document.getElementById('btn-demo-ocean-conditions')?.addEventListener('click', () => {
    populateDriftInputs();
    document.getElementById('drift-current-speed').value = '0.4';
    document.getElementById('drift-current-direction').value = '138';
    document.getElementById('drift-wind-speed').value = '7.3';
    document.getElementById('drift-wind-direction').value = '310';
    document.getElementById('drift-hours').value = '12';
    document.getElementById('drift-uncertainty').value = '5';
    requestDriftForecast();
  });
  populateDriftInputs();

  let driftParticles = [];
  function initDriftSimulation() {
    const canvas = document.getElementById('drift-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const container = document.getElementById('drift-sim-container');

    // Resize canvas
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;

    // Create 70 Lagrangian particles representing oil droplets drifting backwards
    driftParticles = [];
    const originX = canvas.width * 0.35;
    const originY = canvas.height * 0.35;
    const currentX = canvas.width * 0.72;
    const currentY = canvas.height * 0.70;

    for (let i = 0; i < 75; i++) {
      driftParticles.push({
        progress: Math.random(),
        speed: 0.003 + Math.random() * 0.003,
        spreadX: (Math.random() - 0.5) * 45,
        spreadY: (Math.random() - 0.5) * 45,
        size: 2 + Math.random() * 2.5
      });
    }

    function renderDriftFrame() {
      if (state.currentScreen !== 'screen-investigation') {
        cancelAnimationFrame(state.driftAnimationId);
        return;
      }

      ctx.fillStyle = '#040912';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // 1. Grid lines
      ctx.strokeStyle = 'rgba(0, 212, 255, 0.06)';
      ctx.lineWidth = 1;
      for (let x = 0; x < canvas.width; x += 40) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, canvas.height);
        ctx.stroke();
      }
      for (let y = 0; y < canvas.height; y += 40) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvas.width, y);
        ctx.stroke();
      }

      // 2. MT Ocean Vanguard AIS Track Line (Cyan)
      ctx.strokeStyle = '#00D4FF';
      ctx.lineWidth = 2.5;
      ctx.shadowColor = 'rgba(0, 212, 255, 0.5)';
      ctx.shadowBlur = 10;
      ctx.beginPath();
      ctx.moveTo(canvas.width * 0.15, canvas.height * 0.20);
      ctx.lineTo(canvas.width * 0.35, canvas.height * 0.35); // Intercept Point
      ctx.lineTo(canvas.width * 0.60, canvas.height * 0.55);
      ctx.lineTo(canvas.width * 0.85, canvas.height * 0.78);
      ctx.stroke();
      ctx.shadowBlur = 0;

      // 3. AIS Blackout Zone (dashed red segment along the ship's course)
      ctx.strokeStyle = '#FF4438';
      ctx.lineWidth = 3;
      ctx.setLineDash([6, 6]);
      ctx.shadowColor = 'rgba(255, 68, 56, 0.8)';
      ctx.shadowBlur = 12;
      ctx.beginPath();
      ctx.moveTo(canvas.width * 0.25, canvas.height * 0.275);
      ctx.lineTo(canvas.width * 0.45, canvas.height * 0.43);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.shadowBlur = 0;

      // AIS Blackout Label
      ctx.fillStyle = '#FF4438';
      ctx.font = '11px JetBrains Mono';
      ctx.fillText('AIS SILENT: 3h 48m (Blackout Zone)', canvas.width * 0.26, canvas.height * 0.25);

      // 4. Backward Drift Trajectory (Amber dashed curve)
      ctx.strokeStyle = '#FFB020';
      ctx.lineWidth = 2;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(currentX, currentY);
      ctx.quadraticCurveTo(canvas.width * 0.55, canvas.height * 0.58, originX, originY);
      ctx.stroke();
      ctx.setLineDash([]);

      // 5. Draw Animated Lagrangian Particles
      driftParticles.forEach(p => {
        p.progress += p.speed;
        if (p.progress > 1) p.progress = 0;

        // Interpolate along the drift trajectory (from current slick position backwards to origin)
        const t = p.progress;
        const px = (1 - t) * currentX + t * originX + p.spreadX * (1 - t);
        const py = (1 - t) * currentY + t * originY + p.spreadY * (1 - t);

        ctx.fillStyle = `rgba(255,176,32, ${0.85 - t * 0.5})`;
        ctx.beginPath();
        ctx.arc(px, py, p.size, 0, Math.PI * 2);
        ctx.fill();
      });

      // 6. Current Slick Position (Red Solid Blob)
      ctx.fillStyle = 'rgba(255, 68, 56, 0.45)';
      ctx.strokeStyle = '#FF4438';
      ctx.lineWidth = 2;
      ctx.shadowColor = 'rgba(255, 68, 56, 0.6)';
      ctx.shadowBlur = 16;
      ctx.beginPath();
      ctx.ellipse(currentX, currentY, 55, 35, Math.PI / 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.shadowBlur = 0;

      ctx.fillStyle = '#FFF';
      ctx.font = '12px Space Grotesk';
      ctx.fillText('SLICK: Sentinel-1A SAR (45.2 km²)', currentX - 90, currentY + 50);

      // 7. Intercept Point (Intersection of Vessel Track & Reverse Drift Origin)
      ctx.strokeStyle = '#FF4438';
      ctx.fillStyle = 'rgba(255, 68, 56, 0.2)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(originX, originY, 18, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = '#FF4438';
      ctx.beginPath();
      ctx.arc(originX, originY, 5, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = '#FFF';
      ctx.font = '12px Space Grotesk';
      ctx.fillText('DISCHARGE INTERCEPT POINT', originX - 70, originY - 26);
      ctx.fillStyle = 'var(--cyan-primary)';
      ctx.font = '10px JetBrains Mono';
      ctx.fillText('02°26\'42"N 101°51\'18"E @ 03:14 UTC', originX - 70, originY - 12);

      state.driftAnimationId = requestAnimationFrame(renderDriftFrame);
    }

    renderDriftFrame();
  }

  document.getElementById('btn-replay-drift')?.addEventListener('click', () => {
    driftParticles.forEach(p => p.progress = 0);
  });

  // Modal Controls
  const dossierModal = document.getElementById('dossier-modal');
  document.getElementById('btn-open-dossier-modal')?.addEventListener('click', () => {
    dossierModal?.classList.add('modal-active');
  });

  document.getElementById('btn-close-modal')?.addEventListener('click', () => {
    dossierModal?.classList.remove('modal-active');
  });

  document.getElementById('btn-cancel-modal')?.addEventListener('click', () => {
    dossierModal?.classList.remove('modal-active');
  });

  document.getElementById('btn-download-pdf')?.addEventListener('click', () => {
    alert("Official UNCLOS / MARPOL Annex I Forensic Dossier (SHA-256 Verified) downloaded.");
    dossierModal?.classList.remove('modal-active');
  });

  // Feedback modal and form handling
  const feedbackModal = document.getElementById('feedback-modal');
  const feedbackForm = document.getElementById('feedback-form');
  const feedbackStatus = document.getElementById('feedback-status');
  const feedbackRatingInput = document.getElementById('feedback-rating');
  const feedbackStars = document.querySelectorAll('.feedback-star-btn');

  function openFeedbackModal() {
    feedbackModal?.classList.add('modal-active');
    feedbackStatus?.classList.remove('success', 'error');
    feedbackStatus && (feedbackStatus.textContent = '');
  }

  function closeFeedbackModal() {
    feedbackModal?.classList.remove('modal-active');
    feedbackStatus?.classList.remove('success', 'error');
    feedbackStatus && (feedbackStatus.textContent = '');
    feedbackForm?.reset();
    const currentRating = Number(feedbackRatingInput?.value || 3);
    feedbackStars.forEach(star => {
      const value = Number(star.dataset.value);
      star.classList.toggle('active', value <= currentRating);
    });
  }

  document.getElementById('nav-feedback-btn')?.addEventListener('click', openFeedbackModal);
  document.querySelectorAll('[data-close-feedback]').forEach(btn => {
    btn.addEventListener('click', closeFeedbackModal);
  });

  feedbackStars.forEach(star => {
    star.addEventListener('click', () => {
      const selected = Number(star.dataset.value || 1);
      feedbackRatingInput.value = selected;
      feedbackStars.forEach(item => {
        item.classList.toggle('active', Number(item.dataset.value) <= selected);
      });
    });
  });

  feedbackForm?.addEventListener('submit', async (event) => {
    event.preventDefault();

    const formData = new FormData(feedbackForm);
    const message = String(formData.get('message') || '').trim();
    const rating = Number(formData.get('rating') || 0);
    const payload = {
      name: String(formData.get('name') || '').trim() || null,
      email: String(formData.get('email') || '').trim() || null,
      feedback_type: String(formData.get('feedback_type') || 'General Feedback'),
      rating,
      message,
    };

    if (!message) {
      feedbackStatus?.classList.remove('success');
      feedbackStatus?.classList.add('error');
      feedbackStatus.textContent = 'Please enter your feedback message before submitting.';
      return;
    }

    if (!Number.isInteger(rating) || rating < 1 || rating > 5) {
      feedbackStatus?.classList.remove('success');
      feedbackStatus?.classList.add('error');
      feedbackStatus.textContent = 'Please select a rating between 1 and 5.';
      return;
    }

    try {
      const response = await fetch(apiUrl('/api/feedback'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const result = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(result.detail || 'Unable to save feedback.');
      }

      feedbackStatus?.classList.remove('error');
      feedbackStatus?.classList.add('success');
      feedbackStatus.textContent = 'Thank you for your feedback!';
      feedbackForm.reset();
      feedbackRatingInput.value = '3';
      feedbackStars.forEach(star => {
        const value = Number(star.dataset.value);
        star.classList.toggle('active', value <= 3);
      });

      setTimeout(() => closeFeedbackModal(), 1800);
    } catch (error) {
      feedbackStatus?.classList.remove('success');
      feedbackStatus?.classList.add('error');
      feedbackStatus.textContent = error.message || 'Something went wrong while submitting your feedback.';
    }
  });


  // =========================================================================
  // SCREEN 6: VESSEL TRACKING TABLE & SEARCH
  // =========================================================================
  function renderVesselsTable() {
    const tbody = document.getElementById('vessels-tbody');
    if (!tbody) return;

    const searchTerm = (document.getElementById('vessel-search-input')?.value || '').toLowerCase();
    const filter = state.selectedVesselFilter;
    const vesselCatalog = Array.isArray(state.masterVessels) && state.masterVessels.length
      ? state.masterVessels
      : Array.isArray(SPILLGUARD_DATA.vessels)
        ? SPILLGUARD_DATA.vessels
        : [];

    const filtered = vesselCatalog.filter(v => {
      const vesselName = String(v.name || '').toLowerCase();
      const vesselType = String(v.type || '').toLowerCase();
      const vesselFlag = String(v.flag || '').toLowerCase();
      const matchesSearch = vesselName.includes(searchTerm) ||
                            String(v.imo || '').includes(searchTerm) ||
                            vesselFlag.includes(searchTerm) ||
                            vesselType.includes(searchTerm);

      if (!matchesSearch) return false;

      if (filter === 'dark') return Boolean(v.isDarkVessel);
      if (filter === 'tankers') return vesselType.includes('tanker') || vesselType.includes('carrier');
      if (filter === 'high-risk') return Number(v.riskScore || 0) > 70;
      return true;
    });

    tbody.innerHTML = filtered.map(v => `
      <tr>
        <td>
          <div style="font-weight: 600; color: #FFF;">${v.name || 'Unknown Vessel'}</div>
          <div class="mono" style="font-size: 11px; color: var(--text-muted);">IMO ${v.imo || '—'} • MMSI ${v.mmsi || '—'}</div>
        </td>
        <td>
          <span style="display: flex; align-items: center; gap: 6px;">
            <span>${v.flag || 'Unknown'}</span>
          </span>
        </td>
        <td>${v.type || 'Unknown'}</td>
        <td class="mono" style="font-size: 12px;">${v.lastAisPing || '—'}</td>
        <td>
          ${v.isDarkVessel ? `
            <span class="dark-vessel-badge">
              <span class="pulse-cyan-dot" style="background: var(--red-alert); box-shadow: 0 0 6px var(--red-alert);"></span>
              ${v.darkDuration || 'Dark vessel'}
            </span>
          ` : `
            <span class="safe-vessel-badge">
              <span class="pulse-cyan-dot" style="background: var(--green-safe); box-shadow: 0 0 6px var(--green-safe);"></span>
              AIS Compliant
            </span>
          `}
        </td>
        <td class="mono" style="font-size: 12px;">${v.speed ?? '—'} kt / ${v.heading ?? '—'}°</td>
        <td>
          <span class="mono" style="font-weight: 700; color: ${Number(v.riskScore || 0) > 75 ? 'var(--red-alert)' : Number(v.riskScore || 0) > 40 ? 'var(--amber-warning)' : 'var(--green-safe)'};">
            ${Number(v.riskScore || 0)}/100
          </span>
        </td>
        <td>
          ${v.isDarkVessel ? `
            <button class="btn-secondary btn-inspect-vessel" data-imo="${v.imo || ''}" style="padding: 4px 10px; font-size: 11px; border-color: var(--red-border); color: var(--red-alert);">
              Investigate Anomaly →
            </button>
          ` : `
            <button class="btn-secondary" style="padding: 4px 10px; font-size: 11px;">
              Track Path
            </button>
          `}
        </td>
      </tr>
    `).join('');

    // Bind row investigate buttons
    document.querySelectorAll('.btn-inspect-vessel').forEach(btn => {
      btn.addEventListener('click', () => {
        navigateTo('screen-investigation');
      });
    });
  }

  // Filter tabs
  document.querySelectorAll('.filter-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.selectedVesselFilter = btn.getAttribute('data-filter');
      renderVesselsTable();
    });
  });

  document.getElementById('vessel-search-input')?.addEventListener('input', renderVesselsTable);
  renderVesselsTable();


  // =========================================================================
  // SCREEN 7: ANALYTICS CHARTS & DISTRIBUTION
  // =========================================================================
  function renderAnalyticsCharts() {
    // 1. Spills Over Time SVG Chart
    const chartContainer = document.getElementById('chart-spills-time');
    if (!chartContainer) return;

    const data = SPILLGUARD_DATA.analytics.monthlyTrend;
    const maxVal = 45;
    const w = 560;
    const h = 220;

    let svgHtml = `
      <svg viewBox="0 0 ${w} ${h}" width="100%" height="100%" style="overflow: visible;">
        <!-- Grid lines -->
        <line x1="40" y1="20" x2="${w}" y2="20" stroke="rgba(255,255,255,0.06)" />
        <line x1="40" y1="70" x2="${w}" y2="70" stroke="rgba(255,255,255,0.06)" />
        <line x1="40" y1="120" x2="${w}" y2="120" stroke="rgba(255,255,255,0.06)" />
        <line x1="40" y1="170" x2="${w}" y2="170" stroke="rgba(255,255,255,0.06)" />
        <line x1="40" y1="200" x2="${w}" y2="200" stroke="rgba(144,164,190,0.3)" />

        <!-- Y Axis Labels -->
        <text x="15" y="25" fill="#536B88" font-family="JetBrains Mono" font-size="10">45</text>
        <text x="15" y="75" fill="#536B88" font-family="JetBrains Mono" font-size="10">30</text>
        <text x="15" y="125" fill="#536B88" font-family="JetBrains Mono" font-size="10">15</text>
        <text x="15" y="175" fill="#536B88" font-family="JetBrains Mono" font-size="10">5</text>
    `;

    const colWidth = (w - 60) / data.length;

    data.forEach((d, idx) => {
      const cx = 50 + idx * colWidth + colWidth / 2;
      const hMinor = (d.minor / maxVal) * 160;
      const hSig = (d.significant / maxVal) * 160;
      const hCat = (d.catastrophic / maxVal) * 160;

      const yMinor = 200 - hMinor;
      const ySig = yMinor - hSig;
      const yCat = ySig - hCat;

      svgHtml += `
        <!-- Stacked Bars -->
        <rect x="${cx - 16}" y="${yCat}" width="32" height="${hCat}" fill="#FF4438" rx="2" />
        <rect x="${cx - 16}" y="${ySig}" width="32" height="${hSig}" fill="#FFB020" />
        <rect x="${cx - 16}" y="${yMinor}" width="32" height="${hMinor}" fill="#00D4FF" />

        <!-- X Label -->
        <text x="${cx}" y="218" text-anchor="middle" fill="#90A4BE" font-family="JetBrains Mono" font-size="11">${d.month}</text>
      `;
    });

    svgHtml += `</svg>`;
    chartContainer.innerHTML = svgHtml;

    // 2. Regional Distribution Bars
    const regContainer = document.getElementById('regional-distribution-bars');
    if (regContainer) {
      regContainer.innerHTML = SPILLGUARD_DATA.analytics.regionalDistribution.map(item => `
        <div>
          <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 6px;">
            <span>${item.region}</span>
            <span class="mono" style="font-weight: 700; color: ${item.color};">${item.percent}%</span>
          </div>
          <div class="bar-track">
            <div class="bar-fill" style="width: ${item.percent}%; background: ${item.color}; box-shadow: 0 0 10px ${item.color}40;"></div>
          </div>
        </div>
      `).join('');
    }

    // 3. Top Flagged Repeat Offenders
    const topFleets = document.getElementById('top-flagged-bars');
    if (topFleets) {
      topFleets.innerHTML = SPILLGUARD_DATA.analytics.topFlaggedFleets.map(item => `
        <div class="bar-row-item">
          <div class="bar-row-label-wrap">
            <span>${item.name}</span>
            <span class="mono" style="color: var(--text-primary); font-weight: 600;">${item.count} Incidents</span>
          </div>
          <div class="bar-track">
            <div class="bar-fill ${item.color}" style="width: ${item.pct}%;"></div>
          </div>
        </div>
      `).join('');
    }
  }

  renderAnalyticsCharts();

  // Analysis Panel
  function renderAnalysisPanel() {
    const rankingBody = document.getElementById('analysis-ranking-body');
    const warningList = document.getElementById('dark-vessel-warning-list');
    if (!rankingBody || !warningList) return;

    if (!state.analysisData.rankings.length) {
      rankingBody.innerHTML = '<tr><td colspan="3" class="analysis-empty-state">No analysis run yet</td></tr>';
      warningList.innerHTML = '<li>No suspicious AIS gaps detected yet.</li>';
      return;
    }

    rankingBody.innerHTML = state.analysisData.rankings.slice(0, 5).map(v => `
      <tr>
        <td>${v.vessel_name || 'Unknown vessel'}</td>
        <td class="mono">${v.total_score}</td>
        <td><span class="priority-badge ${v.priority.toLowerCase()}">${v.priority}</span></td>
      </tr>
    `).join('');

    const warnings = state.analysisData.darkWarnings.length
      ? state.analysisData.darkWarnings
      : ['No suspicious AIS gaps detected yet.'];

    warningList.innerHTML = warnings.map(w => `<li>${w}</li>`).join('');
  }

  function getDemoDataset() {
    const demoSpill = {
      ...SPILLGUARD_DATA.spills[0],
      id: 'SG-8842',
      title: 'Malacca Strait TSS Central Infiltration',
      coords: [2.3812, 101.9124],
      areaKm2: 45.2,
      volumeBbls: 18400,
      confidence: 96.8,
      sensor: 'Sentinel-1A (C-Band IW VV+VH)'
    };

    const demoVessels = SPILLGUARD_DATA.vessels.map((v, index) => ({
      ...v,
      coords: v.coords,
      isDarkVessel: index === 0 || index === 3,
      speed: v.speed || 12,
      heading: v.heading || 120,
      riskScore: v.riskScore || 60,
      lastAisPing: index === 0 ? '3 min ago' : `${(index + 1) * 45} sec ago`,
      darkDuration: index === 0 ? '3h 48m blackout at spill origin' : index === 3 ? '1h 14m intermittent gap' : 'None (continuous)'
    }));

    return { spills: [demoSpill], vessels: demoVessels };
  }

  function loadDemoData() {
    const demo = getDemoDataset();
    SPILLGUARD_DATA.spills = demo.spills;
    SPILLGUARD_DATA.vessels = demo.vessels;
    state.selectedSpill = demo.spills[0];
    renderMapData();
    renderVesselsTable();
    renderAnalysisPanel();

    if (state.map) {
      state.map.flyTo(demo.spills[0].coords, 9, { duration: 0.8 });
    }

    return demo;
  }

  // Client-side demo-only analysis (no backend calls)
  function runDemoAnalysis() {
    const spill = SPILLGUARD_DATA.spills[0];
    if (!spill) return;

    // Simple heuristic ranking based on distance and dark flag
    const rankings = (SPILLGUARD_DATA.vessels || []).map((v) => {
      const lat = Array.isArray(v.coords) ? v.coords[0] : null;
      const lon = Array.isArray(v.coords) ? v.coords[1] : null;
      const distance = lat !== null && lon !== null
        ? (function(){ try { return haversine_distance_km(spill.coords[0], spill.coords[1], lat, lon); } catch(e){ return 999; } })()
        : 999;
      let score = Math.max(0, 100 - Math.min(100, distance * 8));
      if (v.isDarkVessel) score = Math.min(100, score + 25);
      return {
        vessel_name: v.name || `Vessel ${v.mmsi}`,
        total_score: Math.round(score * 100) / 100,
        priority: score >= 70 ? 'High' : score >= 40 ? 'Medium' : 'Low'
      };
    });

    state.analysisData.rankings = rankings.sort((a,b) => b.total_score - a.total_score);
    state.analysisData.darkWarnings = (SPILLGUARD_DATA.vessels || []).filter(v=>v.isDarkVessel).map(v=>`${v.name}: AIS gap detected`).slice(0,3);
    renderAnalysisPanel();
  }

  async function runAnalysis(spillOverride = null, originOverride = null) {
    const spill = spillOverride || state.selectedSpill || SPILLGUARD_DATA.spills[0];
    if (!spill) return;

    const spillLat = spill.coords[0];
    const spillLon = spill.coords[1];
    const analysisOrigin = originOverride || { lat: spillLat, lon: spillLon };
    const payload = {
      sar_time: '2026-09-17T10:00:00Z',
      sar_vessels: [{ id: 'sar_1', lat: spillLat, lon: spillLon }],
      ais_points: SPILLGUARD_DATA.vessels.map(v => ({
        mmsi: String(v.mmsi),
        vessel_name: v.name,
        lat: v.coords[0],
        lon: v.coords[1],
        timestamp: new Date(Date.now() - (v.isDarkVessel ? 210 : 30) * 60 * 1000).toISOString(),
        speed_knots: v.speed,
        heading: v.heading,
        vessel_type: v.type
      }))
    };

    try {
      const [matchResponse, rankingResponse, driftResponse] = await Promise.all([
        fetch(apiUrl('/api/match-vessels'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        }),
        fetch(apiUrl('/api/rank-suspects'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            origin_lat: analysisOrigin.lat,
            origin_lon: analysisOrigin.lon,
            release_start: '2026-09-17T03:00:00Z',
            release_end: '2026-09-17T05:00:00Z',
            vessels: SPILLGUARD_DATA.vessels.map(v => ({
              vessel_name: v.name,
              vessel_type: v.type,
              lat: v.coords[0],
              lon: v.coords[1],
              speed_knots: v.speed,
              timestamp: new Date(Date.now() - (v.isDarkVessel ? 35 : 15) * 60 * 1000).toISOString(),
              ais_gap_minutes: v.isDarkVessel ? 228 : 12,
              is_dark_vessel: v.isDarkVessel
            }))
          })
        }),
        fetch(apiUrl('/api/drift'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            spill_lat: spillLat,
            spill_lon: spillLon,
            current_speed_mps: 0.4,
            current_direction_degrees: 45,
            hours: 12
          })
        })
      ]);

      if (!matchResponse.ok || !rankingResponse.ok || !driftResponse.ok) {
        throw new Error('One or more analysis endpoints failed.');
      }

      const matchData = await matchResponse.json();
      const rankingData = await rankingResponse.json();
      const driftData = await driftResponse.json();

      state.analysisData.matchResults = matchData.results || [];
      state.analysisData.rankings = rankingData.results || [];
      state.analysisData.drift = driftData;

      state.analysisData.darkWarnings = state.analysisData.matchResults
        .filter(item => item.status === 'possible_dark_vessel')
        .map(item => `${item.sar_vessel_id}: possible dark vessel without a close AIS match within 5 km / 15 minutes.`);

      if (!state.analysisData.darkWarnings.length && state.analysisData.rankings.length) {
        state.analysisData.darkWarnings = state.analysisData.rankings
          .filter(item => item.priority === 'High')
          .map(item => `${item.vessel_name}: high-priority suspect based on proximity and AIS behaviour.`);
      }

      renderAnalysisPanel();
      renderMapData();
      if (state.map) {
        state.map.flyTo(spill.coords, 9, { duration: 0.8 });
      }
    } catch (error) {
      console.error('Analysis request failed:', error);
      state.analysisData.darkWarnings = ['Analysis failed. Please confirm the backend is running.', 'Investigation support, not final proof.'];
      state.analysisData.rankings = [];
      renderAnalysisPanel();
    }
  }

  document.getElementById('btn-case-review')?.addEventListener('click', () => {
    const regionKey = state.currentRegion || 'malacca';
    const localSpills = SPILLGUARD_DATA.regionSpills?.[regionKey] || SPILLGUARD_DATA.spills || [];
    const selected = localSpills[0] || state.selectedSpill || SPILLGUARD_DATA.spills?.[0];
    if (!selected) return;

    state.selectedSpill = selected;
    openSpillDrawer(selected);
    if (state.map) {
      state.map.flyTo(selected.coords, 10, { duration: 0.8 });
    }
  });

  document.getElementById('btn-reset-view')?.addEventListener('click', () => {
    const region = SPILLGUARD_DATA.regions[state.currentRegion];
    if (!region || !state.map) return;
    updateRegionUI(state.currentRegion);
    if (region.bounds) {
      state.map.fitBounds(region.bounds, { padding: [24, 24], maxZoom: region.zoom });
    } else {
      state.map.flyTo(region.center, region.zoom, { duration: 1.0 });
    }
  });

  renderAnalysisPanel();

});
