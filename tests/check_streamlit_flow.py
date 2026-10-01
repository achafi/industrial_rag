"""Exercise real OCR + upload/search state with Streamlit's app test runner.

Run: uv run python tests/check_streamlit_flow.py
"""
import hashlib
import io
import json
from pathlib import Path
import sys
from unittest.mock import patch
import zipfile

import cairosvg
from PIL import Image
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pid_pipeline import render_bytes, generic_layout


def healthy(at):
    assert not at.exception, [e.message for e in at.exception]


def search(at, query):
    at.text_input(key="tag_query").set_value(query)
    next(b for b in at.button if b.label == "Find all occurrences").click().run()
    healthy(at)
    return at.session_state['search_bundle']['report']


at = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=180).run()
healthy(at)
at.button(key='run_ocr').click().run()
healthy(at)
assert not at.error, [e.value for e in at.error]
processed = at.session_state['processed']
p = processed['payload']
assert len(p['detections']) > 200
assert any(d['text_raw'] == 'MNc 47127 75HB13 50 Q 80' for d in p['detections'])
assert any('47124' in d['text_raw'] for d in p['detections'])
assert {d['region_type'] for d in p['detections']} == {'process_drawing','equipment_data_table','title_block','drawing_border'}
print('Reference OCR through UI passed.', flush=True)
with patch('pid_pipeline.run_ocr', side_effect=AssertionError('Search must not rerun OCR')):
    report = search(at, 'P4711')
    assert report['occurrence_count'] == 2
    table = report['groups']['equipment_data_table'][0]
    assert not any('P4712' in d['text_raw'] for d in table['nearby_ocr'])
    process = report['groups']['process_drawing'][0]
    assert any('47122' in d['text_raw'] for d in process['nearby_ocr'])
    bundle = at.session_state['search_bundle']
    with zipfile.ZipFile(io.BytesIO(bundle['zip'])) as z:
        assert 'search_results.json' in z.namelist()
        assert len([f for f in z.namelist() if f.endswith('.png')]) == 2
    assert search(at, 'P47110')['occurrence_count'] == 0
    at.text_input(key='tag_query').set_value('.*')
    next(b for b in at.button if b.label=='Find all occurrences').click().run()
    healthy(at)
    assert at.error and 'search_bundle' not in at.session_state

at.radio(key='source').set_value('Upload a drawing').run()
healthy(at)
assert 'processed' not in at.session_state
assert at.button(key='run_ocr').disabled
assert at.selectbox(key='layout_Upload a drawing').value == 'Generic / custom layout'

svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400"><rect width="800" height="400" fill="white"/><text x="100" y="180" font-size="40" font-family="sans-serif">P-101</text></svg>'
at.file_uploader(key='drawing_upload').set_value(('pump.svg', svg, 'image/svg+xml')).run()
at.select_slider[0].set_value(2000)
at.checkbox[0].set_value(False)
at.run()
at.button(key='run_ocr').click().run()
healthy(at)
assert not at.error, [e.value for e in at.error]
assert at.session_state['processed']['payload']['metadata']['source_sha256'] == hashlib.sha256(svg).hexdigest()
assert search(at, 'P101')['occurrence_count'] >= 1
print('Uploaded SVG → OCR → exact search → crop passed.', flush=True)

# New file invalidates old OCR/search data, even before processing.
at.file_uploader(key='drawing_upload').set_value(('invalid.svg', b'not an svg', 'image/svg+xml')).run()
assert 'processed' not in at.session_state and 'search_bundle' not in at.session_state
at.button(key='run_ocr').click().run()
healthy(at)
assert at.error and 'processed' not in at.session_state

# Render the other accepted upload formats and reject invalid pages/resources.
png = io.BytesIO()
Image.new('RGBA', (400,200), (0,0,0,0)).save(png, format='PNG')
im = render_bytes(png.getvalue(), '.png', 1000)
assert im.size == (1000,500) and im.getpixel((0,0)) == (255,255,255)
pdf = cairosvg.svg2pdf(bytestring=svg)
assert render_bytes(pdf, '.pdf', 1000).size == (1000,500)
for data, suffix, page in [(pdf,'.pdf',2),(png.getvalue(),'.png',2),(b'', '.svg',1)]:
    try:
        render_bytes(data,suffix,1000,page)
    except ValueError:
        pass
    else:
        raise AssertionError((suffix,page))
external=b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><image href="file:///etc/passwd" width="100" height="100"/></svg>'
try:
    render_bytes(external,'.svg',1000)
except ValueError:
    pass
else:
    raise AssertionError('External SVG resource was accepted')
assert generic_layout()['REGION_ZONES'] == {'equipment_data_table':[], 'title_block':[]}
print('Upload invalidation, invalid query/file, downloads, PDF/PNG and SVG resource checks passed.')
