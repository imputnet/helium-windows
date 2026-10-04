export const MARKER = '# LOCAL TAB TRANSFER POWERSHELL';
export const PAYLOAD_MARKER = '@@TAB_PAYLOAD@@';
export const MAX_URL_LENGTH = 23000;

export function transferableUrl(raw) {
  if (typeof raw !== 'string' || raw.length > MAX_URL_LENGTH || /[\u0000-\u0020\u007f]/.test(raw)) return null;
  if (/^chrome:\/\/newtab\/?$/i.test(raw) || raw === 'about:blank') return 'about:blank';
  try {
    const url = new URL(raw);
    if (!['http:', 'https:', 'file:'].includes(url.protocol)) return null;
    if (url.protocol !== 'file:' && !url.hostname) return null;
    return url.href;
  } catch { return null; }
}

export function captureWindows(windows) {
  const captured = [], skipped = [];
  for (const window of windows) {
    if (window.type !== 'normal' || window.incognito) continue;
    const urls = [];
    for (const tab of [...(window.tabs || [])].sort((a, b) => a.index - b.index)) {
      if (tab.incognito) continue;
      const raw = tab.pendingUrl || tab.url;
      const url = transferableUrl(raw);
      if (url) urls.push(url);
      else skipped.push({title: tab.title || 'Unavailable tab', reason: raw?.startsWith('chrome-extension:')
        ? 'Extension page' : raw?.startsWith('chrome:') ? 'Chrome settings/internal page' : 'Unsupported or oversized URL'});
    }
    if (urls.length) captured.push({urls});
  }
  return {payload: {format: 'chrome-tabs-to-helium', version: 1, createdAt: new Date().toISOString(), windows: captured}, skipped};
}

export function validatePayload(payload) {
  if (!payload || payload.format !== 'chrome-tabs-to-helium' || payload.version !== 1
    || !Array.isArray(payload.windows) || !payload.windows.length || payload.windows.length > 2000) {
    throw new Error('Invalid tab snapshot.');
  }
  let count = 0;
  for (const window of payload.windows) {
    if (!Array.isArray(window.urls) || !window.urls.length) throw new Error('Invalid tab window.');
    for (const url of window.urls) {
      if (transferableUrl(url) !== url) throw new Error('Snapshot contains an unsupported URL.');
      count++;
    }
  }
  if (count > 20000) throw new Error('Too many tabs in one launcher.');
  return payload;
}

export function buildLauncher(payload, template) {
  validatePayload(payload);
  if (template.split(PAYLOAD_MARKER).length !== 2) throw new Error('Invalid launcher template.');
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  let text = '';
  for (let i = 0; i < bytes.length; i += 8192) text += String.fromCharCode(...bytes.subarray(i, i + 8192));
  // Only Base64 data enters the fixed PowerShell program. URLs never enter shell code.
  const script = template.replace(PAYLOAD_MARKER, btoa(text));
  const batch = [
    '@echo off',
    'setlocal DisableDelayedExpansion',
    'set "LOCAL_TAB_TRANSFER_FILE=%~f0"',
    '"%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -NoLogo -NoProfile -STA -ExecutionPolicy Bypass -Command "$text=[IO.File]::ReadAllText($env:LOCAL_TAB_TRANSFER_FILE);$marker=[char]35+\' LOCAL TAB TRANSFER POWERSHELL\';$offset=$text.IndexOf($marker,[StringComparison]::Ordinal);if($offset -lt 0){throw \'Invalid tab launcher.\'};& ([scriptblock]::Create($text.Substring($offset+$marker.Length)))"',
    'exit /b %errorlevel%',
    MARKER,
    script
  ];
  return batch.join('\r\n');
}
