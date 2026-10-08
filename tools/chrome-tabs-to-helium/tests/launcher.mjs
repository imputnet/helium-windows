import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtemp, readFile, writeFile, mkdir, readdir, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {buildLauncher, transferableUrl} from '../extension/core.mjs';

if (process.platform !== 'win32') throw Error('Windows launcher test requires Windows.');
const temp = await mkdtemp(path.join(tmpdir(),'helium-tabs-test-'));
const recorder = path.join(temp, 'argument recorder & fixture.exe');
const records = path.join(temp, 'records');
await mkdir(records);
const template = await readFile(new URL('../extension/launcher.ps1.txt',import.meta.url),'utf8');
const run = (exe,args,options={}) => new Promise((resolve,reject) => {
  const child = spawn(exe,args,{...options,windowsHide:true,stdio:['ignore','pipe','pipe']});
  let output=''; child.stdout.on('data',(data)=> {output+=data;}); child.stderr.on('data',(data)=> {output+=data;});
  child.on('error',reject); child.on('exit',(code)=> { if(code !== 0) reject(Error(`Exit ${code}: ${output}`)); else resolve(output); });
});
try {
  const compile = path.join(temp,'compile.ps1');
  await writeFile(compile, String.raw`Add-Type -OutputAssembly $env:LOCAL_TAB_TRANSFER_HELIUM -OutputType ConsoleApplication -TypeDefinition @'
using System;
using System.IO;
using System.Text;
public class Recorder {
 public static void Main(string[] args) {
  string[] lines = new string[args.Length];
  for(int i=0;i<args.Length;i++) lines[i] = Convert.ToBase64String(Encoding.UTF8.GetBytes(args[i]));
  File.WriteAllLines(Path.Combine(Environment.GetEnvironmentVariable("LOCAL_TAB_TRANSFER_RECORD"), Guid.NewGuid().ToString()+".txt"), lines);
 }
}
'@
`);
  const env = {...process.env,LOCAL_TAB_TRANSFER_HELIUM:recorder,LOCAL_TAB_TRANSFER_RECORD:records};
  await run('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File',compile],{env});
  const urls = [
    'https://example.com/?quote=%22&command=%26calc.exe&literal=$(&percent=100%25!&single=\'&backslash=\\',
    'https://example.com/unicode-%C3%A7%C3%A3o',
    'file:///C:/My%20Files/test.html', 'about:blank'
  ].map(transferableUrl);
  const payload = {format:'chrome-tabs-to-helium',version:1,windows:[{urls},{urls:['https://example.com/duplicate','https://example.com/duplicate']}]};
  const launcherPath = path.join(temp, "launcher's & ! tabs.cmd");
  await writeFile(launcherPath,buildLauncher(payload,template),'utf8');
  await run(path.join(process.env.SystemRoot,'System32','cmd.exe'),['/d','/s','/c',`""${launcherPath}""`],
    {env,windowsVerbatimArguments:true});
  // Wait for short-lived synthetic child processes to flush their argument records.
  let files=[];
  for(let i=0;i<40;i++) { files=await readdir(records); if(files.length===2) break; await new Promise((resolve)=>setTimeout(resolve,50)); }
  assert.equal(files.length,2);
  const launches = await Promise.all(files.map(async(file)=>(await readFile(path.join(records,file),'utf8')).trim().split(/\r?\n/).map((line)=>Buffer.from(line,'base64').toString('utf8'))));
  assert.ok(launches.some((args)=>JSON.stringify(args)===JSON.stringify(['--new-window',...urls])));
  assert.ok(launches.some((args)=>JSON.stringify(args)===JSON.stringify(['--new-window','https://example.com/duplicate','https://example.com/duplicate'])));

  for (const file of files) await rm(path.join(records,file));
  const longUrls = Array.from({length:40},(_,i)=>`https://example.com/${i}?padding=${'a'.repeat(1100)}`);
  await writeFile(launcherPath,buildLauncher({format:'chrome-tabs-to-helium',version:1,windows:[{urls:longUrls}]},template));
  await run(path.join(process.env.SystemRoot,'System32','cmd.exe'),['/d','/s','/c',`""${launcherPath}""`],
    {env,windowsVerbatimArguments:true});
  for(let i=0;i<40;i++) { files=await readdir(records); if(files.length===2) break; await new Promise((resolve)=>setTimeout(resolve,50)); }
  assert.equal(files.length,2,'large snapshot splits into safe command lines');
  const batches = await Promise.all(files.map(async(file)=>(await readFile(path.join(records,file),'utf8')).trim().split(/\r?\n/).map((line)=>Buffer.from(line,'base64').toString('utf8')).slice(1)));
  assert.deepEqual(batches.flat().sort(),longUrls.sort());
  console.log('PASS: double-click-equivalent CMD execution, executable path with spaces and &, exact URL argument boundaries, shell characters, trailing backslash, Unicode, duplicate tabs, window separation, command-size batching. No browser profiles touched.');
} finally {
  assert.equal(path.dirname(path.resolve(temp)),path.resolve(tmpdir()));
  assert.ok(path.basename(temp).startsWith('helium-tabs-test-'));
  await rm(temp,{recursive:true,force:true});
}
