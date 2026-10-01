"""Regression: PI4712 must find the split instrument PI + 4712.01."""
import json
from pathlib import Path
import sys
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pid_search import retrieve_tag
from pid_pipeline import REFERENCE_LAYOUT

payload = json.loads((ROOT/'outputs/reference_pid_searchable.json').read_text())
regions = REFERENCE_LAYOUT['REGION_INSTANCES']
contains = retrieve_tag(payload, 'PI4712', regions)
matching = [o for rows in contains['groups'].values() for o in rows if o['matched_text']=='PI4712.01']
assert len(matching)==1
assert matching[0]['match_quality']=='partial' and matching[0]['match_method']=='spatially_grouped'
assert len(matching[0]['source_boxes'])==2
assert retrieve_tag(payload, 'PI4712', regions, match_mode='exact')['occurrence_count']==0
assert retrieve_tag(payload, 'PI4712.01', regions, match_mode='exact')['occurrence_count']==1
assert retrieve_tag(payload, 'pi-4712', regions)['occurrence_count']==contains['occurrence_count']
assert retrieve_tag(payload, 'PI', regions)['occurrence_count']>0
assert retrieve_tag(payload, '4712', regions)['occurrence_count']>0
assert retrieve_tag(payload, 'PI4712X01', regions)['occurrence_count']==0
assert retrieve_tag(payload, 'MNb 47121', regions)['occurrence_count']>0
base=payload['detections'][0]
fixture=dict(payload, detections=[dict(base,id='long',text_raw='P47110'),dict(base,id='exact',text_raw='P4711')])
r=retrieve_tag(fixture,'P4711',[])['groups'][base['region_type']]
assert [(o['source_detection_id'],o['match_quality']) for o in r]==[('exact','exact'),('long','partial')]
assert retrieve_tag(fixture,'P4711',[],match_mode='exact')['occurrence_count']==1
for invalid in ('', '.*', '[PI]'):
    try:
        retrieve_tag(payload,invalid,regions)
    except ValueError:
        pass
    else:
        raise AssertionError(invalid)

at=AppTest.from_file(str(ROOT/'app.py'),default_timeout=40).run()
at.button(key='prepared').click().run()
assert not at.exception
with patch('pid_pipeline.run_ocr',side_effect=AssertionError('Search must reuse OCR')):
    assert at.radio(key='match_mode').value=='Contains'
    at.text_input(key='tag_query').set_value('PI4712')
    next(b for b in at.button if b.label=='Find all occurrences').click().run()
    assert not at.exception
    report=at.session_state['search_bundle']['report']
    assert report['search_mode']=='contains' and report['occurrence_count']>=1
    assert any('Partial text match' in c.value for c in at.caption)
    at.radio(key='match_mode').set_value('Exact tag')
    next(b for b in at.button if b.label=='Find all occurrences').click().run()
    assert not at.exception
    assert at.session_state['search_bundle']['report']['occurrence_count']==0
    at.text_input(key='tag_query').set_value('PI4712.01')
    next(b for b in at.button if b.label=='Find all occurrences').click().run()
    assert not at.exception
    assert at.session_state['search_bundle']['report']['occurrence_count']==1
print('Partial grouped-tag, literal fragments, exact ordering and app mode switching passed.')
