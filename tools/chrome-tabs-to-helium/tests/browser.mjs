import {chromium} from 'playwright-core';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {spawn} from 'node:child_process';
import {mkdtemp, readFile, writeFile, readdir, rm} from 'node:fs/promises';
import {tmpdir,homedir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const temp=await mkdtemp(path.join(tmpdir(),'helium-live-tabs-test-'));
const server=createServer((req,res)=>{res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>Synthetic tab fixture</title><h1>Tab fixture</h1>');});
await new Promise((resolve)=>server.listen(0,'127.0.0.1',resolve));
const site=`http://127.0.0.1:${server.address().port}`;
const run=(exe,args,options={})=>new Promise((resolve,reject)=>{
  const child=spawn(exe,args,{...options,windowsHide:true,stdio:['ignore','pipe','pipe']});let output='';
  child.stdout.on('data',(data)=>{output+=data;});child.stderr.on('data',(data)=>{output+=data;});
  child.on('error',reject);child.on('exit',(code)=>code===0?resolve(output):reject(Error(`Exit ${code}: ${output}`)));
});
let source,target,targetBrowser,targetProcess;
try {
  const cache=path.join(homedir(),'AppData','Local','ms-playwright');
  const versions=(await readdir(cache)).filter((name)=>/^chromium-\d+$/.test(name)).sort((a,b)=>Number(b.split('-')[1])-Number(a.split('-')[1]));
  const chrome=process.env.SESSION_TRANSFER_CHROMIUM || path.join(cache,versions[0],'chrome-win64','chrome.exe');
  const helium=process.env.TAB_TRANSFER_TEST_HELIUM || path.join(process.env.LOCALAPPDATA,'imput','Helium','Application','chrome.exe');
  const extensionPath=path.join(root,'extension');
  source=await chromium.launchPersistentContext(path.join(temp,'source'),{executablePath:chrome,headless:true,acceptDownloads:true,
    args:[`--disable-extensions-except=${extensionPath}`,`--load-extension=${extensionPath}`]});
  const manager=source.pages()[0];await manager.goto('chrome://extensions');
  const extensionId=await manager.evaluate(()=>{
    const manager=document.querySelector('extensions-manager');
    const list=manager.shadowRoot.querySelector('extensions-item-list');
    return [...list.shadowRoot.querySelectorAll('extensions-item')].find((item)=>item.shadowRoot.querySelector('#name').textContent.trim()==='Chrome Tabs to Helium').id;
  });
  const popup=await source.newPage();await popup.goto(`chrome-extension://${extensionId}/popup.html`);
  const urls=[`${site}/first?q=%22&safe=%26&percent=100%25!`,`${site}/duplicate`,`${site}/duplicate`,`${site}/unicode-%C3%A7%C3%A3o`];
  await popup.evaluate(async(urls)=>{
    await chrome.windows.create({type:'normal',url:urls.slice(0,3)});
    await chrome.windows.create({type:'normal',url:urls.slice(3)});
  },urls);
  // Capture happens on Save, not merely when the popup initially opened.
  const downloadPromise=popup.waitForEvent('download');await popup.locator('#save').evaluate((button)=>{button.disabled=false;button.click();});
  const download=await downloadPromise;
  const launcherPath=path.join(temp,'live-export.cmd');await download.saveAs(launcherPath);
  const launcher=await readFile(launcherPath,'utf8');
  const payload=JSON.parse(Buffer.from(launcher.match(/FromBase64String\('([A-Za-z0-9+/=]+)'\)/)[1],'base64').toString('utf8'));
  assert.deepEqual(payload.windows.map((window)=>window.urls),[urls.slice(0,3),urls.slice(3)]);
  assert.match(await popup.locator('#count').innerText(),/4 tabs in 2 windows/);
  assert.match(await popup.locator('#skipped-count').innerText(),/2 tabs cannot transfer/);
  await popup.screenshot({path:path.join(root,'tests','preview.png')});

  const targetProfile=path.join(temp,'helium-target');
  // Start Helium normally, then attach. Playwright's own launch flags can prevent
  // Windows' existing-browser notification path from accepting a second launch.
  const portServer=createServer();await new Promise((resolve)=>portServer.listen(0,'127.0.0.1',resolve));
  const debugPort=portServer.address().port;await new Promise((resolve)=>portServer.close(resolve));
  targetProcess=spawn(helium,[`--user-data-dir=${targetProfile}`,`--remote-debugging-port=${debugPort}`,
    '--no-first-run','--no-default-browser-check','--start-minimized','about:blank'],{windowsHide:true,stdio:'ignore'});
  let ready=false;
  for(let i=0;i<100;i++) {
    try { const response=await fetch(`http://127.0.0.1:${debugPort}/json/version`);if(response.ok){ready=true;break;} } catch {}
    await new Promise((resolve)=>setTimeout(resolve,100));
  }
  assert.equal(ready,true,'isolated Helium is ready');
  targetBrowser=await chromium.connectOverCDP(`http://127.0.0.1:${debugPort}`);
  target=targetBrowser.contexts()[0];
  // Test-only bridge forces the launcher into this temporary Helium profile.
  // The real generated launcher itself does not change profiles or browser settings.
  const bridge=path.join(temp,'isolated-helium-bridge.exe');
  const compile=path.join(temp,'bridge.ps1');
  await writeFile(compile,String.raw`Add-Type -OutputAssembly $env:LOCAL_TAB_TRANSFER_HELIUM -OutputType ConsoleApplication -TypeDefinition @'
using System;
using System.Diagnostics;
using System.Text;
using System.Text.RegularExpressions;
using System.IO;
public class IsolatedHeliumBridge {
 static string Quote(string value) {
  return "\"" + Regex.Replace(Regex.Replace(value, "(\\\\*)\"", "$1$1\\\""), "(\\\\+)$", "$1$1") + "\"";
 }
 public static void Main(string[] args) {
  StringBuilder line = new StringBuilder("--start-minimized " + Quote("--user-data-dir=" + Environment.GetEnvironmentVariable("TAB_TRANSFER_TEST_PROFILE")));
  foreach(string arg in args) line.Append(" ").Append(Quote(arg));
  File.AppendAllText(Environment.GetEnvironmentVariable("TAB_TRANSFER_TEST_LOG"), line.ToString() + Environment.NewLine);
  Process process = Process.Start(new ProcessStartInfo(Environment.GetEnvironmentVariable("TAB_TRANSFER_TEST_BROWSER"), line.ToString()) {UseShellExecute=false, WindowStyle=ProcessWindowStyle.Hidden});
  if (process.WaitForExit(5000)) File.AppendAllText(Environment.GetEnvironmentVariable("TAB_TRANSFER_TEST_LOG"), "Exit: " + process.ExitCode.ToString() + Environment.NewLine);
 }
}
'@
`);
  const bridgeLog=path.join(temp,'bridge.log');
  const env={...process.env,LOCAL_TAB_TRANSFER_HELIUM:bridge,TAB_TRANSFER_TEST_PROFILE:targetProfile,TAB_TRANSFER_TEST_BROWSER:helium,TAB_TRANSFER_TEST_LOG:bridgeLog};
  await run('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File',compile],{env});
  await run(path.join(process.env.SystemRoot,'System32','cmd.exe'),['/d','/s','/c',`""${launcherPath}""`],{env,windowsVerbatimArguments:true});
  let actual=[];
  for(let i=0;i<100;i++) {
    actual=target.pages().map((page)=>page.url()).filter((url)=>url.startsWith(site));
    if(actual.length===4) break;
    await new Promise((resolve)=>setTimeout(resolve,100));
  }
  if(actual.length!==4) {
    console.log('Bridge arguments:',await readFile(bridgeLog,'utf8'));
    console.log('Helium pages:',target.pages().map((page)=>page.url()));
  }
  assert.deepEqual(actual.sort(),[...urls].sort());
  const destinationWindows=new Map();
  for(const page of target.pages().filter((page)=>page.url().startsWith(site))) {
    const cdp=await target.newCDPSession(page);
    const {windowId}=await cdp.send('Browser.getWindowForTarget');await cdp.detach();
    if(!destinationWindows.has(windowId))destinationWindows.set(windowId,[]);
    destinationWindows.get(windowId).push(page.url());
  }
  const groups=[...destinationWindows.values()];
  assert.equal(groups.length,2,'each source window opens separately');
  assert.ok(groups.some((group)=>JSON.stringify(group)===JSON.stringify(urls.slice(0,3))),'first window retains order and duplicates');
  assert.ok(groups.some((group)=>JSON.stringify(group)===JSON.stringify(urls.slice(3))),'second window retains its tab');
  assert.equal(source.pages().filter((page)=>page.url().startsWith(site)).length,4,'Chrome tabs remain open');
  console.log('PASS: live Chrome extension captures two windows, order, duplicate tabs and special-character URLs; generated CMD opens all four tabs in installed Helium using an isolated test profile. Chrome tabs remain open.');
} finally {
  if(source)await source.close();
  if(targetBrowser) {
    try { const cdp=await targetBrowser.newBrowserCDPSession();await cdp.send('Browser.close'); } catch {}
    await targetBrowser.close();
  }
  if(targetProcess && targetProcess.exitCode === null) {
    await new Promise((resolve)=>{targetProcess.once('exit',resolve);setTimeout(resolve,3000);});
    if(targetProcess.exitCode===null)targetProcess.kill();
  }
  await new Promise((resolve)=>server.close(resolve));
  assert.equal(path.dirname(path.resolve(temp)),path.resolve(tmpdir()));
  assert.ok(path.basename(temp).startsWith('helium-live-tabs-test-'));
  await rm(temp,{recursive:true,force:true,maxRetries:10,retryDelay:100});
}
