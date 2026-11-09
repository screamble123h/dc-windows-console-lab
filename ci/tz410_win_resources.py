#!/usr/bin/env python3
"""Win32 resource snapshot for a PUBLIC GitHub-hosted Windows lab ONLY.

Snapshot new FMDCLab_ desktop objects and candidate process PIDs. No mutation.
Windows sessions other than the runner's own window station are not enumerated.
"""
from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
from datetime import datetime,timezone
from tz49_process_probe import snapshot as process_snapshot


def run():
    if not (sys.platform=='win32' and os.getenv('GITHUB_ACTIONS')=='true'
            and os.getenv('RUNNER_ENVIRONMENT')=='github-hosted'
            and os.getenv('RUNNER_OS')=='Windows'
            and os.getenv('GITHUB_REPOSITORY')=='screamble123h/dc-windows-console-lab'):
        raise SystemExit('NOT_AN_ISOLATED_GITHUB_WINDOWS_LAB')
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    opts=parser.parse_args()
    u=ctypes.WinDLL('user32',use_last_error=True)
    CB=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.LPWSTR,wintypes.LPARAM)
    u.GetProcessWindowStation.restype=wintypes.HANDLE
    u.EnumDesktopsW.argtypes=(wintypes.HANDLE,CB,wintypes.LPARAM)
    u.EnumDesktopsW.restype=wintypes.BOOL
    names=[]
    def cb(name,_):
        names.append(name)
        return True
    h=u.GetProcessWindowStation()
    ok=bool(h and u.EnumDesktopsW(h,CB(cb),0))
    output={'name':'TZ410_RESOURCE_SNAPSHOT','timestamp_utc':datetime.now(timezone.utc).isoformat(),
            'window_station_desktops_enumerated':ok,
            'enumeration_winerror':None if ok else ctypes.get_last_error(),
            'broker_desktop_names':[n for n in names if n.startswith('FMDCLab_')],
            'candidate_processes':list(process_snapshot().values()),
            'note':'Only runner window station; no proof of process tree or remote GUI when access is missing.'}
    opts.output.parent.mkdir(parents=True,exist_ok=True)
    opts.output.write_text(json.dumps(output,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in output.items() if k!='candidate_processes'},indent=2))

if __name__=='__main__':run()
