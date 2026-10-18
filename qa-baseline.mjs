// Baseline: does ANY external script execute on this server in headless mode?
export default async function run(page, ui) {
  const out = {};

  // A data: URL with an inline script — no server involved at all.
  await page.goto('data:text/html,<html><body><script>window.MARKER="inline-ran";<\/script></body></html>');
  await page.waitForTimeout(500);
  out.inlineDataUrl = await page.evaluate(() => window.MARKER || null);

  // The real site, probes at several delays.
  await page.goto('http://127.0.0.1:5500/index.html', { waitUntil: 'load' });
  const probes = [];
  for (const ms of [500, 1500, 3000, 6000, 10000]) {
    await page.waitForTimeout(ms === 500 ? 500 : ms - probes[probes.length - 1].at);
    probes.push({
      at: ms,
      hasL: await page.evaluate(() => !!window.L),
      hasData: await page.evaluate(() => !!window.SPILLGUARD_DATA),
      hasAlerts: await page.evaluate(() => !!window.SpillGuardAlerts),
      readyState: await page.evaluate(() => document.readyState)
    });
  }
  out.probes = probes;

  // Are the script elements flagged as loaded/errored?
  out.scriptEls = await page.evaluate(() =>
    Array.from(document.scripts).map((s) => ({
      src: s.getAttribute('src'),
      hasLoadEvent: s.readyState || null,
      inDocument: document.contains(s)
    }))
  );

  return out;
}
