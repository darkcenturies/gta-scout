"""Run in Blender on a Scout character.blend to export head-only position edits.
blender -b character.blend --python export_character_edits.py -- --out edits.json
"""
import argparse,json,sys
from pathlib import Path
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
from asset_catalog_character import inspect,digest
from asset_catalog_dragon import clumps
import os
sys.path.insert(0,os.environ['DRAGONFF_PATH'])
from gtaLib.dff import dff


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if a.out.exists():raise ValueError('Output exists')
    scene=bpy.context.scene;source=Path(scene['scout_source_dff']);data=source.read_bytes()
    if digest(data)!=scene['scout_source_sha256']:raise ValueError('Source changed since scene preparation')
    native=dff();native.load_file(str(source));models=clumps(native)
    if len(models)!=1:raise ValueError('Expected single clump')
    model=models[0];head_geometry=scene['scout_head_geometry'];edits=[];seen=set()
    originals=inspect(data)
    for obj in bpy.data.objects:
        if 'native_geometry' not in obj:continue
        gi=obj['native_geometry'];fi=obj['native_frame'];g=model.geometry_list[gi]
        if (fi,gi) in seen:raise ValueError('Duplicate source object')
        seen.add((fi,gi))
        if obj.modifiers or len(obj.data.vertices)!=len(g.vertices):raise ValueError('Modifiers or changed vertex count')
        attribute=obj.data.attributes.get('native_vertex')
        if not attribute or [r.value for r in attribute.data]!=list(range(len(g.vertices))):raise ValueError('Native vertex identities changed')
        triangles=[(t.a,t.b,t.c) for t in g.triangles if len({t.a,t.b,t.c})==3 and (Vector(g.vertices[t.b])-Vector(g.vertices[t.a])).cross(Vector(g.vertices[t.c])-Vector(g.vertices[t.a])).length_squared>1.e-15]
        if [tuple(poly.vertices) for poly in obj.data.polygons]!=triangles:raise ValueError('Topology changed')
        # Prepared transforms are recorded in the source Blender object.
        expected=obj.get('scout_native_matrix')
        actual=[value for row in obj.matrix_world for value in row]
        if expected is None or max(abs(x-y) for x,y in zip(actual,expected))>1.e-6:raise ValueError('Frame transform changed')
        uv=obj.data.uv_layers.active
        if not uv:raise ValueError('UVs missing')
        for loop in obj.data.loops:
            native_uv=g.uv_layers[0][loop.vertex_index];actual=uv.data[loop.index].uv
            if abs(actual.x-native_uv.u)>1.e-6 or abs(actual.y-(1-native_uv.v))>1.e-6:raise ValueError('UVs changed')
        for i,(vertex,original) in enumerate(zip(obj.data.vertices,g.vertices)):
            if any(abs(vertex.co[j]-original[j])>1.e-8 for j in range(3)):
                if gi!=head_geometry:raise ValueError('Body vertex changed')
                edits.append(dict(vertex=i,position=list(vertex.co)))
    if seen!={(atomic.frame,atomic.geometry) for atomic in model.atomic_list}:raise ValueError('Source object missing')
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(dict(source_sha256=digest(data),head_frame=originals['layout']['frames'][originals['layout']['frame']]['name'],edits=edits),indent=2)+'\n')
    print('SCOUT_HEAD_EDITS',len(edits))


if __name__=='__main__':main()
