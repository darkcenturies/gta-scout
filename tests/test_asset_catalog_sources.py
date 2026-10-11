import struct, sys, tempfile, unittest, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import asset_catalog_sources as s

def chunk(k,b): return struct.pack('<III',k,len(b),0)+b

def texture(name):
    return chunk(0x15,chunk(1,struct.pack('<II',9,0)+name.encode().ljust(32,b'\0')+bytes(32)))

def txd(name='fixture'): return chunk(0x16,chunk(1,struct.pack('<HH',1,0))+texture(name))

class SourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.game=self.root/'game';(self.game/'DATA').mkdir(parents=True);(self.game/'MODELS').mkdir()
        (self.game/'DATA/GTA.DAT').write_text('IDE data\\custom.ide\n')
        (self.game/'DATA/default.ide').write_text('objs\n1, fixture_a, fixture_txd, 1, 100, 0\nend\n')
        (self.game/'DATA/custom.ide').write_text('objs\n2, fixture_b, fixture_txd, 1, 100, 0\nend\n')
    def test_inventory_case_insensitive_and_sources_read_only(self):
        path=self.game/'MODELS/loose.txd';path.write_bytes(txd());before=path.read_bytes()
        report=s.inventory(self.game,self.root/'out')
        self.assertEqual((report['models'],report['textures'],report['failures']),(2,1,[]));self.assertEqual(before,path.read_bytes())
        rows=json.loads((self.root/'out/textures/data/textures.json').read_text())['textures'];self.assertEqual(rows[0]['source'],str(path.resolve()))
    def test_reject_game_output_existing_snapshot_and_conflicting_id(self):
        with self.assertRaisesRegex(ValueError,'outside'):s.inventory(self.game,self.game/'out')
        (self.root/'out').mkdir()
        with self.assertRaisesRegex(ValueError,'exists'):s.inventory(self.game,self.root/'out')
        (self.game/'DATA/custom.ide').write_text('objs\n1, other, x, 1, 50, 0\nend\n')
        with self.assertRaisesRegex(ValueError,'Conflicting'):s.inventory(self.game,self.root/'out2')
        self.assertFalse((self.root/'out2').exists())
    def test_invalid_txd_reported_not_silently_counted(self):
        (self.game/'MODELS/broken.txd').write_bytes(b'broken')
        r=s.inventory(self.game,self.root/'out');self.assertEqual(len(r['failures']),1);self.assertEqual(r['textures'],0)
    def test_archive_and_same_name_dictionaries_preserve_occurrences(self):
        data=txd();entry=struct.pack('<IHH',1,1,0)+b'shared.txd'.ljust(24,b'\0')
        for name in ['first.img','second.img']:
            (self.game/'MODELS'/name).write_bytes((b'VER2'+struct.pack('<I',1)+entry).ljust(2048,b'\0')+data.ljust(2048,b'\0'))
        self.assertEqual(s.inventory(self.game,self.root/'out')['textures'],2)
    def test_malformed_chunk_bounds_and_platform(self):
        for data in [b'',txd()[:20],chunk(0x16,chunk(1,struct.pack('<HH',2,0))+texture('x')),chunk(0x16,chunk(1,struct.pack('<HH',1,0))+chunk(0x15,chunk(1,bytes(72))))]:
            with self.assertRaises(ValueError): s.txd_names(data)
    def test_no_parent_traversal(self):
        with self.assertRaises(ValueError):s.relative_file(self.game,'../other')
    def test_invalid_img_offsets(self):
        p=self.root/'bad.img';p.write_bytes(b'VER2'+struct.pack('<I',1)+struct.pack('<IHH',99,1,0)+b'x.txd'.ljust(24,b'\0'))
        with self.assertRaises(ValueError):list(s.img_entries(p))
    def test_iii_dat_and_external_img_directory(self):
        (self.game/'DATA/GTA.DAT').rename(self.game/'DATA/GTA3.DAT')
        p=self.game/'MODELS/gta3.img';p.write_bytes(txd().ljust(2048,b'\0'))
        p.with_suffix('.DIR').write_bytes(struct.pack('<II24s',0,1,b'fixture.txd'))
        r=s.inventory(self.game,self.root/'iii',game_id='iii')
        self.assertEqual((r['game'],r['models'],r['textures'],r['failures']),('iii',2,1,[]))
        self.assertEqual(list(s.img_entries(p)),[('fixture.txd',0,2048)])
    def test_img_v1_bounds_traversal_duplicates_and_partial_records(self):
        p=self.root/'x.img';p.write_bytes(bytes(2048));directory=p.with_suffix('.dir')
        cases=[b'bad',struct.pack('<II24s',1,1,b'x.txd'),struct.pack('<II24s',0,0,b'x.txd'),struct.pack('<II24s',0,1,b'../x.txd'),struct.pack('<II24s',0,1,b'x.txd')*2]
        for rows in cases:
            directory.write_bytes(rows)
            with self.assertRaises(ValueError):list(s.img_entries(p))
if __name__=='__main__':unittest.main()
