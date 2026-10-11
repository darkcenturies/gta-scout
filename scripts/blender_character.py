"""Scout's rigid-head Blender scene bridge; inspect before editing landmarks."""
import argparse,hashlib,json,math,os,runpy,sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from asset_catalog_character import inspect,digest
from asset_catalog_dragon import clumps
sys.path.insert(0,os.environ['DRAGONFF_PATH'])
from gtaLib.dff import dff


def main():
    p=argparse.ArgumentParser();p.add_argument('--dff',type=Path,required=True);p.add_argument('--texture',type=Path,required=True);p.add_argument('--head-texture',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    a.dff=a.dff.resolve();a.texture=a.texture.resolve();a.out=a.out.resolve()
    report=json.loads((a.out/'head.json').read_text());native=dff();native.load_file(str(a.dff));model=clumps(native)
    if len(model)!=1:raise ValueError('Only one rigid character clump supported')
    model=model[0]
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    binding={t.name:str(a.texture) for g in model.geometry_list for m in g.materials for t in m.textures}
    if len(binding)!=1:raise ValueError('Single-atlas workflow requires exactly one source texture name')
    renderer=runpy.run_path(str(ROOT/'render-asset-catalog-views.py'))
    objects,missing=renderer['build'](dict(id='iii:local-character',model='Claude',dff=str(a.dff),textures=binding))
    if missing:raise ValueError('Missing source textures: '+repr(missing))
    head=None
    for obj,atomic in zip(objects,model.atomic_list):
        frame=model.frame_list[atomic.frame];name=frame.name if hasattr(frame,'name') else report['layout']['frames'][atomic.frame]['name']
        obj.name=name or ('Frame_'+str(atomic.frame));obj['native_geometry']=atomic.geometry;obj['native_frame']=atomic.frame
        g=model.geometry_list[atomic.geometry]
        if g.normals and len(g.normals)==len(obj.data.vertices):
            for poly in obj.data.polygons:poly.use_smooth=True
            obj.data.normals_split_custom_set_from_vertices(g.normals)
        ids=obj.data.attributes.new('native_vertex','INT','POINT')
        for i,value in enumerate(ids.data):value.value=i
        if atomic.geometry==report['layout']['geometry']:head=obj
    if head is None:raise ValueError('Head not imported')
    if a.head_texture:
        image=bpy.data.images.load(str(a.head_texture.resolve()),check_existing=True)
        for material in head.data.materials:
            for node in material.node_tree.nodes:
                if node.type=='TEX_IMAGE':node.image=image
    bpy.context.view_layer.update()
    for obj in objects:obj['scout_native_matrix']=[value for row in obj.matrix_world for value in row]
    points=[head.matrix_world@v.co for v in head.data.vertices]
    lo=Vector([min(v[i] for v in points) for i in range(3)]);hi=Vector([max(v[i] for v in points) for i in range(3)]);center=(lo+hi)/2
    basis=head.matrix_world.to_3x3();up=(basis@Vector((1,0,0))).normalized();front=(basis@Vector((0,1,0))).normalized();side=(basis@Vector((0,0,1))).normalized()
    height=max((v-center).dot(up) for v in points)-min((v-center).dot(up) for v in points)
    scene=bpy.context.scene;scene.render.engine='BLENDER_EEVEE_NEXT';scene.render.resolution_x=512;scene.render.resolution_y=512;scene.render.resolution_percentage=100
    scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.18,.18,.18,1);scene.world.node_tree.nodes['Background'].inputs[1].default_value=.6
    scene.view_settings.view_transform='Standard';scene.view_settings.look='Medium High Contrast';scene.view_settings.exposure=0
    bpy.ops.object.light_add(type='AREA',location=center+front*.7+up*.6+side*.2);light=bpy.context.object;light.data.energy=5;light.data.size=.8;light.rotation_euler=(center-light.location).to_track_quat('-Z','Y').to_euler()
    views=[]
    for name,direction in [('front',front),('profile',side),('rear',-front)]:
        bpy.ops.object.camera_add();camera=bpy.context.object;camera.name='Scout_'+name;scene.camera=camera
        camera.location=center+direction*1.5;right=up.cross(direction).normalized();real_up=direction.cross(right).normalized()
        camera.rotation_euler=Matrix((right,real_up,direction)).transposed().to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=height*1.25;camera.data.lens=70
        target=a.out/(name+'.png');scene.render.filepath=str(target);bpy.ops.render.render(write_still=True)
        views.append(dict(view=name,path=str(target),sha256=digest(target.read_bytes()),camera='Orthographic; native head frame axes; unchanged bind pose'))
    scene['scout_source_dff']=str(a.dff);scene['scout_source_sha256']=report['source_sha256'];scene['scout_head_geometry']=report['layout']['geometry']
    scene['scout_body_preservation']='Edit only the named head mesh, without modifiers, changing vertex positions only.'
    bpy.ops.object.select_all(action='DESELECT');head.select_set(True);bpy.context.view_layer.objects.active=head
    for obj in objects:
        if obj!=head:obj.hide_select=True
    text=bpy.data.texts.new('SCOUT_README');text.write('Native source: '+str(a.dff)+'\nEdit only '+head.name+'. native_vertex identifies every original vertex. Body objects are locked for selection. Cameras use head-frame axes. This is an unchanged bind-pose inspection, not a gameplay pose. Export edits with export_character_edits.py, then asset-catalog-character edit.\n')
    blend=a.out/'character.blend';bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    result=dict(source_sha256=report['source_sha256'],texture_sha256=digest(a.texture.read_bytes()),blender=bpy.app.version_string,dragonff_sha256=digest(Path(os.environ['DRAGONFF_PATH'],'gtaLib/dff.py').read_bytes()),views=views,editable_scene=str(blend),scope='Static native rigid-frame character. No gameplay or animation claim.')
    if a.head_texture:result['head_texture_sha256']=digest(a.head_texture.read_bytes())
    (a.out/'scene-report.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
