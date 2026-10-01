"""Run: uv run python tests/check_instrument_grouping.py"""
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pid_instruments import build_instrument_inventory
from pid_search import retrieve_tag, save_search_results
from functools import partial
retrieve_tag = partial(retrieve_tag, match_mode="exact")


def d(id, text, box, region='process_drawing'):
    return dict(id=id, text_raw=text, confidence=.97, region_type=region, searchable=region!='drawing_border',
                bounding_box=dict(zip(('x_min','y_min','x_max','y_max'),box)))


def payload(items):
    return dict(document_id='fixture', page=1, image_width=1000, image_height=800, detections=items)


base = payload([d('prefix','PT',(100,100,125,120)), d('number','133035',(80,126,145,146)),
                d('hz','HZ',(300,100,325,120)),d('suffix','133065C',(280,126,350,146)),
                d('complete','PT133035',(100,400,250,425))])
before = deepcopy(base)
inventory = build_instrument_inventory(base)
assert base == before
assert {r['canonical_tag'] for r in inventory['instruments']} == {'PT133035','HZ133065C'}
assert next(r for r in inventory['instruments'] if r['canonical_tag']=='PT133035')['occurrence_count'] == 2
assert all(not r['ambiguous'] for r in inventory['occurrences'])
result = retrieve_tag(base,'PT133035',[])
assert result['occurrence_count'] == 2  # Direct AND split occurrences, not zero-match fallback.
grouped = next(r for r in result['groups']['process_drawing'] if r['match_method']=='spatially_grouped')
assert grouped['source_detection_ids'] == ['prefix','number']
assert len(grouped['source_boxes']) == 2
assert not {'prefix','number'} & {r['id'] for r in grouped['nearby_ocr']}
assert retrieve_tag(base,'PT13303',[])['occurrence_count'] == 0
assert retrieve_tag(base,'HZ133065C',[])['occurrence_count'] == 1
assert retrieve_tag(base,'HZ133065',[])['occurrence_count'] == 0

# Scale-invariant geometry, right-of-prefix and dotted suffixes.
scaled = deepcopy(base)
scaled['image_width'] *= 2; scaled['image_height'] *= 2
for item in scaled['detections']:
    item['bounding_box'] = {k:v*2 for k,v in item['bounding_box'].items()}
assert [i['canonical_tag'] for i in build_instrument_inventory(scaled)['instruments']] == [i['canonical_tag'] for i in inventory['instruments']]
side = payload([d('p','PI',(100,100,125,120)), d('n','4712.01',(130,100,200,120))])
assert build_instrument_inventory(side)['instruments'][0]['canonical_tag'] == 'PI4712.01'

# Reject distant, misaligned, reverse, unrelated-region and other-page pairs.
for number in [d('n','133035',(80,200,145,220)),d('n','133035',(180,126,245,146)),
               d('n','133035',(80,60,145,80)),d('n','133035',(80,126,145,146),'equipment_data_table'),
               d('n','133035',(80,126,145,146),'drawing_border'),
               dict(d('n','133035',(80,126,145,146)),page=2)]:
    assert not build_instrument_inventory(payload([base['detections'][0],number]))['occurrences']
assert not build_instrument_inventory(payload([d('x','UNKNOWN',(100,100,125,120)),base['detections'][1]]))['occurrences']

ambiguous = payload([base['detections'][0], base['detections'][1],d('n2','133036',(82,128,147,148))])
amb = build_instrument_inventory(ambiguous)
assert len(amb['occurrences']) == 2 and all(o['ambiguous'] for o in amb['occurrences'])
assert retrieve_tag(ambiguous,'PT133035',[])['groups']['process_drawing'][0]['ambiguous']
shared = payload([base['detections'][0], d('p2','FT',(103,100,128,120)), base['detections'][1]])
assert all(o['ambiguous'] for o in build_instrument_inventory(shared)['occurrences'])
with tempfile.TemporaryDirectory() as tmp:
    path = save_search_results(result,Image.new('RGB',(1000,800),'white'),Path(tmp))
    assert json.loads(path.read_text()) == result
    with Image.open(Path(tmp)/grouped['crop_file']) as crop:
        b = grouped['crop_bounds']
        for q in grouped['source_boxes']:
            assert crop.getpixel((q['x_min']-b['x_min'],q['y_min']-b['y_min'])) == (214,40,40)
print('Split/complete inventory, suffixes, ambiguity, geometry, immutability and dual-box highlight checks passed.')
