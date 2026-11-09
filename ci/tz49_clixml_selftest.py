#!/usr/bin/env python3
"""No-Windows, no-process self test for CLIXML classification without hiding errors."""
from tz49_clixml_probe import classify_clixml


def make(kind):
    return ('#< CLIXML\n<Objs xmlns="http://schemas.microsoft.com/powershell/2004/04">'
            '<Obj S="'+kind+'"><MS><S N="Detail">TEST</S></MS></Obj></Objs>').encode()

for key in ('progress','error','warning'):
    result = classify_clixml(make(key))
    assert result['present'] and result['valid_xml']
    assert result[f'{key}_records'] == 1
    for other in ('progress','error','warning'):
        if other != key: assert result[f'{other}_records'] == 0
plain = classify_clixml(b'ordinary stderr text')
assert plain['present'] is False
bad = classify_clixml(b'#< CLIXML\n<Objs><Obj S="error"')
assert bad['present'] and bad['valid_xml'] is False
print('TZ4_9_CLIXML_CLASSIFIER_SELFTEST_PASS')
