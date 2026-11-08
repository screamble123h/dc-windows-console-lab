import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';

async function execDirect(payload,code=0){
  return await new Promise((resolve,reject)=>{
    const child=spawn(process.execPath,['-e',`process.stdout.write(${JSON.stringify(payload)});process.stderr.write('err');process.exit(${code})`],{
      shell:false,windowsHide:true,stdio:['pipe','pipe','pipe']
    });
    let stdout='',stderr='';
    child.stdout.setEncoding('utf8');child.stderr.setEncoding('utf8');
    child.stdout.on('data',s=>stdout+=s);child.stderr.on('data',s=>stderr+=s);
    child.on('error',reject);
    child.on('close',exitCode=>resolve({stdout,stderr,exitCode}));
  });
}

test('direct one-process non-shell commands preserve stdout, stderr and exit code (Linux only)',async()=>{
  const result=await execDirect('LAB_STDOUT',23);
  assert.deepEqual(result,{stdout:'LAB_STDOUT',stderr:'err',exitCode:23});
});

test('30 repeated local direct starts preserve captured streams (NOT Windows UI evidence)',async()=>{
  for(let i=0;i<30;i++){
    const result=await execDirect(`round=${i}`);
    assert.deepEqual(result,{stdout:`round=${i}`,stderr:'err',exitCode:0});
  }
});
