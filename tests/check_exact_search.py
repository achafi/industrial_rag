"""Run: uv run python tests/check_exact_search.py"""
import ast
import json
from pathlib import Path
import sys
import tempfile

import nbformat
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pid_search import exact_tag_pattern, retrieve_tag, save_search_results
from functools import partial
retrieve_tag = partial(retrieve_tag, match_mode="exact")

pattern = exact_tag_pattern("P4711")
for text in ("P4711", "p-4711", "Feed P4711 discharge", "P4711 / P4712"):
    assert pattern.search(text), text
for text in ("P47110", "P4711A", "XP4711", "P4711.02", "P4711-20"):
    assert not pattern.search(text), text
assert exact_tag_pattern("PV4712.02").search("PV4712.02")
assert not exact_tag_pattern("PV4712.02").search("PV4712X02")
for query in ("", "P", ".*", "../"):
    try:
        exact_tag_pattern(query)
    except ValueError:
        pass
    else:
        raise AssertionError(query)

nb = nbformat.read(ROOT / 'notebooks/01_reference_pid_ocr.ipynb', 4)
regions = None
for cell in nb.cells:
    if cell.cell_type == 'code':
        for node in ast.parse(cell.source).body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'REGION_INSTANCES' for t in node.targets):
                regions = ast.literal_eval(node.value)
assert regions
payload = json.loads((ROOT / 'outputs/reference_pid_searchable.json').read_text())
result = retrieve_tag(payload, 'P4711', regions)
assert result['occurrence_count'] == 2
assert set(result['groups']) == {'process_drawing', 'equipment_data_table'}
table = result['groups']['equipment_data_table'][0]
assert table['region_id'] == 'table_lower_left'
assert any('200' in d['text_raw'] for d in table['nearby_ocr'])
assert not any('P4712' in d['text_raw'] or '420' in d['text_raw'] for d in table['nearby_ocr'])
assert result['groups']['process_drawing'][0]['region_selection_method'] == 'local_spatial_window'
process = result['groups']['process_drawing'][0]
assert any('47121' in d['text_raw'] for d in process['nearby_ocr'])
assert any('47122' in d['text_raw'] for d in process['nearby_ocr'])
for d in process['nearby_ocr']:
    b, crop = d['bounding_box'], process['crop_bounds']
    assert crop['x_min'] <= b['x_min'] < b['x_max'] <= crop['x_max']
    assert crop['y_min'] <= b['y_min'] < b['y_max'] <= crop['y_max']
assert retrieve_tag(payload, 'P47110', regions)['groups'] == {}
fallback = retrieve_tag(payload, 'P4711', [])
assert all(r['region_selection_method'] == 'local_spatial_window' for rows in fallback['groups'].values() for r in rows)
synthetic = dict(payload)
hit = dict(payload['detections'][0], text_raw='P4711 P4711', region_type='process_drawing', searchable=True)
border = dict(hit, id='border', region_type='drawing_border', searchable=False)
synthetic['detections'] = [hit, border]
repeated = retrieve_tag(synthetic, 'P4711', [])
assert repeated['occurrence_count'] == 1 and repeated['tag_match_count'] == 2
# A label can overlap the seed while its center lies outside. Select it in full,
# but do not recursively follow another label reached only by the expansion.
def item(identifier, text, coords, region='process_drawing'):
    return dict(id=identifier, text_raw=text, confidence=.9, searchable=True,
                region_type=region, bounding_box=dict(zip(('x_min','y_min','x_max','y_max'),coords)))
chain = dict(payload, image_width=1000, image_height=1000, detections=[
    item('pump', 'P4711', (450,450,500,480)),
    item('edge', 'complete long line', (530,455,850,475)),
    item('cascade', 'should not be selected', (800,450,990,480)),
    item('table', 'other region', (460,450,490,480), 'equipment_data_table'),
])
single = retrieve_tag(chain, 'P4711', [])['groups']['process_drawing'][0]
assert [d['id'] for d in single['nearby_ocr']] == ['edge']
assert single['crop_bounds']['x_max'] == 858
edge_page = dict(chain, detections=[item('pump','P4711',(0,0,30,20)), item('line','line',(20,0,1000,40))])
bounded = retrieve_tag(edge_page,'P4711',[])['groups']['process_drawing'][0]['crop_bounds']
assert bounded['x_min'] == bounded['y_min'] == 0 and bounded['x_max'] == 1000
with tempfile.TemporaryDirectory() as tmp:
    with Image.open(ROOT / 'outputs/reference_pid.png') as page:
        path = save_search_results(result, page, Path(tmp))
        assert json.loads(path.read_text()) == result
        for items in result['groups'].values():
            for item in items:
                b = item['crop_bounds']
                with Image.open(Path(tmp) / item['crop_file']) as crop:
                    assert crop.size == (b['x_max'] - b['x_min'], b['y_max'] - b['y_min'])
                    q = item['bounding_box']
                    assert crop.getpixel((q['x_min'] - b['x_min'], q['y_min'] - b['y_min'])) == (214, 40, 40)
print('Exact boundaries, grouping, table isolation, repeated matches, empty results and crop checks passed.')
