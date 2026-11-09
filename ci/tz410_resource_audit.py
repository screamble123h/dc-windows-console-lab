"""Pure analysis of two Win32 resource snapshots; never closes processes."""
import json
import sys
from pathlib import Path


def examine(before:dict,after:dict)->dict:
    b=set(before.get('broker_desktop_names') or [])
    a=set(after.get('broker_desktop_names') or [])
    bp={int(p['pid']):p for p in before.get('candidate_processes') or []}
    ap={int(p['pid']):p for p in after.get('candidate_processes') or []}
    born=[p for pid,p in ap.items() if pid not in bp]
    orphan_candidates=[p for p in born if p.get('name','').lower()=='fotomag-headless-broker-win64.exe']
    good=before.get('window_station_desktops_enumerated') is True and after.get('window_station_desktops_enumerated') is True
    return {'new_hidden_desktop_names':sorted(a-b),
            'disappeared_hidden_desktop_names':sorted(b-a),
            'new_candidate_processes':born,
            'new_broker_processes':orphan_candidates,
            'desktop_enumeration_valid':good,
            'status':'PASS_CANDIDATE_ONLY' if good and not(a-b) and not orphan_candidates else 'INCONCLUSIVE_OR_LEAK_CANDIDATE',
            'important':'No proof of zero handle leaks, or child process ownership without additional Windows evidence.'}

if __name__=='__main__':
    before=json.loads(Path(sys.argv[1]).read_text(encoding='utf8'))
    after=json.loads(Path(sys.argv[2]).read_text(encoding='utf8'))
    result=examine(before,after)
    print(json.dumps(result,indent=2))
    Path(sys.argv[3]).write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
