import json,tempfile,unittest
from datetime import datetime
from pathlib import Path
from PIL import Image
from sorter_core import Photo,build_outputs,call_rest_provider
class FakeProvider:
    def generate(self,prompt,photos,image_bytes):
        for p in photos: self.data=image_bytes(p.path)
        return json.dumps({"items":[{"filename":p.path.name,"same_product_as_previous":i>0,"category":"mouse","view":"front" if i==0 else "back","brand":"Demo","model":"M1","catalog_match":"","confidence":.99,"reason":"synthetic"} for i,p in enumerate(photos)]})
class SyntheticIntegrationTests(unittest.TestCase):
    def test_images_flow_provider_to_output_report(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); src=root/"src"; out=root/"out"; src.mkdir(); photos=[]
            for i in range(2):
                p=src/f"{i}.jpg"; Image.new("RGB",(20,20),(i*50,0,0)).save(p); photos.append(Photo(p,datetime.now()))
            result=call_rest_provider(FakeProvider(),photos,"")
            items=[{**x,"path":photos[i].path,"taken_at":photos[i].taken_at} for i,x in enumerate(result["items"])]
            build_outputs(items,out,.75,False)
            self.assertTrue((out/"classification_report.csv").is_file()); self.assertTrue(any((out/"mouse").rglob("*.jpg")))
if __name__=="__main__":unittest.main()
