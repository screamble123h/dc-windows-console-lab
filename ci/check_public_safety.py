#!/usr/bin/env python3
"""Preflight for publishing the staged lab: deny internal identifiers and secrets.

This is a superficial guard, not a replacement for human code review.
"""
from pathlib import Path
import re
import sys

root=Path(__file__).resolve().parent.parent
patterns={
    'private windows hostname':r'DESKTOP-[A-Z0-9]{7,16}\b',
    'local Windows data path':r'(?i)[A-Z]:\\(?:Users\\|FotoMag_|FM_AI_OS|2026\\)',
    'emails':r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',
    'possible secret assignment':r'(?i)(?:api[_-]?key|password|client_secret|access_token)\s*[:=]\s*["\']?[A-Za-z0-9/_+-]{10,}',
}
violations=[]
for p in root.rglob('*'):
    if not p.is_file() or p.name=='SHA256SUMS.txt':continue
    try:txt=p.read_text('utf-8')
    except UnicodeError:continue
    for label,pattern in patterns.items():
        for x in re.finditer(pattern,txt):
            # Remote runner's public workflow YAML contains GitHub pseudo-expressions,
            # but never actual credentials.
            violations.append((p.relative_to(root).as_posix(),label,txt.count('\n',0,x.start())+1))
for p,l,n in violations:print('NOT_PUBLIC_SAFE',p,l,n,file=sys.stderr)
print('public_scan_files=',sum(p.is_file() for p in root.rglob('*')), 'violations=',len(violations))
sys.exit(2 if violations else 0)
