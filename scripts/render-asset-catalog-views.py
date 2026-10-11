#!/usr/bin/env python3
"""Blender CLI textured static-DFF previews. No orientation is assumed.
blender -b --python scripts/render-asset-catalog-views.py -- --input batch.json --output DIR
Input: {"assets":[{"id":"sa:model:...","model":"...","dff":"/file.dff",
"textures":{"texture_name":"/texture.png"},"sourceFiles":["/original.txd"]}]}
"""
import os
import argparse, hashlib, json, math, sys, time, traceback
from array import array
from pathlib import Path
import bpy
from mathutils import Matrix, Vector
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'scripts'))
from asset_catalog_image_signal import pixel_signal
from asset_catalog_dragon import clumps
DRAGONFF_ROOT=Path(os.environ.get('DRAGONFF_PATH', str(ROOT/'references/DragonFF')))
sys.path.insert(0, str(DRAGONFF_ROOT))
from gtaLib.dff import dff


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(asset):
    data = dff(); data.load_file(str(Path(asset['dff']).resolve()))
    objects, missing = [], set()
    for clump in clumps(data):
        objs, absent = build_clump(asset, clump)
        objects.extend(objs);missing.update(absent)
    return objects, sorted(missing)


def build_clump(asset, data):
    objects, missing = [], set()
    texpaths = {k.lower(): str(Path(v).resolve()) for k,v in asset.get('textures',{}).items()}
    frame_cache = {}
    def frame_matrix(idx, trail=()):
        if idx in frame_cache: return frame_cache[idx]
        if idx in trail: raise ValueError('Cyclic frame hierarchy')
        frame = data.frame_list[idx]
        local = Matrix.Translation(frame.position) @ Matrix((frame.rotation_matrix.right, frame.rotation_matrix.up, frame.rotation_matrix.at)).transposed().to_4x4()
        if frame.parent >= 0: local = frame_matrix(frame.parent, trail+(idx,)) @ local
        frame_cache[idx] = local
        return local
    atomics = [(a.geometry,a.frame) for a in data.atomic_list]
    if not atomics: raise ValueError('No static atomics in DFF')
    for index, (gi,fi) in enumerate(atomics):
        g = data.geometry_list[gi]
        if 'skin' in g.extensions: raise ValueError('Skinned DFF unsupported; use full DragonFF importer')
        faces = [t for t in g.triangles if len({t.a,t.b,t.c})==3 and (Vector(g.vertices[t.b])-Vector(g.vertices[t.a])).cross(Vector(g.vertices[t.c])-Vector(g.vertices[t.a])).length_squared > 1e-15]
        mesh = bpy.data.meshes.new('source_geometry'); mesh.from_pydata(g.vertices, [], [(t.a,t.b,t.c) for t in faces]);mesh.update()
        obj = bpy.data.objects.new(asset.get('model',asset['id'])+f'_{index}',mesh); bpy.context.collection.objects.link(obj);objects.append(obj)
        obj.matrix_world = frame_matrix(fi)
        for material in g.materials:
            m = bpy.data.materials.new('source_material');m.use_nodes=True;nodes=m.node_tree.nodes;links=m.node_tree.links;bs=nodes.get('Principled BSDF');bs.inputs['Roughness'].default_value=.85
            bs.inputs['Base Color'].default_value=tuple(c/255 for c in material.color)
            if material.textures:
                name = material.textures[0].name.lower();path=texpaths.get(name)
                if path and Path(path).is_file():
                    tex=nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(path,check_existing=True);tex.interpolation='Closest';links.new(tex.outputs['Color'],bs.inputs['Base Color']);links.new(tex.outputs['Alpha'],bs.inputs['Alpha'])
                else:
                    missing.add(name);bs.inputs['Base Color'].default_value=(1,0,1,1)
            elif g.prelit_colors:
                attr=nodes.new('ShaderNodeVertexColor');attr.layer_name='NativeColor';links.new(attr.outputs['Color'],bs.inputs['Base Color'])
            mesh.materials.append(m)
        mesh.uv_layers.new(name='UVMap')
        colors=mesh.color_attributes.new(name='NativeColor',type='BYTE_COLOR',domain='CORNER')
        # Adding a corner attribute can reallocate Blender's layer storage.
        # Retrieve the UV layer afterwards; a stale RNA handle corrupts memory.
        uv=mesh.uv_layers['UVMap']
        for polygon,t in zip(mesh.polygons,faces):
            polygon.material_index=t.material
            for li in polygon.loop_indices:
                vi=mesh.loops[li].vertex_index
                if g.uv_layers: uv.data[li].uv=(g.uv_layers[0][vi].u,1-g.uv_layers[0][vi].v)
                colors.data[li].color=tuple(c/255 for c in g.prelit_colors[vi]) if g.prelit_colors else (1,1,1,1)
    if not objects or not any(len(o.data.vertices) for o in objects):raise ValueError('Empty model')
    return objects, sorted(missing)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True);p.add_argument('--output',required=True);p.add_argument('--size',type=int,default=384);p.add_argument('--samples',type=int,default=12);args=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    recipe={'rendererSha256':sha(__file__),'signalCheckerSha256':sha(ROOT/'scripts/asset_catalog_image_signal.py'),'dragonAdapterSha256':sha(ROOT/'scripts/asset_catalog_dragon.py'),'dragonParserSha256':sha(DRAGONFF_ROOT/'gtaLib/dff.py'),'blender':bpy.app.version_string,'engine':'CYCLES','samples':args.samples,'resolution':args.size,'azimuthDegrees':[45,135,225,315],'elevationDegrees':25,'textureFilter':'Closest','texturedPrelight':'omitted for neutral material inspection','untexturedPrelight':'preserved','frameHierarchy':'preserved','geometry':'all static atomics; no inferred front; skinned rejected'}
    report={'recipe':recipe,'assets':[]};start=time.time()
    for asset in json.loads(Path(args.input).read_text())['assets']:
        record={'id':asset['id'],'model':asset.get('model',asset['id']),'sourceExtraction':asset.get('sources',[]),'status':'failed'}
        try:
            sources=sorted(set([asset['dff']]+list(asset.get('textures',{}).values())+asset.get('sourceFiles',[])))
            hashes={str(Path(f).resolve()):sha(f) for f in sources}
            fingerprint=hashlib.sha256(json.dumps({'recipe':recipe,'sources':hashes,'textureMapping':asset.get('textures',{})},sort_keys=True).encode()).hexdigest()
            folder=out/fingerprint[:20];folder.mkdir(exist_ok=True);cache=folder/'manifest.json'
            if cache.exists():
                prior=json.loads(cache.read_text())
                if prior.get('fingerprint')==fingerprint and all(Path(v['path']).is_file() and sha(v['path'])==v['sha256'] for v in prior.get('views',[])) and len(prior.get('views',[]))==4:
                    prior.update({'id':asset['id'],'model':record['model'],'cacheHit':True});report['assets'].append(prior);continue
            bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
            for collection in (bpy.data.meshes,bpy.data.materials,bpy.data.images,bpy.data.cameras,bpy.data.lights):
                for block in list(collection):
                    if block.users==0:collection.remove(block)
            objects,missing=build(asset);bpy.context.view_layer.update()
            points=[o.matrix_world@Vector(c) for o in objects for c in o.bound_box]
            lo=Vector([min(v[i] for v in points) for i in range(3)]);hi=Vector([max(v[i] for v in points) for i in range(3)]);center=(lo+hi)/2;radius=max((v-center).length for v in points)
            if radius<1e-6:raise ValueError('Degenerate bounds')
            scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=args.samples;scene.cycles.use_denoising=True;scene.render.resolution_x=args.size;scene.render.resolution_y=args.size;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG';scene.render.film_transparent=False
            scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.35,.35,.35,1);scene.world.node_tree.nodes['Background'].inputs[1].default_value=.8;scene.view_settings.view_transform='Standard'
            bpy.ops.object.light_add(type='AREA',location=center+Vector((radius,-radius,radius*3)));light=bpy.context.object;light.data.energy=radius*radius*180;light.data.size=radius*4
            bpy.ops.object.camera_add();camera=bpy.context.object;scene.camera=camera;camera.data.type='ORTHO';camera.data.ortho_scale=radius*2.3;camera.data.clip_end=max(1000,radius*20)
            views=[]
            for az in recipe['azimuthDegrees']:
                a=math.radians(az);el=math.radians(25);camera.location=center+Vector((math.cos(a)*math.cos(el),math.sin(a)*math.cos(el),math.sin(el)))*radius*5;camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler();path=folder/f'azimuth-{az:03d}.png';scene.render.filepath=str(path);bpy.ops.render.render(write_still=True)
                rendered=bpy.data.images.load(str(path),check_existing=False);pixels=array('f',[0])*len(rendered.pixels);rendered.pixels.foreach_get(pixels);signal=pixel_signal(pixels,rendered.channels);bpy.data.images.remove(rendered)
                views.append({'azimuthDegrees':az,'elevationDegrees':25,'path':str(path),'sha256':sha(path),'signal':signal})
            blank=all(v['signal']['uniform'] for v in views)
            low_signal=all(v['signal']['low_signal'] for v in views)
            record.update({'status':'blank_render' if blank else 'low_signal_render' if low_signal else 'incomplete_textures' if missing else 'ready','cacheHit':False,'fingerprint':fingerprint,'sourceSha256':hashes,'missingTextures':missing,'boundsMin':list(lo),'boundsMax':list(hi),'triangles':sum(len(o.data.polygons) for o in objects),'views':views,'recipe':recipe})
            if blank:record['error']='All four views are uniform; this render provides no visible object evidence. Another preview/context is required.'
            elif low_signal:record['warning']='All four views have very low signal; may be invisible effect geometry, background noise, or a thin/low-contrast object. Requires actual visual review/context, not automatic rejection.'
            cache.write_text(json.dumps(record,indent=2)+'\n')
        except Exception as exc:
            record['error']=str(exc);record['traceback']=traceback.format_exc()
        report['assets'].append(record);(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print('ASSET_PREVIEW',record['id'],record['status'],flush=True)
    report['seconds']=round(time.time()-start,2);(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print('PREVIEW_BATCH',json.dumps({'assets':len(report['assets']),'seconds':report['seconds'],'manifest':str(out/'manifest.json')}),flush=True)

if __name__=='__main__':main()
