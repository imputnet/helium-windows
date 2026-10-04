import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {captureWindows, transferableUrl, validatePayload, buildLauncher, MARKER} from '../extension/core.mjs';

test('captures all normal windows, tab order, pending URLs and duplicates; excludes incognito and apps', () => {
  const result = captureWindows([
    {id: 1, type:'normal', tabs:[
      {index:2, url:'https://example.com/duplicate'},
      {index:0, url:'https://example.com/old', pendingUrl:'https://example.com/new'},
      {index:1, url:'https://example.com/duplicate'},
      {index:3, url:'chrome://newtab/'},
      {index:4, url:'chrome://settings', title:'Settings'},
      {index:5, url:'chrome-extension://abc/page.html'},
    ]},
    {id:2, type:'normal', tabs:[{index:0,url:'file:///C:/test.html'}]},
    {id:3, type:'normal', incognito:true, tabs:[{index:0,url:'https://private.example/'}]},
    {id:4, type:'popup', tabs:[{index:0,url:'https://app.example/'}]}
  ]);
  assert.deepEqual(result.payload.windows.map((window) => window.urls), [
    ['https://example.com/new','https://example.com/duplicate','https://example.com/duplicate','about:blank'],
    ['file:///C:/test.html']
  ]);
  assert.equal(result.skipped.length, 2);
  assert.equal(result.payload.windows.length, 2);
});

test('rejects custom protocols, control characters and oversized URLs', () => {
  for (const raw of ['javascript:alert(1)','data:text/html,hi','blob:https://example.com/id','ms-settings:foo',
    '--user-data-dir=bad','https://example.com/\ncommand','https://example.com/'+ 'a'.repeat(24000)]) {
    assert.equal(transferableUrl(raw), null);
  }
  assert.equal(transferableUrl('https://example.com/?q=ação&x=%25!'), 'https://example.com/?q=a%C3%A7%C3%A3o&x=%25!');
  assert.throws(() => validatePayload({format:'chrome-tabs-to-helium',version:1,windows:[{urls:['javascript:alert(1)']}]}), /unsupported/);
});

test('launcher embeds URLs as data, never shell text, and round trips Unicode and shell characters', async () => {
  const template = await readFile(new URL('../extension/launcher.ps1.txt', import.meta.url), 'utf8');
  const urls = ['https://example.com/?x=%22%20%26%20calc.exe&y=$(&z=100%25!','https://example.com/ação'];
  const payload = captureWindows([{type:'normal',tabs:urls.map((url,index) => ({url,index}))}]).payload;
  const launcher = buildLauncher(payload, template);
  assert.ok(!launcher.includes(urls[0]));
  assert.equal(launcher.split(MARKER).length, 2, 'batch reader must find only the program marker');
  const data = launcher.match(/FromBase64String\('([A-Za-z0-9+/=]+)'\)/)[1];
  assert.deepEqual(JSON.parse(Buffer.from(data,'base64').toString('utf8')), payload);
  assert.throws(() => buildLauncher(payload, '@@TAB_PAYLOAD@@ @@TAB_PAYLOAD@@'), /template/);
});
