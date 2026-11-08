#!/usr/bin/env python3
"""Read-only lab check that no owned broker-launched children remain active.

Requires psutil and real Windows PID evidence. Never attempts termination.
Can be run only after the lab test's normal completion.
"""
from pathlib import Path
import json, os, sys, argparse

if sys.platform != 'win32' or os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted':
    raise SystemExit('REFUSED_NOT_INDEPENDENT_WINDOWS_LAB')
if os.environ.get('FOTOMAG_ISOLATED_WINDOWS_LAB')!='YES':
    raise SystemExit('REFUSED_MISSING_LAB_GATE')
try:
    import psutil
except ImportError:
    raise SystemExit('NOT_VERIFIABLE_WITHOUT_PSUTIL')

p=argparse.ArgumentParser();p.add_argument('evidence_dir',type=Path);args=p.parse_args()
rows=[]
for fp in sorted(args.evidence_dir.glob('lab_pid_*.json')):
    record=json.loads(fp.read_text(encoding='utf-8'))
    pid=record['target_pid']; status='ended'
    try:
        proc=psutil.Process(pid)
        # PID reuse is possible; only count a process created at the time of
        # the launch evidence or within a small race allowance.
        if abs(proc.create_time()-fp.stat().st_mtime)<20 and proc.is_running() and proc.status()!=psutil.STATUS_ZOMBIE:
            status='orphan_running'
    except psutil.NoSuchProcess: pass
    except psutil.Error: status='unverified'
    rows.append({'pid':pid,'status':status})
result={'count':len(rows),'orphan_running':sum(x['status']=='orphan_running' for x in rows),
        'unverified':sum(x['status']=='unverified' for x in rows),'rows':rows}
print(json.dumps(result,indent=2,ensure_ascii=False))
sys.exit(0 if len(rows)>=100 and result['orphan_running']==0 and result['unverified']==0 else 2)
