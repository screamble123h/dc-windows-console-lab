#!/usr/bin/env python3
"""Windows functional comparison with passive GUI observer; hosted runner only.

The observer measures *this* hosted runner's input desktop. Even a clean run
cannot prove that a human-facing desktop or Remote MCP behaves identically.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def observe_report(path: Path, observer_exit: int | None, stderr: str):
    events=[]
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            try: events.append(json.loads(line))
            except json.JSONDecodeError: continue
    start = next((e for e in events if e.get('event')=='lab_observer_start'),{})
    end = next((e for e in events if e.get('event')=='lab_observer_finished'),{})
    return {'observer_exit':observer_exit,'started':bool(start),'finished':bool(end),
            'ticks':end.get('ticks'),'seconds':end.get('seconds'),
            'new_visible_console_events':end.get('new_visible_console_events'),
            'console_focus_events':end.get('console_focus_events'),
            'baseline_windows':start.get('baseline_window_count'),
            'starting_foreground_hwnd_present':start.get('interactive_foreground_present'),
            'observer_error':stderr[-500:] if stderr else None,
            'measures_hosted_runner_only':True,'human_visible_desktop_proven':False}


def main():
    if not (os.name=='nt' and os.environ.get('GITHUB_ACTIONS')=='true' and
            os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted' and
            os.environ.get('RUNNER_OS')=='Windows'):
        print('REFUSED: GitHub-hosted Windows runner only',file=sys.stderr)
        return 19
    root=Path.cwd()
    lab=root/'lab'
    evidence=root/'evidence'
    evidence.mkdir(exist_ok=True)
    environment=os.environ.copy()
    environment['FOTOMAG_ISOLATED_WINDOWS_LAB']='YES'
    environment['FOTOMAG_VM_EVIDENCE_SAFE']='YES'
    rows=[]
    observations=[]
    for mode in ('baseline','broker'):
        log=evidence/f'GUI_OBSERVER_{mode.upper()}.jsonl'
        obs=subprocess.Popen([sys.executable,str(lab/'test/windows/LAB_CONSOLE_OBSERVER.py'),
                              '--seconds','65','--interval','0.10','--output',str(log)],
                             cwd=lab,env=environment,stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             creationflags=subprocess.CREATE_NO_WINDOW)
        # Let the observer establish baseline before the test process starts.
        time.sleep(1.0)
        start=time.monotonic()
        argv=['node',str(lab/'test/windows/lab-baseline-vs-broker.mjs'),f'--mode={mode}']
        try:
            r=subprocess.run(argv,cwd=lab,env=environment,text=True,
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             timeout=1150,check=False,creationflags=subprocess.CREATE_NO_WINDOW)
            code,out,err=r.returncode,r.stdout,r.stderr
        except subprocess.TimeoutExpired as exc:
            code=124
            out=str(exc.stdout or b'')[-20000:]
            err='TIMEOUT after 1150s\n'+str(exc.stderr or b'')[-20000:]
        (evidence/f'{mode}_stdout.txt').write_text(str(out)[-60000:],encoding='utf-8')
        (evidence/f'{mode}_stderr.txt').write_text(str(err)[-60000:],encoding='utf-8')
        result_path=lab/f'WINDOWS_LAB_{mode.upper()}_100.json'
        result=None
        if result_path.exists():
            result=json.loads(result_path.read_text(encoding='utf-8'))
            (evidence/result_path.name).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        manifest=(result or {}).get('manifest') or {}
        elapsed=round(time.monotonic()-start,2)
        rows.append({'mode':mode,'process_exit':code,'attempted':manifest.get('attempted'),
                     'passed':manifest.get('passed'),'failed':manifest.get('failed'),
                     'seconds':elapsed,'manifest_exists':bool(result)})
        try:
            out_b,err_b=obs.communicate(timeout=80)
            obs_code=obs.returncode
            obs_error=err_b.decode('utf-8','replace') if err_b else ''
        except subprocess.TimeoutExpired:
            obs.kill()
            out_b,err_b=obs.communicate(timeout=10)
            obs_code=124
            obs_error='GUI_OBSERVER_TIMEOUT\n'+err_b.decode('utf-8','replace')
        report=observe_report(log,obs_code,obs_error)
        report.update({'mode':mode,'trial_seconds':elapsed})
        observations.append(report)
        (evidence/f'GUI_OBSERVER_{mode.upper()}_SUMMARY.json').write_text(
            json.dumps(report,indent=2)+'\n',encoding='utf-8')
    broker=next(x for x in rows if x['mode']=='broker')
    success=bool(broker['attempted']==100 and broker['passed']==100 and
                 broker['failed']==0 and broker['process_exit']==0)
    payload={'gitlab_or_azure_rental':False,'actual_windows_functional':True,
             'v4_6_derivative_not_byte_identical':True,'results':rows,
             'functional_broker_100_pass':success,'hosted_runner_gui_observer':observations,
             'remote_mcp_e2e':'NOT_RUN','visible_gui_and_focus':'HOSTED_RUNNER_OBSERVATION_ONLY',
             'deployment_readiness':'NOT_READY'}
    (evidence/'CI_FUNCTIONAL_RESULT.json').write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(payload,indent=2))
    return 0 if success else 2

if __name__=='__main__':
    sys.exit(main())
