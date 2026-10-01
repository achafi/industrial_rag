"""UI checks for grouped inventory and search without repeating OCR."""
from pathlib import Path
import sys
from PIL import Image
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pid_pipeline import annotate, classify_payload, generic_layout


def detection(identifier, text, box):
    b = dict(zip(('x_min','y_min','x_max','y_max'), box))
    return dict(id=identifier,text_raw=text,text_normalized=text,confidence=.95,bounding_box=b,
                bounding_box_normalized={k:v/(1000 if k.startswith('x') else 800) for k,v in b.items()},
                needs_review=False)


at=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
assert not at.exception
at.button(key='prepared').click().run()
assert not at.exception
image=Image.new('RGB',(1000,800),'white')
payload=classify_payload(dict(document_id='split-test',page=1,image_width=1000,image_height=800,
    metadata={},detections=[detection('pt','PT',(100,100,125,120)),
                           detection('num','133035',(80,126,145,146))]),generic_layout())
import io
png=io.BytesIO();annotate(image,payload).save(png,format='PNG')
at.session_state['processed']={'payload':payload,'image':image,'annotated':png.getvalue(),'filename':'split-test.png'}
at.run()
assert not at.exception
assert any(t.label=='Instrument list' for t in at.tabs)
assert at.selectbox(key='inspect_instrument').value=='PT133035'
at.text_input(key='tag_query').set_value('PT133035')
next(b for b in at.button if b.label=='Find all occurrences').click().run()
assert not at.exception
report=at.session_state['search_bundle']['report']
assert report['occurrence_count']==1
match=report['groups']['process_drawing'][0]
assert match['source_detection_ids']==['pt','num']
assert any('Matched across separate OCR boxes' in i.value for i in at.info)
assert len(at.session_state['search_bundle']['crops'])==1
print('Instrument inventory tab, split-tag search and grouped UI evidence passed.')
