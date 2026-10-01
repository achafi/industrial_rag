"""Run from any directory: uv run python tests/check_region_classification.py."""
import ast
import json
from pathlib import Path
import nbformat

ROOT = Path(__file__).resolve().parents[1]
notebook = nbformat.read(ROOT / 'notebooks/01_reference_pid_ocr.ipynb', 4)
namespace = {}
for cell in notebook.cells:
    if cell.cell_type != 'code':
        continue
    for node in ast.parse(cell.source).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {'DRAWING_CONTENT_BOUNDS', 'REGION_ZONES'} for t in node.targets):
            exec(compile(ast.Module(body=[node], type_ignores=[]), '<config>', 'exec'), namespace)
        if isinstance(node, ast.FunctionDef) and node.name in {'drawing_border_reason', 'classify_region'}:
            exec(compile(ast.Module(body=[node], type_ignores=[]), '<regions>', 'exec'), namespace)

def classify(coords, scale=1):
    box = dict(zip(('x_min', 'y_min', 'x_max', 'y_max'), [v * scale for v in coords]))
    return namespace['classify_region'](box, 5000 * scale, 3536 * scale, namespace['DRAWING_CONTENT_BOUNDS'], namespace['REGION_ZONES'])

for coords in [(239, 14, 264, 44), (15, 245, 44, 281), (4962, 249, 4983, 273), (1873, 3488, 1901, 3523)]:
    assert classify(coords) == 'drawing_border'
assert classify((40, 100, 80, 130)) == 'process_drawing'  # Straddles the inner frame: retain.
assert classify((1000, 1800, 1100, 1840)) == 'process_drawing'
assert classify((914, 3156, 1013, 3190)) == 'equipment_data_table'
assert classify((913, 2819, 1015, 2850)) == 'equipment_data_table'
assert classify((3535, 3437, 3925, 3474)) == 'title_block'  # Near bottom, but still content.
for scale in (0.5, 2):
    assert classify((914, 3156, 1013, 3190), scale) == 'equipment_data_table'
    assert classify((239, 14, 264, 44), scale) == 'drawing_border'
# Same text appearing in process and table must be classified by location, not its string.
data = json.loads((ROOT / 'outputs/reference_pid_ocr.json').read_text())
pumps = [d for d in data['detections'] if d['text_raw'] == 'P4711']
assert {namespace['classify_region'](d['bounding_box'], data['image_width'], data['image_height'], namespace['DRAWING_CONTENT_BOUNDS'], namespace['REGION_ZONES']) for d in pumps} == {'process_drawing', 'equipment_data_table'}
print('Region, four border edges, boundary retention, title/table preservation and scale checks passed.')
