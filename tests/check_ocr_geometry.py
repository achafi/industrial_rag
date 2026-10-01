import ast
from pathlib import Path
import nbformat
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
nb=nbformat.read(ROOT / 'notebooks/01_reference_pid_ocr.ipynb',4)
ns={'np':np,'REVIEW_THRESHOLD':.8}
for c in nb.cells:
 if c.cell_type=='code':
  for node in ast.parse(c.source).body:
   if isinstance(node,ast.FunctionDef) and node.name in {'unrotate_points','internal_edge_flags','overlap_fraction','same_text_region','selection_priority','deduplicate_candidates'}:
    exec(compile(ast.Module(body=[node],type_ignores=[]),'notebook','exec'),ns)
p=np.array([[10,20],[70,20],[70,40],[10,40]],dtype=float)
w,h=100,60
for angle in [0,90,270]:
 rot=p if angle==0 else (np.column_stack((p[:,1],w-p[:,0])) if angle==90 else np.column_stack((h-p[:,1],p[:,0])))
 np.testing.assert_allclose(ns['unrotate_points'](rot,angle,w,h),p)
f=ns['internal_edge_flags']
assert f([0,0,10,10],[0,0,100,60],100,60,12)==[]
assert f([2590,950,2878,983],[1280,0,2880,1600],5000,3536,12)==['right']
def cand(i,box,edge=False,confidence=.97,tile=2,rotation=0):
 return dict(candidate_id=i,text_raw=i,box=box,near_internal_tile_edge=edge,confidence=confidence,tile=tile,rotation_ccw=rotation,internal_tile_edges=['right'] if edge else [])
short=cand('short',[2590,950,2878,983],True,.999)
full=cand('full',[2592,951,3104,984],False,.976,tile=3)
f=ns['deduplicate_candidates']
for inputs in [[short,full],[full,short]]:
 r=f(inputs); assert len(r)==1 and r[0]['candidate_id']=='full'
a=cand('vertical',[100,100,130,400],tile=1)
b=cand('rotated',[99,99,131,401],tile=1,rotation=90)
r=f([a,b]);assert len(r)==1 and len(r[0]['alternatives'])==1
far=cand('elsewhere',[500,100,530,400],tile=3)
assert len(f([a,far]))==2
cross=cand('cross',[20,200,200,225],tile=3)
assert len(f([a,cross]))==2
nozzle=cand('N2',[100,100,130,125],tile=2)
assert len(f([a,nozzle]))==2  # Rotated long text must not swallow nearby horizontal labels.
print('Rotation transforms, page/tile edges, complete-over-clipped selection, cross-pass deduplication and separate locations passed.')
