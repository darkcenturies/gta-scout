import json,struct,sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from asset_catalog_character import inspect,edit,layout,digest


def fixture(shared=False,version=0x310):
    def chunk(kind,payload):return struct.pack('<III',kind,len(payload),version)+payload
    matrix=struct.pack('<12fii',1,0,0,0,1,0,0,0,1,0,0,0,-1,0)
    head=struct.pack('<12fii',1,0,0,0,1,0,0,0,1,0,0,1,0,0)
    fs=chunk(14,chunk(1,struct.pack('<I',2)+matrix+head)+chunk(3,chunk(0x253f2fe,b'Body\0'))+chunk(3,chunk(0x253f2fe,b'Shead\0')))
    positions=np.array([[0,0,0],[.02,0,0],[.02,.02,0],[0,.02,0]],dtype='<f4')
    normals=np.array([[0,0,1]]*4,dtype='<f4')
    legacy=struct.pack('<3f',1,1,1) if version==0x310 else b''
    geometry=chunk(15,chunk(1,struct.pack('<4I',0x10074,2,4,1)+legacy+struct.pack('<8f',0,0,1,0,1,1,0,1)+struct.pack('<8H',0,1,0,2,0,2,0,3)+struct.pack('<4f2I',0,0,0,1,1,1)+positions.tobytes()+normals.tobytes())+chunk(3,b''))
    gl=chunk(26,chunk(1,struct.pack('<I',2))+geometry+geometry)
    atomic=lambda frame,gi:chunk(20,chunk(1,struct.pack('<4I',frame,gi,5,0))+chunk(3,b''))
    return chunk(16,chunk(1,struct.pack('<3I',2,0,0))+fs+gl+atomic(0,1 if shared else 0)+atomic(1,1))


class HeadWorkflowTests(unittest.TestCase):
    def packet(self,data,edits):return dict(source_sha256=digest(data),edits=edits)
    def test_no_edits_is_exact_roundtrip_and_legacy_and_new_headers(self):
        for version in (0x310,0x1803ffff):
            data=fixture(version=version);r=inspect(data)
            self.assertEqual(r['layout']['geometry'],1);self.assertEqual(r['layout']['count'],4)
            self.assertEqual(data,edit(data,self.packet(data,[])))
    def test_patch_preserves_body_rig_uv_materials_and_topology(self):
        data=fixture();l=layout(data)
        output=edit(data,self.packet(data,[dict(vertex=2,position=[.02,.02,.003])]))
        ranges=[(l['sphere'],l['sphere']+16),(l['positions'],l['normals']+l['count']*12)]
        allowed=np.zeros(len(data),dtype=bool)
        for a,b in ranges:allowed[a:b]=True
        np.testing.assert_array_equal(np.frombuffer(data,'u1')[~allowed],np.frombuffer(output,'u1')[~allowed])
        norms=np.frombuffer(output,'<f4',12,l['normals']).reshape(-1,3)
        np.testing.assert_allclose(np.linalg.norm(norms,axis=1),1,atol=1.e-6)
        center=np.array(struct.unpack_from('<3f',output,l['sphere']));radius=struct.unpack_from('<f',output,l['sphere']+12)[0]
        points=np.frombuffer(output,'<f4',12,l['positions']).reshape(-1,3)
        self.assertLessEqual(np.linalg.norm(points-center,axis=1).max(),radius+1.e-7)
    def test_invalid_or_stale_edits_and_face_collapse_are_rejected(self):
        data=fixture()
        cases=[dict(vertex=2,position=[float('nan'),0,0]),dict(vertex=4,position=[0,0,0]),dict(vertex=True,position=[0,0,0]),dict(vertex=2,position=[2,0,0]),dict(vertex=2,position=[0,0,0]),dict(vertex=2,position=[-.02,-.02,0])]
        for row in cases:
            with self.assertRaises(ValueError):edit(data,self.packet(data,[row]))
        row=dict(vertex=2,position=[.02,.02,.001])
        with self.assertRaises(ValueError):edit(data,self.packet(data,[row,row]))
        with self.assertRaisesRegex(ValueError,'Source changed'):edit(data,dict(source_sha256='0'*64,edits=[]))
    def test_shared_head_and_malformed_parent_bounds_rejected(self):
        with self.assertRaisesRegex(ValueError,'shared'):inspect(fixture(shared=True))
        for data in (b'',fixture()[:-1],fixture()[:12]):
            with self.assertRaises(ValueError):inspect(data)


import json,tempfile,unittest
from pathlib import Path
from PIL import Image
from asset_catalog_character_compare import compare
class ComparisonTests(unittest.TestCase):
    def test_three_views_and_stale_evidence(self):
        from asset_catalog_character import digest
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);views=[];refs={}
            for name in ('front','profile','rear'):
                path=root/(name+'.png');Image.new('RGB',(16,16),'red').save(path)
                views.append(dict(view=name,path=str(path),sha256=digest(path.read_bytes())))
                refs[name]=dict(path=str(path),crop=[1,1,15,15])
            report=root/'report.json';report.write_text(json.dumps(dict(views=views)));references=root/'refs.json';references.write_text(json.dumps(refs))
            result=compare(report,report,root/'sheet',references)
            with Image.open(result) as image:self.assertEqual(image.size,(1232,1346))
            Image.new('RGB',(16,16),'blue').save(path)
            with self.assertRaisesRegex(ValueError,'evidence changed'):compare(report,report,root/'stale')
            self.assertFalse((root/'stale').exists())

if __name__=='__main__':unittest.main()
