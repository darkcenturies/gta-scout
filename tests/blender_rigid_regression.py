"""Optional game-free Blender regression for UV storage and repeated meshes.
blender -b --factory-startup --python tests/blender_rigid_regression.py
DRAGONFF_PATH must point at the installed parser; no native model is loaded.
"""
import json,runpy,sys
from pathlib import Path
from types import SimpleNamespace as N
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
r=runpy.run_path(str(ROOT/'scripts/render-asset-catalog-views.py'))
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
g=N(vertices=[(0,0,0),(1,0,0),(0,1,0)],triangles=[N(a=0,b=1,c=2,material=0)],materials=[N(color=(255,255,255,255),textures=[])],extensions={},prelit_colors=[(255,128,64,255)]*3,uv_layers=[[N(u=.2,v=.3),N(u=.8,v=.3),N(u=.2,v=.9)]])
frame=N(position=(0,0,0),rotation_matrix=N(right=(1,0,0),up=(0,1,0),at=(0,0,1)),parent=-1)
data=N(geometry_list=[g],frame_list=[frame],atomic_list=[N(geometry=0,frame=0)]*16)
objects,missing=r['build_clump'](dict(id='synthetic-rigid'),data)
assert len(objects)==16 and missing==[]
for obj in objects:
 for loop in obj.data.loops:
  uv=obj.data.uv_layers['UVMap'].data[loop.index].uv;source=g.uv_layers[0][loop.vertex_index]
  assert abs(uv.x-source.u)<1.e-6 and abs(uv.y-(1-source.v))<1.e-6
  color=obj.data.color_attributes['NativeColor'].data[loop.index].color
  assert color[0]>.99 and color[1]>.2
print('PASS: sixteen synthetic rigid atomics; UV and colour attributes intact.',flush=True)
