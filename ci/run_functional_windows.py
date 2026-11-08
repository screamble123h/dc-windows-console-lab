#!/usr/bin/env python3
"""Drive 100 baseline and 100 broker trials only on GitHub-hosted Windows.

This evaluates subprocess exit/output from the v4.6-derived test harness.
No local workstation, GUI user account, Remote MCP connection, or secrets involved.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    if not (os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true' and
            os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted' and
            os.environ.get('RUNNER_OS') == 'Windows'):
        print('REFUSED: GitHub-hosted Windows runner only', file=sys.stderr)
        return 19
    root = Path.cwd()
    lab = root/'lab'
    evidence = root/'evidence'
    evidence.mkdir(exist_ok=True)
    environment = os.environ.copy()
    environment['FOTOMAG_ISOLATED_WINDOWS_LAB'] = 'YES'
    environment['FOTOMAG_VM_EVIDENCE_SAFE'] = 'YES'
    rows = []
    for mode in ('baseline', 'broker'):
        start = time.monotonic()
        argv = ['node', str(lab/'test/windows/lab-baseline-vs-broker.mjs'), f'--mode={mode}']
        try:
            r = subprocess.run(argv, cwd=lab, env=environment, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=1150, check=False)
            code, out, err = r.returncode, r.stdout, r.stderr
        except subprocess.TimeoutExpired as exc:
            code = 124
            out = str(exc.stdout or b'')[-20000:]
            err = 'TIMEOUT after 1150s\n' + str(exc.stderr or b'')[-20000:]
        (evidence/f'{mode}_stdout.txt').write_text(str(out)[-60000:], encoding='utf-8')
        (evidence/f'{mode}_stderr.txt').write_text(str(err)[-60000:], encoding='utf-8')
        result_path = lab/f'WINDOWS_LAB_{mode.upper()}_100.json'
        result = None
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding='utf-8'))
            (evidence/result_path.name).write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        manifest = (result or {}).get('manifest') or {}
        rows.append({'mode':mode,'process_exit':code,'attempted':manifest.get('attempted'),
                     'passed':manifest.get('passed'), 'failed':manifest.get('failed'),
                     'seconds':round(time.monotonic()-start,2),
                     'manifest_exists':bool(result)})
    broker = next(x for x in rows if x['mode']=='broker')
    # Baseline is allowed to fail. Its failures may reproduce the nested-shell issue.
    success = bool(broker['attempted']==100 and broker['passed']==100 and
                   broker['failed']==0 and broker['process_exit']==0)
    payload = {'gitlab_or_azure_rental':False,'actual_windows_functional':True,
               'v4_6_derivative_not_byte_identical':True,
               'results':rows, 'functional_broker_100_pass':success,
               'remote_mcp_e2e':'NOT_RUN', 'visible_gui_and_focus':'NOT_PROVEN',
               'deployment_readiness':'NOT_READY'}
    (evidence/'CI_FUNCTIONAL_RESULT.json').write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(payload,indent=2))
    return 0 if success else 2

if __name__=='__main__':
    sys.exit(main())
