"""Read-only Win32 process snapshot (GitHub Windows lab; no process killing)."""
import ctypes
from ctypes import wintypes
import os
import sys

TH32CS_SNAPPROCESS = 2
CANDIDATES = {'powershell.exe','pwsh.exe','cmd.exe','conhost.exe',
              'git.exe','fotomag-headless-broker-win64.exe','openconsole.exe'}


def snapshot() -> dict[int, dict]:
    if sys.platform != 'win32' or os.getenv('GITHUB_ACTIONS') != 'true' or os.getenv('RUNNER_ENVIRONMENT') != 'github-hosted':
        raise RuntimeError('ONLY_GITHUB_HOSTED_WINDOWS_PROCESS_SNAPSHOT')
    k=ctypes.WinDLL('kernel32', use_last_error=True)
    k.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD]
    k.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    k.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.c_void_p]
    k.Process32FirstW.restype=wintypes.BOOL
    k.Process32NextW.argtypes=[wintypes.HANDLE,ctypes.c_void_p]
    k.Process32NextW.restype=wintypes.BOOL
    k.CloseHandle.argtypes=[wintypes.HANDLE]
    class PE(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('usage',wintypes.DWORD),('pid',wintypes.DWORD),
                  ('heap',ctypes.c_size_t),('module',wintypes.DWORD),('threads',wintypes.DWORD),
                  ('ppid',wintypes.DWORD),('priority',wintypes.LONG),('flags',wintypes.DWORD),
                  ('exe',wintypes.WCHAR*260)]
    out={}
    h=k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0)
    if not h or h==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry=PE();entry.size=ctypes.sizeof(entry)
        ok=k.Process32FirstW(h,ctypes.byref(entry))
        while ok:
            name=str(entry.exe).lower()
            if name in CANDIDATES:
                out[int(entry.pid)]={'pid':int(entry.pid),'ppid':int(entry.ppid),'name':name}
            ok=k.Process32NextW(h,ctypes.byref(entry))
    finally:k.CloseHandle(h)
    return out


def delta(before,after):
    return {'existing_before':len(before),'existing_after':len(after),
            'new_candidates':[v for pid,v in after.items() if pid not in before],
            'disappeared_candidates':[v for pid,v in before.items() if pid not in after],
            'isolation_note':'Candidate processes on shared hosted runner; not proof of ownership or memory/handle leaks.'}
