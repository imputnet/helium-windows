import {captureWindows, buildLauncher} from './core.mjs';
const $ = (id) => document.getElementById(id);
let count = 0;

async function snapshot() {
  const windows = await chrome.windows.getAll({populate: true, windowTypes: ['normal']});
  const result = captureWindows(windows);
  count = result.payload.windows.reduce((sum, window) => sum + window.urls.length, 0);
  $('count').textContent = `${count} tabs in ${result.payload.windows.length} windows ready to open.`;
  $('skipped').hidden = !result.skipped.length;
  $('skipped-count').textContent = `${result.skipped.length} tabs cannot transfer`;
  $('skipped-list').replaceChildren(...result.skipped.map((item) => {
    const li = document.createElement('li');
    li.textContent = `${item.title} — ${item.reason}`;
    return li;
  }));
  return result.payload;
}

$('save').addEventListener('click', async () => {
  $('save').disabled = true;
  let blobUrl;
  try {
    // Re-query on click so tabs opened or closed since the popup appeared are reflected.
    const payload = await snapshot();
    if (!count) throw new Error('No transferable tabs are open.');
    const response = await fetch(chrome.runtime.getURL('launcher.ps1.txt'));
    if (!response.ok) throw new Error('Launcher template is unavailable. Reload the extension.');
    const launcher = buildLauncher(payload, await response.text());
    blobUrl = URL.createObjectURL(new Blob([launcher], {type:'application/octet-stream'}));
    await chrome.downloads.download({url: blobUrl, filename: `Open-${count}-Chrome-tabs-in-Helium.cmd`, saveAs: true});
    $('status').textContent = 'Finish saving, then double-click the .cmd file. It detects Helium automatically; if needed, select Helium’s executable.';
  } catch (error) { $('status').textContent = error.message || 'Could not save the launcher.'; }
  finally {
    $('save').disabled = !count;
    // The browser releases this extension document's Blob URLs when the popup closes.
    if (blobUrl) setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
  }
});

try { await snapshot(); $('save').disabled = !count; }
catch { $('status').textContent = 'Could not read tabs. Reload the extension and try again.'; }
