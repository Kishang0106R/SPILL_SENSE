/**
 * Spill Sense Maritime Data & Forensic Telemetry Service
 * Realistic Synthetic Aperture Radar (SAR) and Class-A AIS Dataset
 */

window.SPILLGUARD_DATA = {
  // Current active region metadata
  regions: {
    malacca: {
      name: "Strait of Malacca (TSS Corridor)",
      center: [2.5228, 101.7967],
      zoom: 10,
      bounds: [[2.15, 101.20], [2.80, 102.30]],
      liveFeed: { lat: 2.45, lon: 101.85, radius: 50 },
      overlays: {
        corridor: [[2.2700, 101.9700], [2.3100, 101.9350], [2.3600, 101.9000], [2.4100, 101.8600], [2.4500, 101.8200], [2.5000, 101.7900], [2.5228, 101.7967]],
        waypoints: [
          { coords: [2.2700, 101.9700], label: 'WP-1 Linggi Entry' }, { coords: [2.3100, 101.9350], label: 'WP-2 Channel Bend' },
          { coords: [2.3600, 101.9000], label: 'WP-3 Mid-Strait' }, { coords: [2.4100, 101.8600], label: 'WP-4 Approach' },
          { coords: [2.4500, 101.8200], label: 'WP-5 Outer Anchorage' }, { coords: [2.5000, 101.7900], label: 'WP-6 Port Roads' },
          { coords: [2.5228, 101.7967], label: 'WP-7 Terminal' }
        ],
        priorityZone: [[2.4900, 101.7600], [2.5400, 101.7600], [2.5550, 101.8100], [2.5350, 101.8400], [2.5000, 101.8350], [2.4800, 101.8000]],
        sarVector: [[2.3300, 101.8200], [2.4400, 101.9400]],
        sarIntercept: [2.3850, 101.8800],
        labels: [{ coords: [2.5350, 101.7750], text: 'PORT DICKSON' }, { coords: [2.2550, 101.9800], text: 'Linggi' }]
      },
      slicksCount: 3,
      darkVesselsCount: 4,
      riskLevel: "CRITICAL"
    },
    persian_gulf: {
      name: "Persian Gulf (Strait of Hormuz)",
      center: [26.45, 55.85],
      zoom: 9,
      bounds: [[25.70, 54.60], [27.20, 57.00]],
      liveFeed: { lat: 26.45, lon: 55.85, radius: 50 },
      overlays: {
        corridor: [[26.15, 56.35], [26.25, 56.10], [26.38, 55.92], [26.45, 55.85], [26.55, 55.72]],
        waypoints: [
          { coords: [26.15, 56.35], label: 'WP-1 Gulf of Oman' }, { coords: [26.25, 56.10], label: 'WP-2 Eastern Approach' },
          { coords: [26.38, 55.92], label: 'WP-3 Strait Center' }, { coords: [26.45, 55.85], label: 'WP-4 Hormuz' },
          { coords: [26.55, 55.72], label: 'WP-5 Persian Gulf' }
        ],
        priorityZone: [[26.40, 55.80], [26.50, 55.80], [26.53, 55.90], [26.45, 55.96], [26.38, 55.90]],
        sarVector: [[26.30, 56.02], [26.48, 55.84]],
        sarIntercept: [26.45, 55.85],
        labels: [{ coords: [26.48, 55.78], text: 'STRAIT OF HORMUZ' }, { coords: [26.20, 56.25], text: 'Gulf of Oman' }]
      },
      slicksCount: 2,
      darkVesselsCount: 3,
      riskLevel: "HIGH"
    },
    north_sea: {
      name: "North Sea (Dogger Bank Sector)",
      center: [55.10, 3.20],
      zoom: 8,
      bounds: [[54.20, 1.00], [56.00, 5.00]],
      liveFeed: { lat: 55.10, lon: 3.20, radius: 80 },
      overlays: {
        corridor: [[54.70, 2.00], [54.85, 2.45], [55.10, 3.20], [55.35, 3.70], [55.60, 4.20]],
        waypoints: [
          { coords: [54.70, 2.00], label: 'WP-1 Southern Approach' }, { coords: [54.85, 2.45], label: 'WP-2 Dogger South' },
          { coords: [55.10, 3.20], label: 'WP-3 Dogger Bank' }, { coords: [55.35, 3.70], label: 'WP-4 Northern Route' },
          { coords: [55.60, 4.20], label: 'WP-5 North Sea Exit' }
        ],
        priorityZone: [[55.04, 3.08], [55.18, 3.08], [55.22, 3.30], [55.08, 3.38], [54.98, 3.25]],
        sarVector: [[54.92, 2.80], [55.14, 3.25]],
        sarIntercept: [55.10, 3.20],
        labels: [{ coords: [55.16, 3.00], text: 'DOGGER BANK' }, { coords: [54.78, 2.10], text: 'North Sea Route' }]
      },
      slicksCount: 1,
      darkVesselsCount: 1,
      riskLevel: "MODERATE"
    },
    gulf_mexico: {
      name: "Gulf of Mexico (Mississippi Canyon)",
      center: [28.75, -88.35],
      zoom: 8,
      bounds: [[27.80, -90.20], [29.60, -86.80]],
      liveFeed: { lat: 28.75, lon: -88.35, radius: 80 },
      overlays: {
        corridor: [[28.20, -89.10], [28.45, -88.75], [28.75, -88.35], [29.05, -88.00], [29.35, -87.65]],
        waypoints: [
          { coords: [28.20, -89.10], label: 'WP-1 Deepwater South' }, { coords: [28.45, -88.75], label: 'WP-2 Mississippi Fan' },
          { coords: [28.75, -88.35], label: 'WP-3 Mississippi Canyon' }, { coords: [29.05, -88.00], label: 'WP-4 Shelf Edge' },
          { coords: [29.35, -87.65], label: 'WP-5 Northern Route' }
        ],
        priorityZone: [[28.65, -88.48], [28.85, -88.48], [28.90, -88.22], [28.72, -88.18], [28.60, -88.32]],
        sarVector: [[28.45, -88.70], [28.80, -88.30]],
        sarIntercept: [28.75, -88.35],
        labels: [{ coords: [28.82, -88.52], text: 'MISSISSIPPI CANYON' }, { coords: [28.30, -88.95], text: 'Gulf of Mexico' }]
      },
      slicksCount: 2,
      darkVesselsCount: 2,
      riskLevel: "ELEVATED"
    }
  },

  // Active Oil Spill Incidents Detected by SAR
  spills: [
    {
      id: "SG-8842",
      title: "Malacca Strait TSS Central Infiltration",
      severity: "critical", // red
      status: "UNATTRIBUTED DISCHARGE",
      coords: [2.3812, 101.9124],
      areaKm2: 45.2,
      volumeBbls: 18400,
      confidence: 96.8,
      sensor: "Sentinel-1A (C-Band IW VV+VH)",
      detectedAt: "2026-09-16 04:12:44 UTC",
      wind: "14 kt NW (310°)",
      current: "1.8 kt SE (135°)",
      surfaceTemp: "29.4°C",
      slickType: "Heavy Crude Oil Emulsion",
      thumbnail: "assets/images/sar_slick_detail.jpg",
      primarySuspect: {
        name: "MT Ocean Vanguard",
        imo: 9482154,
        confidence: 94.8,
        matchType: "High Forensic Correlation"
      },
      slickPolygon: [
        [2.420, 101.860],
        [2.435, 101.905],
        [2.410, 101.960],
        [2.370, 101.980],
        [2.340, 101.930],
        [2.355, 101.875]
      ]
    },
    {
      id: "SG-8839",
      title: "Cape Rachado Outer Slick",
      severity: "medium", // amber
      status: "UNDER INVESTIGATION",
      coords: [2.5210, 101.7100],
      areaKm2: 12.8,
      volumeBbls: 3600,
      confidence: 88.4,
      sensor: "ICEYE-X12 (X-Band StripMap)",
      detectedAt: "2026-09-16 01:45:10 UTC",
      wind: "11 kt WNW (295°)",
      current: "1.4 kt SE (140°)",
      surfaceTemp: "29.6°C",
      slickType: "Bilge Wash / Fuel Oil Residue",
      thumbnail: "assets/images/sar_slick_detail.jpg",
      primarySuspect: {
        name: "Nordic Titan",
        imo: 9310842,
        confidence: 41.2,
        matchType: "Secondary Candidate"
      },
      slickPolygon: [
        [2.535, 101.690],
        [2.540, 101.730],
        [2.510, 101.745],
        [2.495, 101.715],
        [2.515, 101.685]
      ]
    },
    {
      id: "SG-8831",
      title: "Port Dickson South Discharge",
      severity: "medium", // amber
      status: "FLAGGED PRELIMINARY",
      coords: [2.2240, 102.0450],
      areaKm2: 5.4,
      volumeBbls: 980,
      confidence: 82.1,
      sensor: "RADARSAT Constellation Mission-2",
      detectedAt: "2026-09-15 22:30:18 UTC",
      wind: "9 kt N (350°)",
      current: "1.6 kt SE (130°)",
      surfaceTemp: "29.2°C",
      slickType: "Oily Water Separator Discharge",
      thumbnail: "assets/images/sar_slick_detail.jpg",
      primarySuspect: {
        name: "Stellar Voyager",
        imo: 9604122,
        confidence: 18.5,
        matchType: "Uncorrelated"
      },
      slickPolygon: [
        [2.235, 102.030],
        [2.240, 102.060],
        [2.215, 102.065],
        [2.210, 102.035]
      ]
    }
  ],

  // Monitored Vessel Database (AIS Streams)
  vessels: [
    {
      name: "MT Ocean Vanguard",
      imo: 9482154,
      mmsi: 636019842,
      callSign: "ELVA8",
      flag: "Liberia",
      flagCode: "lr",
      type: "VLCC Crude Tanker",
      length: "333m",
      beam: "60m",
      dwt: "305,000",
      coords: [2.285, 102.120],
      heading: 132,
      speed: 13.8,
      draft: "19.2m",
      lastAisPing: "3 min ago",
      signalHealth: "Dark",
      isDarkVessel: true,
      darkDuration: "3h 48m Blackout at Spill Origin",
      riskScore: 95,
      riskLevel: "CRITICAL",
      trackHistory: [
        [2.650, 101.450],
        [2.540, 101.680],
        [2.440, 101.880], // Slick origin point where AIS was disabled
        [2.350, 102.010],
        [2.285, 102.120]
      ]
    },
    {
      name: "Nordic Titan",
      imo: 9310842,
      mmsi: 538006214,
      callSign: "V7KT4",
      flag: "Marshall Islands",
      flagCode: "mh",
      type: "Capesize Bulk Carrier",
      length: "292m",
      beam: "45m",
      dwt: "180,000",
      coords: [2.480, 101.820],
      heading: 130,
      speed: 11.4,
      draft: "16.8m",
      lastAisPing: "45 sec ago",
      signalHealth: "Good",
      isDarkVessel: false,
      darkDuration: "None (Continuous)",
      riskScore: 42,
      riskLevel: "MEDIUM",
      trackHistory: [
        [2.720, 101.350],
        [2.600, 101.600],
        [2.480, 101.820]
      ]
    },
    {
      name: "Stellar Voyager",
      imo: 9604122,
      mmsi: 354891000,
      callSign: "3FGL9",
      flag: "Panama",
      flagCode: "pa",
      type: "Ultra-Large Container (20k TEU)",
      length: "399m",
      beam: "59m",
      dwt: "198,000",
      coords: [2.180, 102.250],
      heading: 128,
      speed: 18.2,
      draft: "14.5m",
      lastAisPing: "1 min ago",
      signalHealth: "Good",
      isDarkVessel: false,
      darkDuration: "None (Continuous)",
      riskScore: 18,
      riskLevel: "SAFE",
      trackHistory: [
        [2.450, 101.800],
        [2.320, 102.020],
        [2.180, 102.250]
      ]
    },
    {
      name: "Seaborne Horizon",
      imo: 9284177,
      mmsi: 636014522,
      callSign: "D5HG2",
      flag: "Liberia",
      flagCode: "lr",
      type: "Chemical / Products Tanker",
      length: "183m",
      beam: "32m",
      dwt: "50,000",
      coords: [2.580, 101.620],
      heading: 310,
      speed: 12.0,
      draft: "10.2m",
      lastAisPing: "5 min ago",
      signalHealth: "Degraded",
      isDarkVessel: true,
      darkDuration: "1h 14m Intermittent Gap",
      riskScore: 78,
      riskLevel: "HIGH",
      trackHistory: [
        [2.420, 101.900],
        [2.500, 101.760],
        [2.580, 101.620]
      ]
    },
    {
      name: "CMA CGM Pegasus",
      imo: 9839923,
      mmsi: 228389000,
      callSign: "FNKJ",
      flag: "France",
      flagCode: "fr",
      type: "Container Ship",
      length: "366m",
      beam: "51m",
      dwt: "155,000",
      coords: [2.390, 102.040],
      heading: 134,
      speed: 16.5,
      draft: "13.8m",
      lastAisPing: "20 sec ago",
      signalHealth: "Good",
      isDarkVessel: false,
      darkDuration: "None",
      riskScore: 12,
      riskLevel: "SAFE",
      trackHistory: [
        [2.610, 101.650],
        [2.500, 101.840],
        [2.390, 102.040]
      ]
    },
    {
      name: "Apex Trader",
      imo: 9145892,
      mmsi: 312548000,
      callSign: "V3TR8",
      flag: "Belize",
      flagCode: "bz",
      type: "Aframax Crude Carrier",
      length: "244m",
      beam: "42m",
      dwt: "105,000",
      coords: [2.620, 101.550],
      heading: 135,
      speed: 9.8,
      draft: "15.1m",
      lastAisPing: "2h ago",
      signalHealth: "Dark",
      isDarkVessel: true,
      darkDuration: "5h 22m Blackout",
      riskScore: 88,
      riskLevel: "CRITICAL",
      trackHistory: [
        [2.780, 101.240],
        [2.620, 101.550]
      ]
    },
    {
      name: "Pacific Sentinel",
      imo: 9741203,
      mmsi: 563044100,
      callSign: "9V648",
      flag: "Singapore",
      flagCode: "sg",
      type: "LPG Tanker",
      length: "226m",
      beam: "37m",
      dwt: "55,000",
      coords: [2.310, 101.990],
      heading: 312,
      speed: 14.1,
      draft: "11.4m",
      lastAisPing: "1 min ago",
      signalHealth: "Good",
      isDarkVessel: false,
      darkDuration: "None",
      riskScore: 14,
      riskLevel: "SAFE",
      trackHistory: [
        [2.150, 102.260],
        [2.310, 101.990]
      ]
    }
  ],

  // Optional explicit per-region datasets to ensure the UI shows region-specific
  // incidents and vessel markers without relying on spatial filters.
  regionSpills: {
    malacca: [
      // reuse SG-8842 as primary for Malacca
      {
        id: "SG-8842",
        title: "Malacca Strait TSS Central Infiltration",
        severity: "critical",
        coords: [2.3812, 101.9124],
        areaKm2: 45.2,
        volumeBbls: 18400,
        confidence: 96.8,
        sensor: "Sentinel-1A (C-Band IW VV+VH)",
        detectedAt: "2026-09-16 04:12:44 UTC",
        slickPolygon: [
          [2.420, 101.860],
          [2.435, 101.905],
          [2.410, 101.960],
          [2.370, 101.980],
          [2.340, 101.930],
          [2.355, 101.875]
        ],
        primarySuspect: { name: "MT Ocean Vanguard", confidence: 94.8 }
      }
    ],
    persian_gulf: [
      {
        id: "SG-PG-2101",
        title: "Strait of Hormuz Offshore Slick",
        severity: "high",
        coords: [26.45, 55.85],
        areaKm2: 18.6,
        volumeBbls: 5200,
        confidence: 92.1,
        sensor: "ICEYE-X12 (X-Band)",
        detectedAt: "2026-09-17 02:34:12 UTC",
        slickPolygon: [
          [26.47, 55.82],
          [26.46, 55.88],
          [26.42, 55.89],
          [26.40, 55.84]
        ],
        primarySuspect: { name: "Al Hadi Trader", confidence: 78.2 }
      }
    ],
    north_sea: [
      {
        id: "SG-NS-3310",
        title: "Dogger Bank Slick",
        severity: "medium",
        coords: [55.10, 3.20],
        areaKm2: 6.4,
        volumeBbls: 1200,
        confidence: 88.4,
        sensor: "RADARSAT-2",
        detectedAt: "2026-09-15 18:12:00 UTC",
        slickPolygon: [
          [55.12, 3.18],
          [55.11, 3.22],
          [55.09, 3.21],
          [55.08, 3.19]
        ],
        primarySuspect: { name: "Nordic Titan", confidence: 41.2 }
      }
    ],
    gulf_mexico: [
      {
        id: "SG-GM-4420",
        title: "Mississippi Canyon Outer Slick",
        severity: "medium",
        coords: [28.75, -88.35],
        areaKm2: 9.2,
        volumeBbls: 2600,
        confidence: 85.0,
        sensor: "Sentinel-1B",
        detectedAt: "2026-09-14 11:05:22 UTC",
        slickPolygon: [
          [28.77, -88.40],
          [28.76, -88.30],
          [28.73, -88.32]
        ],
        primarySuspect: { name: "Gulf Mariner", confidence: 52.4 }
      }
    ]
  },

  regionVessels: {
    malacca: [
      { name: "MT Ocean Vanguard", mmsi: 636019842, coords: [2.285, 102.120], heading: 132, speed: 13.8 },
      { name: "Nordic Titan", mmsi: 538006214, coords: [2.480, 101.820], heading: 130, speed: 11.4 }
    ],
    persian_gulf: [
      { name: "Al Hadi Trader", mmsi: 412345678, coords: [26.46, 55.86], heading: 90, speed: 10.2 }
    ],
    north_sea: [
      { name: "North Sea Carrier", mmsi: 225001122, coords: [55.11, 3.21], heading: 45, speed: 12.5 }
    ],
    gulf_mexico: [
      { name: "Gulf Mariner", mmsi: 367001234, coords: [28.75, -88.35], heading: 210, speed: 9.1 }
    ]
  },

  // Incident SG-8842 Forensic Deep-Dive Data
  investigation: {
    incidentId: "SG-8842",
    caseCode: "CASE-2026-SG8842-MLC",
    classification: "MARPOL Annex I Hydrocarbon Discharge",
    locationDesc: "Strait of Malacca TSS Sector 4 (Offshore Melaka)",
    latLong: "02°22'52\"N, 101°54'45\"E",
    satellite: {
      name: "Sentinel-1A SAR",
      passTime: "2026-09-16 04:12:44 UTC",
      orbit: "Ascending Path 148, Frame 582",
      mode: "Interferometric Wide (IW)",
      polarization: "VV + VH Dual-Pol",
      spatialResolution: "10m x 10m"
    },
    metocean: {
      windSpeed: "14.2 knots",
      windDir: "310° (NW)",
      surfaceCurrent: "1.8 knots @ 135° (SE)",
      driftVelocity: "2.1 knots @ 138°",
      sst: "29.4 °C",
      waveHeight: "0.8m significant",
      coralReefProximity: "8.4 nautical miles (Pulau Besar MPA)"
    },
    forensics: {
      polarimetricRatio: "VV/VH ratio drops by -7.4 dB within anomaly zone (characteristic of crude oil dampening capillary-gravity waves)",
      meanThickness: "1.42 mm (emulsified core exceeds 3.8 mm)",
      slickTotalArea: "45.2 km²",
      slickVolumeEst: "18,400 bbls (2,925 m³)",
      sha256DossierHash: "e4b983c27189fa3198de7e5a01bc6f4439c09d57a2c4187f1b70298e10fa31ce"
    },
    driftSimulation: {
      // Reverse Lagrangian particle simulation backwards in time
      timeSteps: [
        { time: "T-0h (Now / SAR Scan)", label: "SAR Acquisition", coords: [2.381, 101.912] },
        { time: "T-3h (01:12 UTC)", label: "Lagrangian Step -3h", coords: [2.410, 101.885] },
        { time: "T-6h (22:12 UTC)", label: "Lagrangian Step -6h", coords: [2.438, 101.860] },
        { time: "T-9h (19:12 UTC)", label: "Slick Origin Confluence", coords: [2.465, 101.835] }
      ],
      originEstimate: {
        coords: [2.445, 101.855],
        timestamp: "2026-09-15 23:45 UTC ± 35 min",
        accuracyRadius: "0.4 nautical miles"
      }
    },
    // Ranked candidate attribution
    candidates: [
      {
        rank: 1,
        name: "MT Ocean Vanguard",
        imo: 9482154,
        flag: "Liberia 🇱🇷",
        type: "VLCC Crude Tanker",
        confidence: 94.8,
        matchLevel: "PRIMARY SUSPECT",
        evidence: [
          { type: "red", text: "AIS transponder disabled for 3h 48m precisely across slick origin zone" },
          { type: "red", text: "Vessel draft dropped by 1.6m mid-transit (-2,400 tonnes displacement)" },
          { type: "red", text: "Speed anomaly: decelerated from 14.4 kt to 6.4 kt during transponder blackout" },
          { type: "amber", text: "Lagrangian reverse-drift origin trajectory aligns with ship course (r = 0.984)" },
          { type: "amber", text: "SAR backscatter detects distinctive dark trailing stern wake plume on swath" }
        ]
      },
      {
        rank: 2,
        name: "Nordic Titan",
        imo: 9310842,
        flag: "Marshall Islands 🇲🇭",
        type: "Bulk Carrier",
        confidence: 41.2,
        matchLevel: "LOW PROBABILITY",
        evidence: [
          { type: "neutral", text: "Passed 4.8 nm downwind of estimated origin coordinates" },
          { type: "neutral", text: "Maintained continuous uninterrupted AIS broadcast" },
          { type: "neutral", text: "Engine RPM and draft telemetry show nominal steady cruising" }
        ]
      },
      {
        rank: 3,
        name: "Stellar Voyager",
        imo: 9604122,
        flag: "Panama 🇵🇦",
        type: "Container Carrier",
        confidence: 18.5,
        matchLevel: "EXCLUDED",
        evidence: [
          { type: "neutral", text: "Transited TSS corridor 8.5 hours after calculated discharge timestamp" },
          { type: "neutral", text: "Speed maintained steady at 18.2 kt throughout sector" }
        ]
      }
    ]
  },

  // Analytics Trends & Performance Data
  analytics: {
    kpis: {
      totalDetections90d: 1248,
      volumeDischargedBbls: "342,800 bbls",
      attributionSuccessRate: "92.4%",
      penaltiesLeviedUSD: "$48.2M"
    },
    monthlyTrend: [
      { month: "Apr", catastrophic: 2, significant: 8, minor: 24 },
      { month: "May", catastrophic: 3, significant: 11, minor: 28 },
      { month: "Jun", catastrophic: 1, significant: 7, minor: 19 },
      { month: "Jul", catastrophic: 4, significant: 14, minor: 32 },
      { month: "Aug", catastrophic: 2, significant: 9, minor: 22 },
      { month: "Sep (MTD)", catastrophic: 5, significant: 16, minor: 38 }
    ],
    regionalDistribution: [
      { region: "Strait of Malacca", percent: 42, color: "#FF4438" },
      { region: "Persian Gulf", percent: 28, color: "#FFB020" },
      { region: "South China Sea", percent: 14, color: "#00D4FF" },
      { region: "North Sea", percent: 10, color: "#2BD97C" },
      { region: "Gulf of Mexico", percent: 6, color: "#90A4BE" }
    ],
    topFlaggedFleets: [
      { name: "Liberia (FOC)", count: 48, pct: 85, color: "red-fill" },
      { name: "Panama (FOC)", count: 39, pct: 70, color: "red-fill" },
      { name: "Gabon (Dark Tanker Fleet)", count: 31, pct: 56, color: "amber-fill" },
      { name: "Marshall Islands", count: 18, pct: 32, color: "cyan-fill" },
      { name: "Cook Islands", count: 14, pct: 25, color: "cyan-fill" }
    ]
  }
};
