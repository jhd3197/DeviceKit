"""The rendered `/api/v1/docs` page (plan 21, part 2).

A single self-contained HTML document — no CDN scripts, no build step — that fetches
``/api/v1/openapi.json`` client-side and renders it grouped by tag, in the app's dark
theme. Session cookies ride along on the same-origin fetch; a machine can open it with
``?api_key=dk_…`` (the same query-param fallback the API itself accepts).
"""

DOCS_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DeviceKit API v1</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #09090b; color: #a1a1aa; font: 14px/1.55 ui-sans-serif, system-ui, sans-serif; }
  .wrap { max-width: 960px; margin: 0 auto; padding: 32px 20px 80px; }
  h1 { color: #fafafa; font-size: 22px; letter-spacing: -0.02em; }
  .sub { margin: 6px 0 4px; }
  .pill { display: inline-block; padding: 1px 8px; border: 1px solid #27272a; border-radius: 999px;
          font-size: 11px; color: #71717a; margin-right: 6px; }
  h2 { color: #e4e4e7; font-size: 15px; margin: 34px 0 10px; text-transform: capitalize;
       border-bottom: 1px solid #27272a; padding-bottom: 8px; }
  details { background: #101012; border: 1px solid #27272a; border-radius: 8px; margin: 8px 0; }
  details[open] { background: #131316; }
  summary { display: flex; align-items: center; gap: 10px; padding: 9px 12px; cursor: pointer;
            list-style: none; }
  summary::-webkit-details-marker { display: none; }
  .m { font: 700 11px/1 ui-monospace, monospace; padding: 3px 7px; border-radius: 5px;
       min-width: 52px; text-align: center; }
  .m-get    { color: #60a5fa; background: rgba(59,130,246,.12); }
  .m-post   { color: #34d399; background: rgba(16,185,129,.12); }
  .m-put    { color: #fbbf24; background: rgba(245,158,11,.12); }
  .m-patch  { color: #c084fc; background: rgba(168,85,247,.12); }
  .m-delete { color: #f87171; background: rgba(239,68,68,.12); }
  .path { font: 13px ui-monospace, monospace; color: #e4e4e7; word-break: break-all; }
  .sum { color: #71717a; font-size: 12.5px; margin-left: auto; text-align: right; }
  .body { padding: 4px 14px 14px; border-top: 1px solid #1f1f23; }
  .desc { margin: 10px 0; white-space: pre-wrap; }
  .scope { display: inline-block; margin: 8px 0 2px; padding: 2px 9px; border-radius: 999px;
           font: 600 11px ui-monospace, monospace; color: #fbbf24;
           background: rgba(245,158,11,.1); border: 1px solid rgba(245,158,11,.3); }
  .public { color: #34d399; background: rgba(16,185,129,.1); border-color: rgba(16,185,129,.3); }
  table { border-collapse: collapse; margin: 10px 0 2px; font-size: 12.5px; }
  td, th { border: 1px solid #27272a; padding: 4px 10px; text-align: left; }
  th { color: #71717a; font-weight: 600; }
  td code { color: #e4e4e7; font-family: ui-monospace, monospace; }
  .err { background: #1c1012; border: 1px solid #7f1d1d; color: #fca5a5; border-radius: 8px;
         padding: 14px 16px; margin-top: 24px; }
  a { color: #60a5fa; text-decoration: none; }
</style>
</head>
<body>
<div class="wrap">
  <h1>DeviceKit API <span class="pill">v1</span></h1>
  <p class="sub" id="meta">Loading spec…</p>
  <p class="sub"><span class="pill">X-API-Key: dk_…</span><span class="pill">Bearer session token</span>
     <a href="/api/v1/openapi.json">openapi.json</a></p>
  <div id="root"></div>
</div>
<script>
(async () => {
  const qs = new URLSearchParams(location.search);
  const specUrl = '/api/v1/openapi.json' + (qs.get('api_key') ? ('?api_key=' + encodeURIComponent(qs.get('api_key'))) : '');
  const root = document.getElementById('root');
  let spec;
  try {
    const res = await fetch(specUrl, { credentials: 'include' });
    if (!res.ok) throw new Error(res.status + ' ' + res.statusText);
    spec = await res.json();
  } catch (e) {
    root.innerHTML = '<div class="err">Could not load the spec (' + e.message +
      '). Log in to the DeviceKit UI first, or append <code>?api_key=dk_…</code> to this URL.</div>';
    return;
  }
  document.getElementById('meta').textContent = spec.info.description || '';
  const byTag = {};
  for (const [path, ops] of Object.entries(spec.paths)) {
    for (const [method, op] of Object.entries(ops)) {
      const tag = (op.tags && op.tags[0]) || 'other';
      (byTag[tag] = byTag[tag] || []).push({ path, method, op });
    }
  }
  const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  for (const tag of Object.keys(byTag).sort()) {
    const h = document.createElement('h2');
    h.textContent = tag;
    root.appendChild(h);
    byTag[tag].sort((a, b) => a.path.localeCompare(b.path) || a.method.localeCompare(b.method));
    for (const { path, method, op } of byTag[tag]) {
      const d = document.createElement('details');
      let inner = '<summary><span class="m m-' + method + '">' + method.toUpperCase() +
        '</span><span class="path">' + esc(path) + '</span><span class="sum">' +
        esc(op.summary || '') + '</span></summary><div class="body">';
      if (op.description) inner += '<div class="desc">' + esc(op.description) + '</div>';
      if (op['x-required-scope'])
        inner += '<span class="scope">scope: ' + esc(op['x-required-scope']) + '</span>';
      if (Array.isArray(op.security) && op.security.length === 0)
        inner += '<span class="scope public">public</span>';
      if (op.parameters && op.parameters.length) {
        inner += '<table><tr><th>path param</th><th>type</th></tr>' + op.parameters.map(p =>
          '<tr><td><code>' + esc(p.name) + '</code></td><td>' + esc(p.schema.type) + '</td></tr>'
        ).join('') + '</table>';
      }
      inner += '</div>';
      d.innerHTML = inner;
      root.appendChild(d);
    }
  }
})();
</script>
</body>
</html>
"""
