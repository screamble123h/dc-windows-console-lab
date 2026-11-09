"""Strict readiness gate: functional CI != verified interactive Windows GUI."""
from __future__ import annotations
import json
from pathlib import Path


def parse(path):
    if not path.exists():return {}
    try:return json.loads(path.read_text(encoding='utf8'))
    except Exception:return {}


def verdict(control,channels,matrix,resources):
    cpos=(control.get('positive') or {}).get('status')=='PASS'
    cneg=(control.get('negative') or {}).get('status')=='PASS'
    focus=(control.get('focus') or {}).get('status')=='PASS'
    matrix_rows=matrix.get('matrix') or []
    matrix_ok=(len(matrix_rows)>=3 and all(x.get('exit')==0 for x in matrix_rows))
    # matrix has 100 baseline and 100 patched, never silently count the old run.
    clixml_ok=(channels.get('attempted')==15 and channels.get('passed')==15 and
               not channels.get('failure_ids'))
    ev = Path('evidence')
    baseline = parse(ev/'WINDOWS_LAB_BASELINE_100.json').get('manifest') or {}
    patched = parse(ev/'WINDOWS_LAB_BROKER_100.json').get('manifest') or {}
    counts_ok = baseline.get('attempted') == 100 and patched.get('attempted') == 100
    patched_ok = patched.get('passed') == 100 and patched.get('failed') == 0
    return {
      'target':'FotoMag Desktop Commander TZ4.10',
      'hosted_runner_control':{
        'positive_detected':cpos,'negative_hidden':cneg,
        'notepad_focus_transition_detected':focus,
        'zero_window_claim_calibrated':bool(control.get('calibrated_for_zero_window_claim') and cpos and cneg),
        'status':'PASS_HOSTED_RUNNER_CONTROLS' if cpos and cneg and focus else 'NOT_PROVEN',
      },
      'functional':{'matrix_ok':matrix_ok,'counts_verified':counts_ok,
                    'baseline_attempted':baseline.get('attempted'),
                    'baseline_passed':baseline.get('passed'),
                    'patched_attempted':patched.get('attempted'),
                    'patched_passed':patched.get('passed'),
                    'patched_100_pass':patched_ok,
                    'clixml_raw_streams_ok':clixml_ok},
      'resources':resources,
      'human_interactive_desktop_verified':False,
      'remote_mcp_reconnection_verified':False,
      'original_2026_11_08_window_reproduced':False,
      'root_cause_definitively_identified':False,
      'production_PC_unchanged_by_workflow':True,
      'ready_to_deploy':False,
      'verdict':'НЕ ГОТОВ К ВНЕДРЕНИЮ',
      'reasons':['No independent human interactive GUI validation',
                 'No isolated Remote MCP transport and reconnect test',
                 'No proof that initial production defect has been reproduced and eliminated'],
    }


def main():
    ev=Path('evidence')
    out=verdict(parse(ev/'TZ410_GUI_CONTROL_RESULTS.json'),
                parse(ev/'TZ410_CLIXML_CHANNELS.json'),
                parse(ev/'TZ4_9_MATRIX_REPORT.json'),
                parse(ev/'TZ410_RESOURCE_COMPARISON.json'))
    ev.mkdir(exist_ok=True)
    (ev/'TZ410_FINAL_VERDICT.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(out,ensure_ascii=False,indent=2))
    # Even a green suite may not certify installation; fail if positive control
    # was absent or if functional checks did not run.
    ok=(out['hosted_runner_control']['positive_detected']
        and out['hosted_runner_control']['negative_hidden']
        and out['hosted_runner_control']['notepad_focus_transition_detected']
        and out['functional']['matrix_ok']
        and out['functional']['counts_verified']
        and out['functional']['patched_100_pass']
        and out['resources'].get('status') == 'PASS_CANDIDATE_ONLY'
        and out['functional']['clixml_raw_streams_ok'])
    return 0 if ok else 2

if __name__=='__main__':
    raise SystemExit(main())
