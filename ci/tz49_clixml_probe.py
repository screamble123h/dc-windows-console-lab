#!/usr/bin/env python3
"""Compare PowerShell channel behavior with -Command vs -EncodedCommand and v4.6 broker.

No user credentials. Standard public GitHub-hosted Windows runner only.
Do not use on a production workstation. Does not claim visible GUI focus proof.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET


def ensure_lab() -> None:
    if not (sys.platform == 'win32' and os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('RUNNER_OS') == 'Windows'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and os.environ.get('FOTOMAG_ISOLATED_WINDOWS_LAB') == 'YES'
            and os.environ.get('FOTOMAG_VM_EVIDENCE_SAFE') == 'YES'):
        raise SystemExit('REFUSED_NOT_PUBLIC_GITHUB_HOSTED_WINDOWS_LAB')


def decode(b: bytes) -> tuple[str, str]:
    if b.startswith(b'\xff\xfe'):
        return b.decode('utf-16le', 'replace'), 'utf-16le'
    for enc in ('utf-8-sig', 'cp866', 'cp1251'):
        try:
            return b.decode(enc, 'strict'), enc
        except UnicodeError:
            pass
    return b.decode('utf-8', 'replace'), 'utf-8-replace'


def classify_clixml(stream: bytes) -> dict:
    text, encoding = decode(stream)
    start = text.find('#< CLIXML')
    output = {'present': start != -1, 'encoding': encoding, 'valid_xml': None,
              'progress_records': 0, 'error_records': 0, 'warning_records': 0,
              'xml_parse_error': None}
    if start == -1:
        return output
    fragment = text[start + len('#< CLIXML'):].strip()
    pos = fragment.find('<Objs')
    if pos >= 0:
        try:
            root = ET.fromstring(fragment[pos:])
            objects = root.findall('.//{*}Obj')
            output['valid_xml'] = True
            for obj in objects:
                kind = obj.attrib.get('S', '').lower()
                if kind == 'progress': output['progress_records'] += 1
                if kind == 'error': output['error_records'] += 1
                if kind == 'warning': output['warning_records'] += 1
        except ET.ParseError as exc:
            output['valid_xml'] = False
            output['xml_parse_error'] = str(exc)[:120]
    return output


def run(command: list[str], cwd: Path, env: dict, seconds: int = 18) -> dict:
    try:
        p = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=seconds,
                           creationflags=subprocess.CREATE_NO_WINDOW, check=False)
        code, out, err = p.returncode, p.stdout, p.stderr
        timeout = False
    except subprocess.TimeoutExpired as exc:
        code, out, err, timeout = 124, exc.stdout or b'', exc.stderr or b'', True
    out_text, out_enc = decode(out)
    err_text, err_enc = decode(err)
    return {
        'return_code': code, 'timeout': timeout,
        'stdout': {'bytes': len(out), 'sha256': hashlib.sha256(out).hexdigest(),
                   'encoding': out_enc, 'excerpt': out_text[:800], 'clixml': classify_clixml(out)},
        'stderr': {'bytes': len(err), 'sha256': hashlib.sha256(err).hexdigest(),
                   'encoding': err_enc, 'excerpt': err_text[:1600], 'clixml': classify_clixml(err)}
    }


def main() -> int:
    ensure_lab()
    root = Path.cwd()
    exe = Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    broker = root/'lab/native/windows-headless-broker/fotomag-headless-broker-win64.exe'
    if not exe.is_file() or not broker.is_file():
        raise SystemExit('REQUIRED_WINDOWS_BINARY_MISSING')
    env = dict(os.environ)
    cases = {
        'MULTILINE_GIT': "Write-Output 'LAB_BEGIN'\r\n& git.exe --version 2>&1 | Select-Object -First 1\nWrite-Output 'LAB_END'",
        'PROGRESS': "Write-Progress -Activity 'LAB_PROGRESS' -Status 'LAB_WORK' -PercentComplete 40\nWrite-Output 'LAB_PROGRESS_DONE'",
        'RUSSIAN': "Write-Output 'Проверка русского текста'\n[Console]::Error.WriteLine('TEST_STDERR_OK')\nWrite-Output 'LAB_RU_DONE'",
        'ERROR': "[Console]::Error.WriteLine('LAB_EXPECTED_ERROR')\nWrite-Output 'LAB_ERROR_SEEN'\nexit 23",
        'NESTED_CMD': "& cmd.exe /d /c echo LAB_CHILD_OK\nWrite-Output 'LAB_PARENT_OK'",
    }
    rows = []
    for name, script in cases.items():
        encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
        for variant in ('baseline_command','encoded_direct','encoded_broker'):
            args = (['-NoProfile','-NonInteractive','-Command',script] if variant=='baseline_command'
                    else ['-NoProfile','-NonInteractive','-EncodedCommand',encoded])
            if variant=='encoded_broker':
                payload = {'protocol':1,'executable':str(exe),'args':args,
                           'verbatim':False,'killTree':True}
                wire = base64.urlsafe_b64encode(json.dumps(payload,separators=(',',':')).encode()).rstrip(b'=').decode()
                argv = [str(broker),wire]
            else:
                argv = [str(exe),*args]
            result = run(argv,root,env)
            rows.append({'case':name, 'variant':variant, **result})
            print(f"{name}:{variant}:code={result['return_code']} stdout={result['stdout']['bytes']} stderr={result['stderr']['bytes']} clixml_out={result['stdout']['clixml']['present']} clixml_err={result['stderr']['clixml']['present']}")
    evidence = root/'evidence'
    evidence.mkdir(exist_ok=True)
    output = {'test': 'TZ4_9_CLIXML_STREAMS', 'windows_functional': True,
              'gui_focus_proven': False, 'process_spawn_method': 'subprocess/shell_false/CREATE_NO_WINDOW',
              'cases': len(cases), 'variants': 3, 'results': rows,
              'interpretation': 'CLIXML is PowerShell serialized progress/error stream; classify by channel and XML record type, never discard stderr.'}
    (evidence/'TZ4_9_CLIXML_STREAMS.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    # Do not treat CLIXML as error by itself. Fail for actual non-zero exit mismatch.
    failures=[]
    for row in rows:
        exp = 23 if row['case']=='ERROR' else 0
        if row['return_code']!=exp or row['timeout']:
            failures.append(f"{row['case']}/{row['variant']}: return={row['return_code']} expected={exp}")
    print('CLIXML_PROBE_PASS' if not failures else 'CLIXML_PROBE_MISMATCH', failures)
    return 0 if not failures else 2


if __name__ == '__main__':
    sys.exit(main())
