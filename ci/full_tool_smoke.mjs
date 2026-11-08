/**
 * Real Desktop Commander improved-process-tools.startProcess() integration smoke.
 * GitHub HOSTED Windows only. No Remote MCP enrollment or credentials.
 * No production files, no project commands, and no control over another computer.
 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { pathToFileURL } from 'node:url';

if (process.platform !== 'win32' || process.env.GITHUB_ACTIONS !== 'true' ||
    process.env.RUNNER_OS !== 'Windows' || process.env.RUNNER_ENVIRONMENT !== 'github-hosted') {
  console.error('REFUSED_NOT_GITHUB_HOSTED_WINDOWS');
  process.exit(19);
}
const mode = process.argv.find(x => x.startsWith('--mode='))?.slice(7);
if (!['baseline','broker'].includes(mode)) throw Error('MODE_REQUIRED');
const root=path.resolve(import.meta.dirname,'..');
const file=path.join(root,mode==='baseline'?'upstream-baseline':'upstream-patched','dist','tools','improved-process-tools.js');
const {startProcess,readProcessOutput} = await import(pathToFileURL(file).href);
process.env.FOTOMAG_ISOLATED_WINDOWS_LAB='YES';
process.env.FOTOMAG_VM_EVIDENCE_SAFE='YES';
if(mode==='broker'){
  process.env.DC_WINDOWS_HEADLESS_BROKER='1';
  process.env.DC_WINDOWS_HEADLESS_BROKER_KILL_TREE='1';
  process.env.DC_WINDOWS_HEADLESS_BROKER_PATH=path.join(root,'lab','native','windows-headless-broker','fotomag-headless-broker-win64.exe');
}else{
  delete process.env.DC_WINDOWS_HEADLESS_BROKER;
  delete process.env.DC_WINDOWS_HEADLESS_BROKER_PATH;
  delete process.env.DC_WINDOWS_HEADLESS_BROKER_KILL_TREE;
}
const cases=[
  {id:'MULTILINE_TOOL',cmd:"Write-Output 'LAB_TOOL_BEGIN'\n& git.exe --version 2>&1 | Select-Object -First 1\nWrite-Output 'LAB_TOOL_END'",markers:['LAB_TOOL_BEGIN','git version','LAB_TOOL_END']},
  {id:'NESTED_CMD_TOOL',cmd:'cmd.exe /d /c echo LAB_TOOL_CMD',markers:['LAB_TOOL_CMD']},
  {id:'SIMPLE_TOOL',cmd:"Write-Output 'LAB_SIMPLE_OK'",markers:['LAB_SIMPLE_OK']},
];
const outcomes=[];
for(const c of cases){
  const at=Date.now();let chunks='';let error=null;let pid=null;
  try{
    const started=await startProcess({command:c.cmd,shell:'powershell.exe',timeout_ms:3000});
    pid=started?.structuredContent?.pid;
    chunks+=(started?.content||[]).map(z=>z.text||'').join('\n');
    if(!(pid>0)) throw Error('NO_VALID_SESSION_PID: '+chunks.slice(0,300));
    for(let i=0;i<12 && !c.markers.every(s=>chunks.includes(s));i++){
      const x=await readProcessOutput({pid,timeout_ms:800,offset:0,length:150});
      chunks+='\n'+(x?.content||[]).map(z=>z.text||'').join('\n');
    }
  }catch(e){error=String(e).slice(0,500);}
  outcomes.push({id:c.id,pid,passed:!error&&c.markers.every(s=>chunks.includes(s)),elapsed_ms:Date.now()-at,
                 error,stdout_excerpt:chunks.slice(0,600)});
}
const output={mode,platform:process.platform,github_hosted:true,tool:'improved-process-tools.startProcess',
  total:outcomes.length,passed:outcomes.filter(x=>x.passed).length,outcomes,
  caveat:'Local in-process tool API; not a Remote MCP transport, and no interactive desktop proof.'};
fs.mkdirSync(path.join(root,'evidence'),{recursive:true});
fs.writeFileSync(path.join(root,'evidence',`START_PROCESS_${mode.toUpperCase()}_SMOKE.json`),JSON.stringify(output,null,2));
console.log(JSON.stringify({...output,outcomes:outcomes.map(({id,pid,passed,error,elapsed_ms})=>({id,pid,passed,error,elapsed_ms}))},null,2));
if (output.passed!==output.total) process.exitCode=2;
