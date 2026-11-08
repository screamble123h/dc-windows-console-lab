/**
 * Independently isolated Windows GUI lab ONLY: compare genuine upstream
 * Desktop Commander v0.3.1 against the experimental opt-in hidden-desktop
 * broker. No test may execute on PRODUCTION_HOST_REDACTED.
 *
 * Two separate runs are mandatory, with the passive GUI observer operating
 * on the interactive desktop. Run: --mode=baseline, then --mode=broker.
 * Each run executes 10 cases x 10 rounds = 100 attempts.
 */
import os from 'node:os';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const modeArg = process.argv.find(x=>x.startsWith('--mode='));
const mode = modeArg?.slice(7);
if (!['baseline','broker'].includes(mode)) throw Error('EXPLICIT_MODE_REQUIRED: baseline|broker');
const host = os.hostname().toUpperCase();
if (process.platform!=='win32' || process.env.GITHUB_ACTIONS!=='true' ||
    process.env.RUNNER_OS!=='Windows' || process.env.RUNNER_ENVIRONMENT!=='github-hosted') {
  throw Error('REFUSED_PRODUCTION_OR_NONWINDOWS: no processes launched');
}
if (process.env.FOTOMAG_ISOLATED_WINDOWS_LAB!=='YES'||
    process.env.FOTOMAG_VM_EVIDENCE_SAFE!=='YES') {
  throw Error('LAB_OPT_IN_MISSING: no processes launched');
}
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..','..');
const base = mode==='baseline' ? await import('../../baseline/dist/utils/shell.js') : await import('../../dist/utils/shell.js');
const { getShellSpawnArgs, resolveShellPath } = base;
const git = resolveShellPath('git.exe');
if (!git) throw Error('GIT_REQUIRED_FOR_FULL_MATRIX');
const broker = path.join(root,'native','windows-headless-broker','fotomag-headless-broker-win64.exe');
if(mode==='broker'&&!fs.existsSync(broker))throw Error('BROKER_BINARY_MISSING');
const vars={...process.env};
if(mode==='broker'){
  vars.DC_WINDOWS_HEADLESS_BROKER='1';
  vars.DC_WINDOWS_HEADLESS_BROKER_PATH=broker;
  vars.DC_WINDOWS_HEADLESS_BROKER_KILL_TREE='1'; // Lab ONLY: terminate all owned descendants on exit
  vars.FOTOMAG_LAB_EVIDENCE_DIR=path.join(root,'test','windows','lab_pid_evidence');
  process.env.DC_WINDOWS_HEADLESS_BROKER='1';
  process.env.DC_WINDOWS_HEADLESS_BROKER_PATH=broker;
  process.env.DC_WINDOWS_HEADLESS_BROKER_KILL_TREE='1';
}else {
  delete process.env.DC_WINDOWS_HEADLESS_BROKER;
  delete process.env.DC_WINDOWS_HEADLESS_BROKER_PATH;
  delete process.env.DC_WINDOWS_HEADLESS_BROKER_KILL_TREE;
}
const specList=[
  {id:'MULTILINE_GIT',shell:'powershell.exe',command:"Write-Output LAB_START\r\n& git.exe --version\nWrite-Output LAB_END",stdout:['LAB_START','git version','LAB_END'],code:0},
  {id:'MULTILINE_VARIABLE_GIT',shell:'powershell.exe',command:"$git='git.exe'\n& $git --version 2>&1 | Select-Object -First 1\nWrite-Output LAB_END",stdout:['git version','LAB_END'],code:0},
  {id:'NESTED_POWERSHELL',shell:'powershell.exe',command:"powershell.exe -NoProfile -NonInteractive -Command \"Write-Output LAB_CHILD\"",stdout:['LAB_CHILD'],code:0},
  {id:'NESTED_CMD',shell:'powershell.exe',command:'cmd.exe /d /c echo LAB_CMD',stdout:['LAB_CMD'],code:0},
  {id:'DIRECT_CMD',shell:'cmd.exe',command:'echo LAB_CMD',stdout:['LAB_CMD'],code:0},
  {id:'POWERHELL_NATIVE_GIT',shell:'powershell.exe',command:'git.exe --version',stdout:['git version'],code:0},
  {id:'MULTILINE_REDIRECTION',shell:'powershell.exe',command:"Write-Output 'LAB_FIRST' 2>&1 | Out-String\nWrite-Output 'LAB_SECOND'",stdout:['LAB_FIRST','LAB_SECOND'],code:0},
  {id:'MULTILINE_SEQUENTIAL',shell:'powershell.exe',command:"$a=2\n$b=3\nWrite-Output ('LAB_SUM='+($a+$b))",stdout:['LAB_SUM=5'],code:0},
  {id:'STDERR_EXIT',shell:'powershell.exe',command:"[Console]::Error.WriteLine('LAB_STDERR'); exit 17",stderr:['LAB_STDERR'],code:17},
  {id:'INTERACTIVE',shell:'powershell.exe',command:'powershell.exe -NoProfile -NoLogo',interactive:"Write-Output ('LAB_'+'INTERACTIVE')\r\nexit\r\n",stdout:['LAB_INTERACTIVE'],code:0},
];
async function runOne(spec,iteration){
 const at=Date.now();let cfg;
 try{cfg=getShellSpawnArgs(spec.shell,spec.command)}catch(e){return {id:spec.id,iteration,status:'PLANNER_ERROR',error:String(e)}}
 if (mode==='broker' && !path.resolve(cfg.executable).toLowerCase().includes('headless-broker')){
   return {id:spec.id,iteration,status:'BROKER_NOT_SELECTED',exe:cfg.executable};
 }
 return await new Promise(resolve=>{
  let done=false;let stdout='',stderr='';let child;let timer=null;
  const finish=(state,code,error=null)=>{
    if(done)return;done=true;clearTimeout(timer);
    const outputOk=spec.stdout?.every(s=>stdout.includes(s))??true;
    const errOk=spec.stderr?.every(s=>stderr.includes(s))??true;
    resolve({id:spec.id,iteration,pid:child?.pid,status:state,exit:code,
      outputOk,errOk,pass:state==='CLOSED'&&code===spec.code&&outputOk&&errOk,
      elapsed_ms:Date.now()-at,ended_at:new Date().toISOString(),stderr:stderr.slice(0,180),stdout:stdout.slice(0,180),error});
  };
  try{child=spawn(cfg.executable,cfg.args,{windowsHide:true,shell:cfg.useShellOption||false,
    windowsVerbatimArguments:!!cfg.windowsVerbatim,stdio:['pipe','pipe','pipe'],env:vars});}
  catch(e){return finish('SPAWN_THROW',null,String(e))}
  child.stdout.on('data',b=>stdout+=String(b));
  child.stderr.on('data',b=>stderr+=String(b));
  child.on('error',e=>finish('SPAWN_ERROR',null,String(e)));
  child.on('close',c=>finish('CLOSED',c));
  if(spec.interactive)child.stdin.write(spec.interactive);else child.stdin.end();
  timer=setTimeout(()=>{
    child.kill();finish('TIMEOUT',null);
  },12000);
 });
}
const results=[];
console.log('Isolated Windows CI functional comparison. Foreground GUI evidence must be verified separately.');
await new Promise(resolve=>setTimeout(resolve,5000));
for(let iteration=0;iteration<10;iteration++)for(const spec of specList){
 results.push(await runOne(spec,iteration));
}
const passed=results.filter(x=>x.pass).length;
const manifest={mode,platform:process.platform,host:os.hostname(),at:new Date().toISOString(),
 attempted:results.length,passed,failed:results.length-passed,
 hwndObserverRequired:true,foregroundEvidenceRequired:true,
 independentWindowsOnly:true};
const resultPath=path.join(root,`WINDOWS_LAB_${mode.toUpperCase()}_100.json`);
fs.writeFileSync(resultPath,JSON.stringify({manifest,results},null,2),'utf8');
console.log(JSON.stringify({...manifest,resultPath},null,2));
if(passed!==100)process.exitCode=1;
