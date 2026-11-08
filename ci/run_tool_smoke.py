#!/usr/bin/env python3
"""Invoke real in-process Desktop Commander startProcess on hosted Windows.
Baseline failure is acceptable; broker failure blocks a functional PASS.
"""
import json,os,sys,subprocess
from pathlib import Path
if not (os.name=='nt' and os.environ.get('GITHUB_ACTIONS')=='true' and
        os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted' and
        os.environ.get('RUNNER_OS')=='Windows'):
 print('REFUSED: GitHub-hosted Windows runner only',file=sys.stderr);sys.exit(19)
root=Path.cwd(); e=root/'evidence';e.mkdir(exist_ok=True)
results=[]
for mode in ('baseline','broker'):
 try:
  p=subprocess.run(['node',str(root/'ci/full_tool_smoke.mjs'),f'--mode={mode}'],
                  cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=140)
  code,out,err=p.returncode,p.stdout,p.stderr
 except subprocess.TimeoutExpired:
  code,out,err=124,'','SMOKE_TIMEOUT'
 (e/f'START_PROCESS_{mode.upper()}_SMOKE_STDOUT.txt').write_text(out[-10000:],encoding='utf-8')
 (e/f'START_PROCESS_{mode.upper()}_SMOKE_STDERR.txt').write_text(err[-10000:],encoding='utf-8')
 data=json.loads((e/f'START_PROCESS_{mode.upper()}_SMOKE.json').read_text()) if (e/f'START_PROCESS_{mode.upper()}_SMOKE.json').exists() else {}
 results.append({'mode':mode,'return_code':code,'passed':data.get('passed'),'attempted':data.get('total')})
json.dump(results,(e/'TOOL_API_SMOKE_SUMMARY.json').open('w'),indent=2)
print(json.dumps(results,indent=2))
s=sys.exit(0 if results[-1]['return_code']==0 and results[-1]['passed']==results[-1]['attempted']==3 else 2)
