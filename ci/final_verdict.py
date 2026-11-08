#!/usr/bin/env python3
"""Emit strictly bounded CI findings; never turn hosted functional PASS into GUI PASS."""
import json
from pathlib import Path
p=Path('evidence');p.mkdir(exist_ok=True)
def read(x):
 try: return json.loads((p/x).read_text(encoding='utf-8'))
 except (OSError, ValueError): return {}
func=read('CI_FUNCTIONAL_RESULT.json'); session=read('runner_session_probe.json')
report={'baseline': next((r for r in func.get('results',[]) if r.get('mode')=='baseline'),{}),
        'patched': next((r for r in func.get('results',[]) if r.get('mode')=='broker'),{}),
        'github_hosted_windows': bool(session.get('windows')),
        'interactive_candidate': session.get('interactive_candidate'),
        'focus_and_visible_windows':'NOT_PROVEN',
        'remote_mcp_connection_recovery':'NOT_TESTED',
        'close_desktop_resource_release':'NOT_TESTED',
        'original_v4_6_binary_bit_exact':'NOT_TESTED',
        'ready_to_deploy':False,
        'reason':'Hosted runner lacks independently verified interactive workstation desktop and Remote MCP E2E. Sanitized lab safety guard differs from original package.'}
(p/'CI_FINAL_VERDICT.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2,ensure_ascii=False))
