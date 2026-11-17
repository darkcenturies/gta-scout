import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from asset_catalog_scene_audit import audit


class SceneAuditTests(unittest.TestCase):
    def fixture(self):
        surface = dict(texture_identity=['fixture', 'toy', 'wall'], texture_sha256='a'*64,
                       geometry_surface=[1,1,1], material_surface=[1,.05,1])
        return dict(schema=1, placements=[dict(id='toy_hut', evidence='synthetic authored inverted local axes',
            world_matrix=[[1,0,0,0],[0,-1,0,0],[0,0,-1,2],[0,0,0,1]],
            local_up=[0,0,-1], expected_world_up=[0,0,1],
            contacts=[dict(local_point=[0,0,2],support_world=[0,0,0],support_normal=[0,0,1],gap_range=[-.01,.01])])],
            surfaces=[dict(id='toy_surface', baseline=surface, candidate=copy.deepcopy(surface))])

    def test_inverted_local_axes_need_original_rotation(self):
        data=self.fixture();self.assertTrue(audit(data)['passed'])
        data['placements'][0]['world_matrix']=[[1,0,0,0],[0,1,0,0],[0,0,1,-2],[0,0,0,1]]
        result=audit(data)
        self.assertFalse(result['findings'][0]['passed'])
        self.assertTrue(result['findings'][1]['passed'])  # grounded is not upright

    def test_texture_identity_does_not_prove_surface_match(self):
        data=self.fixture();data['surfaces'][0]['candidate']['material_surface']=[1,.5,.88]
        self.assertFalse(audit(data)['passed'])

    def test_reject_malformed_and_empty(self):
        self.assertFalse(audit(dict(schema=1))['passed'])
        for bad in (float('nan'),float('inf')):
            data=self.fixture();data['placements'][0]['world_matrix'][0][0]=bad
            with self.assertRaises(ValueError):audit(data)

    def test_negative_scale_and_support_gap(self):
        data=self.fixture();data['placements'][0]['world_matrix'][0][0]=-1
        self.assertFalse(audit(data)['passed'])
        data=self.fixture();data['placements'][0]['world_matrix'][2][3]=3
        self.assertFalse(audit(data)['passed'])


if __name__=='__main__':unittest.main()
