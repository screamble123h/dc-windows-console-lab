#!/usr/bin/env python3
"""Read-only audit of downloaded public GitHub run artifacts (no network or Windows)."""
from __future__ import annotations
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile


def review(path: Path):
    with ZipFile(path) as z:
        assert z.testzip() is None, 'CORRUPT_GITHUB_ARTIFACT'
        final=json.loads(z.read('CI_FINAL_VERDICT.json'))
        functional=json.loads(z.read('CI_FUNCTIONAL_RESULT.json'))
        before=json.loads(z.read('START_PROCESS_BASELINE_SMOKE.json'))
        after=json.loads(z.read('START_PROCESS_BROKER_SMOKE.json'))
        b=next(x for x in before['outcomes'] if x['id']=='MULTILINE_TOOL')
        p=next(x for x in after['outcomes'] if x['id']=='MULTILINE_TOOL')
        assert not '#< CLIXML' in b['stdout_excerpt'], 'BASELINE_CLIXML_UNEXPECTED'
        assert '#< CLIXML' in p['stdout_excerpt'], 'PATCH_CLIXML_NOT_FOUND'
        result=p['stdout_excerpt']; m=re.search(r'<Objs\s.*?</Objs>',result,re.DOTALL)
        assert m, 'CLIXML_XML_MISSING'
        root=ET.fromstring(m.group(0))
        objs=root.findall('.//{*}Obj')
        types=[x.attrib.get('S') for x in objs]
        assert types==['progress'], 'NON_PROGRESS_CLIXML_NEEDS_ERROR_REVIEW'
        progress=root.find('.//{*}AV')
        assert progress is not None
        gui=functional.get('hosted_runner_gui_observer') or []
        return {
          'artifact':path.name,
          'baseline_attempted':final['baseline']['attempted'],
          'baseline_passed':final['baseline']['passed'],
          'patched_attempted':final['patched']['attempted'],
          'patched_passed':final['patched']['passed'],
          'tool_api_baseline_passed':before['passed'],
          'tool_api_patch_passed':after['passed'],
          'clixml_in_patched_multiline_tool':True,
          'clixml_in_original_multiline_tool':False,
          'clixml_records':types,
          'clixml_progress_message':progress.text,
          'exit_from_tool_api': 'FINISHED (no process exit-code field in smoke response)',
          'real_stdout_stderr_separated':False,
          'gui_observations':gui,
          'focus_and_visible_windows_proven':False,
          'remote_mcp_e2e_proven':False,
          'ready_to_deploy':False,
        }

if __name__=='__main__':
    result={'source':'Public GitHub Actions artifacts, original v4.6 comparison',
            'audits':[review(Path(x)) for x in sys.argv[1:]]}
    print(json.dumps(result,ensure_ascii=False,indent=2))
