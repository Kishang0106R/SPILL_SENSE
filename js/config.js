// Spill Sense client configuration
// Add your Mapbox Access Token here to use Mapbox Dark tiles on the dashboard.
// Get a token at https://account.mapbox.com/
window.MAPBOX_TOKEN = '';

// Optionally set a Mapbox style id. Default is 'mapbox/dark-v10'.
window.MAPBOX_STYLE = 'mapbox/dark-v10';

// MapTiler satellite/hybrid tiles are used when this key is configured.
window.MAPTILER_KEY = '6Ai35tAGTZpCMYQra61M';

// FastAPI origin. Keep this pointed at the backend when the site is opened
// through Live Server or another static-file server.
// Empty means "use this site's origin".  This works on Vercel and avoids
// hard-coding a localhost API address in production.
window.SPILLGUARD_API_BASE = window.location.origin;

// If you prefer other providers, leave MAPBOX_TOKEN empty to use the built-in CARTO dark tiles.
