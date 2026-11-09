#!/usr/bin/env python3
"""Re-run existing v4.6 functional matrix + tool smoke with a passive HWND observer.

Only a public GitHub-hosted STANDARD windows-2022 runner. No remote computer.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from tz49_process_probe import snapshot, delta

if not (sys.platform == 'win32' and os.getenv('GITHUB_ACTIONS') == 'true'
        and os.getenv('RUNNER_OS') == 'Windows' and os.getenv('RUNNER_ENVIRONMENT') == 'github-hosted'
        and os.getenv('FOTOMAG_ISOLATED_WINDOWS_LAB') == 'YES'):
    raise SystemExit('REFUSED_OUTSIDE_GITHUB_WINDOWS_LAB')
root=Path.cwd(); ev=root/'evidence';ev.mkdir(exist_ok=True)
stop=ev/'OBSERVER_STOP.signal';log=ev/'TZ4_9_HWND_OBSERVER.jsonl'
for p in (stop,log):
    if p.exists():p.unlink()

proc=subprocess.Popen([sys.executable,'ci/tz49_gui_observer.py','--output',str(log),
                       '--stop-file',str(stop),'--max-seconds','240','--interval','.08'],
                      cwd=root,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                      creationflags=subprocess.CREATE_NO_WINDOW)
results=[]
process_deltas=[]
try:
    for attempt in range(40):
        if log.exists() and 'observer_start' in log.read_text(encoding='utf8',errors='replace'): break
        if proc.poll() is not None:raise RuntimeError('OBSERVER_FAILED_TO_START')
        time.sleep(.12)
    else: raise RuntimeError('OBSERVER_START_TIMEOUT')
    matrix=[('functional', 'ci/run_functional_windows.py',180),
            ('tool_api','ci/run_tool_smoke.py',90),
            ('clixml','ci/tz49_clixml_probe.py',120)]
    for label, script, seconds in matrix:
        before = snapshot()
        started=time.monotonic()
        try:
            p=subprocess.run([sys.executable,script],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             timeout=seconds,creationflags=subprocess.CREATE_NO_WINDOW,check=False)
            code,so,se=p.returncode,p.stdout,p.stderr
        except subprocess.TimeoutExpired as exc:
            code,so,se=124,exc.stdout or b'',exc.stderr or b''
        (ev/f'TZ4_9_{label}_stdout.txt').write_bytes(so[:150000])
        (ev/f'TZ4_9_{label}_stderr.txt').write_bytes(se[:150000])
        time.sleep(.65)
        after = snapshot()
        process_deltas.append({'test':label, **delta(before,after)})
        results.append({'test':label,'exit':code,'seconds':round(time.monotonic()-started,2),
                        'stdout_bytes':len(so),'stderr_bytes':len(se),'timeout':code==124})
        print(f"{label}: code={code} seconds={results[-1]['seconds']}",flush=True)
        if code !=0: break
finally:
    stop.touch()
    try:obserr=proc.communicate(timeout=8)[1]
    except subprocess.TimeoutExpired:
        proc.kill();obserr=proc.communicate()[1]
    if obserr:
        (ev/'TZ4_9_OBSERVER_STDERR.txt').write_bytes(obserr[:10000])

try:
    events=[json.loads(x) for x in log.read_text(encoding='utf8').splitlines() if x.strip()]
except Exception as err:
    events=[]
last=next((x for x in reversed(events) if x.get('event')=='observer_done'),None)
report={'test':'TZ4_9_WINDOWS_CI','system':'GITHUB_HOSTED_WINDOWS_2022','kind':'functional+CI_GUI_observation_only',
        'matrix':results,'process_candidate_deltas':process_deltas,'observer_exited':proc.returncode,'observer_complete':bool(last),
        'new_visible_console_events':last.get('console_new') if last else None,
        'console_foreground_transitions':last.get('focus_events') if last else None,
        'gui_user_focus_proven':False,'remote_mcp_e2e_proven':False,
        'ready_to_deploy':False,
        'why':'No independently observed interactive workstation; baseline defect not proven.'}
(ev/'TZ4_9_MATRIX_REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
if len(results)<3 or any(z['exit']!=0 for z in results):sys.exit(2)
if not last or proc.returncode!=0:sys.exit(3)
