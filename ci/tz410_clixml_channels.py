#!/usr/bin/env python3
"""Inspect actual stdout and stderr separately; preserve CLIXML and errors.

Independent public GitHub-hosted Windows runner only. No workspace secrets.
This script NEVER suppresses error records and never rewrites stdio bytes.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET


CASES = {
    "MULTILINE_GIT": ("Write-Output 'TZ410_BEGIN'\r\n& git.exe --version 2>&1 | Select-Object -First 1\nWrite-Output 'TZ410_END'", 0, ('TZ410_BEGIN', 'TZ410_END')),
    "PROGRESS": ("Write-Progress -Activity 'TZ410_LAB' -Status 'SYNTHETIC' -PercentComplete 40\nWrite-Output 'TZ410_PROGRESS_DONE'", 0, ('TZ410_PROGRESS_DONE',)),
    "RUSSIAN": ("Write-Output 'Проверка русского текста'\n[Console]::Error.WriteLine('TZ410_RU_STDERR')\nWrite-Output 'TZ410_RU_DONE'", 0, ('TZ410_RU_DONE',)),
    "CHILD_CMD": ("& cmd.exe /d /c echo TZ410_CHILD_OK\nWrite-Output 'TZ410_PARENT_OK'", 0, ('TZ410_CHILD_OK','TZ410_PARENT_OK')),
    "REAL_ERROR": ("Write-Error 'TZ410_REAL_ERROR'\n[Console]::Error.WriteLine('TZ410_ERROR_STDERR')\nexit 23", 23, ()),
}


def check_environment():
    if not (sys.platform=='win32' and os.getenv('GITHUB_ACTIONS')=='true'
            and os.getenv('RUNNER_ENVIRONMENT')=='github-hosted'
            and os.getenv('RUNNER_OS')=='Windows'
            and os.getenv('GITHUB_REPOSITORY')=='screamble123h/dc-windows-console-lab'
            and os.getenv('FOTOMAG_ISOLATED_WINDOWS_LAB')=='YES'
            and os.getenv('FOTOMAG_VM_EVIDENCE_SAFE')=='YES'):
        raise SystemExit('REFUSED_NOT_PUBLIC_GITHUB_WINDOWS_LAB')


def decoding(blob: bytes):
    for enc in ('utf-8-sig', 'cp866', 'cp1251'):
        try: return blob.decode(enc), enc
        except UnicodeError: continue
    return blob.decode('utf-8', errors='replace'), 'utf-8-replace'


def classify(blob: bytes) -> dict:
    t,enc=decoding(blob)
    fragment=re.search(r'(?:#< CLIXML\s*)?(<Objs\b[\s\S]*?</Objs>)',t)
    output={'clixml_header': '#< CLIXML' in t, 'xml_found':fragment is not None,
            'encoding':enc,'records':{},'xml_valid':None,'contains_real_error_marker':'TZ410_REAL_ERROR' in t}
    if fragment:
        try:
            root=ET.fromstring(fragment.group(1))
            kinds={}
            for obj in root.findall('.//{*}Obj'):
                ty=obj.attrib.get('S', 'unknown').lower()
                kinds[ty]=kinds.get(ty,0)+1
            output.update({'xml_valid':True,'records':kinds})
        except ET.ParseError:
            output.update({'xml_valid':False,'records':{},'xml_parse_error':'PARSE_ERROR'})
    return output


def contains_russian(blob: bytes, marker: str = 'Проверка русского текста') -> bool:
    # A single-byte OEM or ANSI decoder can succeed on arbitrary data but
    # return mojibake. Accept the exact Russian sentence in a known encoding.
    for encoding in ('utf-8', 'cp866', 'cp1251', 'utf-16le'):
        try:
            if marker in blob.decode(encoding, errors='strict'):
                return True
        except UnicodeError:
            pass
    return False


def describe(blob: bytes) -> dict:
    txt,enc=decoding(blob)
    return {'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest(),
            'encoding':enc,'excerpt':txt[:1000], 'clixml':classify(blob)}


def case_call(argv,root,env,timeout=20):
    try:
        p=subprocess.run(argv,cwd=root,env=env,stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,
                         timeout=timeout,creationflags=subprocess.CREATE_NO_WINDOW)
        return p.returncode,p.stdout,p.stderr,False
    except subprocess.TimeoutExpired as ex:
        return 124,ex.stdout or b'',ex.stderr or b'',True


def main():
    check_environment()
    root=Path.cwd()
    ev=root/'evidence'
    ev.mkdir(exist_ok=True)
    exe=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    broker=root/'lab/native/windows-headless-broker/fotomag-headless-broker-win64.exe'
    if not exe.is_file() or not broker.is_file():raise SystemExit('SYNTHETIC_LAB_DEPENDENCY_MISSING')
    all_cases=[];errors=[]
    for name,(script,expected,markers) in CASES.items():
        encoded=base64.b64encode(script.encode('utf-16le')).decode('ascii')
        for mode in ('baseline_command','encoded_direct','patched_broker'):
            ps_args=(['-NoProfile','-NonInteractive','-Command',script]
                     if mode=='baseline_command' else ['-NoProfile','-NonInteractive','-EncodedCommand',encoded])
            if mode=='patched_broker':
                payload={'protocol':1,'executable':str(exe),'args':ps_args,'verbatim':False,'killTree':True}
                wire=base64.urlsafe_b64encode(json.dumps(payload,separators=(',',':')).encode()).rstrip(b'=').decode()
                args=[str(broker),wire]
            else:args=[str(exe),*ps_args]
            code,out,err,timed_out=case_call(args,root,os.environ.copy())
            prefix=f'TZ410_{name}_{mode}'
            # Raw evidence is retained separately from the user presentation.
            # Synthetic inputs only; still keep artifacts repository-private to
            # the workflow run until the reporter confirms there are no secrets.
            (ev/(prefix+'.stdout.bin')).write_bytes(out)
            (ev/(prefix+'.stderr.bin')).write_bytes(err)
            txt,_=decoding(out)
            err_text,_=decoding(err)
            pass_now=(code==expected and not timed_out and all(m in txt for m in markers))
            if name=='REAL_ERROR':
                pass_now=pass_now and ('TZ410_REAL_ERROR' in (txt+err_text))
            if name=='RUSSIAN':
                pass_now=pass_now and contains_russian(out)
            if not pass_now:errors.append(prefix)
            row={'case':name,'mode':mode,'exit_code':code,'expected_exit_code':expected,
                 'timeout':timed_out,'markers_present':all(m in txt for m in markers),
                 'pass':pass_now,'russian_text_preserved':contains_russian(out) if name=='RUSSIAN' else None,
                 'stdout':describe(out),'stderr':describe(err)}
            all_cases.append(row)
            print(prefix,'exit',code,'stdout_bytes',len(out),'stderr_bytes',len(err),
                  'clixml_stderr',row['stderr']['clixml']['clixml_header'])
    summary={'name':'TZ410_CHANNEL_PRESERVATION_TEST','test_platform':'github-hosted-windows-2022',
             'source_streams_preserved':True,'results':all_cases,'passed':len(all_cases)-len(errors),
             'attempted':len(all_cases),'failure_ids':errors,
             'clixml_is_not_automatically_an_error':True,
             'parser_is_diagnostic_only':True,
             'desktop_commander_combined_presentation_not_fixed':True}
    (ev/'TZ410_CLIXML_CHANNELS.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 2 if errors else 0


if __name__=='__main__':
    raise SystemExit(main())
