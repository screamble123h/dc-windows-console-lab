import test from 'node:test';
import assert from 'node:assert/strict';
import {planHeadlessBroker, optionalHeadlessBroker, encodeMultilinePowerShell} from '../dist/utils/windows-headless-broker.js';

const BROKER = 'C:\\lab\\fotomag-headless-broker-win64.exe';
const PS = 'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe';
const CMD = 'C:\\Windows\\System32\\cmd.exe';
const plan = {executable:PS,args:['-Command','Write-Output ok'],useShellOption:false};
const exists = p => p === BROKER;
function decode(broker) {return JSON.parse(Buffer.from(broker.args[0], 'base64url').toString('utf8'));}

test('feature remains OFF for all existing Windows v0.3.1 sessions unless explicitly opted in',()=>{
  assert.equal(optionalHeadlessBroker(plan, PS, 'Write-Output ok',true,{},exists),plan);
  assert.equal(optionalHeadlessBroker(plan, PS, 'Write-Output ok',false,{
    DC_WINDOWS_HEADLESS_BROKER:'1',DC_WINDOWS_HEADLESS_BROKER_PATH:BROKER},exists),plan);
});

test('headless broker unwraps exact JSON payload and preserves both output channel intent and CMD verbatim mode',()=>{
  const r = planHeadlessBroker({executable:CMD,args:['/c','echo a & echo b'],windowsVerbatim:true,useShellOption:false}, BROKER, true,true,exists);
  assert.equal(r.executable,BROKER);
  assert.equal(r.useShellOption,false);
  assert.equal(r.windowsVerbatim,false);
  assert.deepEqual(decode(r),{protocol:1,executable:CMD,args:['/c','echo a & echo b'],verbatim:true,killTree:false});
});

test('multiline PowerShell UTF-16LE roundtrip preserves exact command bytes and shell symbols',()=>{
  const script = "$repo='D:\\Test Folder'\r\n$git='C:\\Program Files\\Git\\cmd\\git.exe'\n& $git -C $repo status --short 2>&1 | Select-Object -First 5\nWrite-Output 'абв\u00e9 1'";
  const encoded=encodeMultilinePowerShell(PS,script,true);
  assert.equal(encoded[0],'-EncodedCommand');
  assert.equal(Buffer.from(encoded[1],'base64').toString('utf16le'),script);
  const result=optionalHeadlessBroker(plan, PS, script,true,{
    DC_WINDOWS_HEADLESS_BROKER:'1',DC_WINDOWS_HEADLESS_BROKER_PATH:BROKER},exists);
  assert.equal(result.executable,BROKER);
  const payload=decode(result);
  assert.deepEqual(payload.args,encoded);
  assert.equal(Buffer.from(payload.args[1],'base64').toString('utf16le'),script);
});

test('explicit multiline child Git and CMD remains unchanged in commands and no extra PowerShell wrapper is inserted by broker',()=>{
  const scripts=[
    `Get-Date\n& git.exe --version\nexit $LASTEXITCODE`,
    `Write-Output start\ncmd.exe /d /c "echo child"\nWrite-Output done`,
    `Get-Item "D:\\tmp" 2>&1 | Select-Object -First 3\nWrite-Error demo`,
    `Write-Output alpha\nWrite-Output beta\nWrite-Output gamma`,
  ];
  for(const script of scripts){
    const result=optionalHeadlessBroker(plan, PS, script,true,{
      DC_WINDOWS_HEADLESS_BROKER:'1',DC_WINDOWS_HEADLESS_BROKER_PATH:BROKER},exists);
    const payload=decode(result);
    assert.equal(Buffer.from(payload.args[1],'base64').toString('utf16le'),script);
  }
});

test('interactive sessions retain their input stream; no unsafe encoding if no newline',()=>{
  const orig={...plan,args:['-Command','powershell -NoProfile -NoLogo']};
  const result=optionalHeadlessBroker(orig,PS,'powershell -NoProfile -NoLogo',true,{
    DC_WINDOWS_HEADLESS_BROKER:'1',DC_WINDOWS_HEADLESS_BROKER_PATH:BROKER},exists);
  assert.deepEqual(decode(result).args,orig.args);
});

test('optional job cleanup is an explicit lab choice not a silent behavior change',()=>{
  const r = planHeadlessBroker(plan,BROKER,true,true,exists,true);
  assert.equal(decode(r).killTree,true);
  assert.equal(decode(planHeadlessBroker(plan,BROKER,true,true,exists)).killTree,false);
});

test('fail closed when broker not installed or invalid; never run an uncontained legacy command as fallback',()=>{
  assert.throws(()=>planHeadlessBroker(plan,'C:\\bad\\missing.exe',true,true,exists),/NOT_INSTALLED/);
  assert.throws(()=>planHeadlessBroker(plan,'broker.exe',true,true,exists),/INVALID_PATH/);
  assert.throws(()=>planHeadlessBroker({...plan,useShellOption:'powershell.exe'},BROKER,true,true,exists),/FALLBACK_UNSUPPORTED/);
  assert.throws(()=>planHeadlessBroker({...plan,executable:'powershell.exe'},BROKER,true,true,exists),/VERIFIED_EXE/);
  assert.equal(planHeadlessBroker(plan,BROKER,false,true,exists),null);
  assert.equal(planHeadlessBroker(plan,BROKER,true,false,exists),null);
});

test('long broker request rejected instead of falling back to visible console',()=>{
  const long={...plan,args:['-Command','abc'.repeat(12000)]};
  assert.throws(()=>planHeadlessBroker(long,BROKER,true,true,exists),/PAYLOAD_TOO_LONG/);
});

test('encoded payload rejects NUL and excessive encoded command lengths rather than corrupting a script',()=>{
  assert.equal(encodeMultilinePowerShell(PS,'a\u0000\nb',true),null);
  assert.equal(encodeMultilinePowerShell(PS,'a\n'+'a'.repeat(10000),true),null);
  assert.equal(encodeMultilinePowerShell(CMD,'a\nb',true),null);
  assert.equal(encodeMultilinePowerShell(PS,'a\nb',false),null);
});

test('1024 deterministic multiline scripts preserve the original UTF-16 code units, including quoted Git paths and redirection',()=>{
  for(let i=0;i<1024;i++){
    const script=`$name='FotoMag-${i}'\r\n$git='C:\\Program Files\\Git\\cmd\\git.exe'\n& $git -C 'D:\\Path With Spaces' status --short 2>&1\nWrite-Output (\"$name : \\${i}\")`;
    const encoded=encodeMultilinePowerShell(PS,script,true);
    assert.equal(Buffer.from(encoded[1],'base64').toString('utf16le'),script);
  }
});


test('unsupported custom Windows shell refuses opt-in instead of silently using a potentially visible different process',()=>{
  assert.throws(()=>optionalHeadlessBroker(plan, 'C:\\Program Files\\Git\\bin\\bash.exe','echo hello',true,{
    DC_WINDOWS_HEADLESS_BROKER:'1',DC_WINDOWS_HEADLESS_BROKER_PATH:BROKER},exists),/NATIVE_SHELL_ONLY/);
});
