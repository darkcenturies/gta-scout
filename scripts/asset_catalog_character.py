"""Inspect and patch a rigid character head without rewriting its body or rig.

III's named rigid atomics are supported. Skinned/shared/native geometries and
multiple morphs are deliberately rejected. All native assets stay local.
"""
import argparse,hashlib,json,os,struct,subprocess,sys
from pathlib import Path
import numpy as np


def digest(data):return hashlib.sha256(data).hexdigest()


def chunks(data,start=0,end=None):
    end=len(data) if end is None else end
    while start<end:
        if end-start<12:raise ValueError('Truncated RenderWare header')
        kind,size,version=struct.unpack_from('<III',data,start);stop=start+12+size
        if stop>end:raise ValueError('RenderWare chunk exceeds parent')
        yield kind,start+12,stop,version
        start=stop


def child(data,parent):return list(chunks(data,parent[1],parent[2]))


def single(rows,kind):
    found=[r for r in rows if r[0]==kind]
    if len(found)!=1:raise ValueError('Missing or ambiguous chunk '+str(kind))
    return found[0]


def layout(data,head_name='Shead'):
    clump=single(list(chunks(data)),16)
    frame_rows=child(data,single(child(data,clump),14));fs=single(frame_rows,1)
    count=struct.unpack_from('<I',data,fs[1])[0]
    if fs[2]-fs[1]!=4+count*56:raise ValueError('Invalid frame table')
    extensions=[r for r in frame_rows if r[0]==3]
    if len(extensions)!=count:raise ValueError('Frame extensions differ')
    frames=[]
    for i,ext in enumerate(extensions):
        names=[data[r[1]:r[2]].split(b'\0')[0].decode('ascii') for r in child(data,ext) if r[0]==0x253f2fe]
        values=struct.unpack_from('<12fii',data,fs[1]+4+i*56)
        if values[12]<-1 or values[12]>=i:raise ValueError('Invalid frame parent')
        frames.append(dict(index=i,name=names[0] if len(names)==1 else '',parent=values[12],transform=list(values[:12])))
    matches=[r['index'] for r in frames if r['name'].casefold()==head_name.casefold()]
    if len(matches)!=1:raise ValueError('Missing or ambiguous named head frame')
    geometries=[r for r in child(data,single(child(data,clump),26)) if r[0]==15]
    bindings=[struct.unpack_from('<4I',data,single(child(data,r),1)[1])[:2] for r in child(data,clump) if r[0]==20]
    if any(fi>=count or gi>=len(geometries) for fi,gi in bindings):raise ValueError('Invalid atomic binding')
    heads=[gi for fi,gi in bindings if fi==matches[0]]
    if len(heads)!=1 or sum(gi==heads[0] for fi,gi in bindings)!=1:raise ValueError('Head geometry is missing or shared')
    gi=heads[0];geometry=geometries[gi];rows=child(data,geometry);s=single(rows,1)
    if any(r[0]==0x116 for ext in rows if ext[0]==3 for r in child(data,ext)):raise ValueError('Skinned character requires a different workflow')
    flags,nt,nv,nm=struct.unpack_from('<4I',data,s[1])
    if nm!=1 or flags&0x01000000 or not flags&16:raise ValueError('Unsupported native/morph/normal layout')
    stamp=s[3];version=stamp<<8 if stamp<0x10000 else ((stamp>>14)&0x3ff00)+0x30000|((stamp>>16)&0x3f)
    sets=(flags>>16)&255 or (2 if flags&128 else 1 if flags&4 else 0)
    uv=s[1]+16+(12 if version<0x34000 else 0)+(nv*4 if flags&8 else 0)
    triangle=uv+nv*8*sets;sphere=triangle+nt*8
    if sets!=1 or sphere+24+nv*24!=s[2] or struct.unpack_from('<2I',data,sphere+16)!=(1,1):raise ValueError('Unsupported head surface layout')
    return dict(frames=frames,frame=matches[0],geometry=gi,count=nv,triangle_count=nt,uv=uv,triangles=triangle,sphere=sphere,positions=sphere+24,normals=sphere+24+nv*12)


def inspect(data,head_name='Shead'):
    l=layout(data,head_name);n=l['count']
    xyz=np.frombuffer(data,'<f4',n*3,l['positions']).reshape(-1,3)
    uv=np.frombuffer(data,'<f4',n*2,l['uv']).reshape(-1,2)
    triangles=np.frombuffer(data,'<u2',l['triangle_count']*4,l['triangles']).reshape(-1,4)[:,[0,1,3]]
    if not np.isfinite(xyz).all() or not np.isfinite(uv).all() or triangles.max(initial=0)>=n:raise ValueError('Invalid head vertices/UVs/triangles')
    return dict(schema='scout-rigid-head-v1',source_sha256=digest(data),layout=l,vertices=xyz.tolist(),uv=uv.tolist(),triangles=triangles.tolist(),local_bounds=[xyz.min(0).tolist(),xyz.max(0).tolist()],scope='Native rigid head only; local frame axes are explicit, not inferred anatomical landmarks.')


def edit(data,packet,max_move=.05):
    if packet.get('source_sha256')!=digest(data):raise ValueError('Source changed since inspection')
    l=layout(data,packet.get('head_frame','Shead'));n=l['count']
    before=np.frombuffer(data,'<f4',n*3,l['positions']).reshape(-1,3).astype(float)
    after=before.copy();seen=set()
    for row in packet['edits']:
        i=row['vertex'];p=np.array(row['position'],dtype=float)
        if not isinstance(i,int) or isinstance(i,bool) or i<0 or i>=n or i in seen or p.shape!=(3,) or not np.isfinite(p).all():raise ValueError('Invalid or repeated vertex edit')
        if np.linalg.norm(p-before[i])>max_move:raise ValueError('Vertex exceeds movement bound')
        seen.add(i);after[i]=p
    tri=np.frombuffer(data,'<u2',l['triangle_count']*4,l['triangles']).reshape(-1,4)[:,[0,1,3]]
    if tri.max(initial=0)>=n:raise ValueError('Invalid triangle index')
    face=lambda v:np.cross(v[tri[:,1]]-v[tri[:,0]],v[tri[:,2]]-v[tri[:,0]])
    a,b=face(before),face(after)
    live=np.linalg.norm(a,axis=1)>1.e-12
    if ((a[live]*b[live]).sum(1)<=0).any():raise ValueError('Edit flips or collapses a triangle')
    if (np.linalg.norm(b[~live],axis=1)>1.e-12).any():raise ValueError('Edit separates a degenerate source seam')
    # Rotate authored normals by each vertex fan's change in direction. Keep
    # split normals instead of welding intentional texture/material seams.
    fans=[]
    for normals in (a,b):
        result=np.zeros((n,3))
        for column in range(3):np.add.at(result,tri[:,column],normals)
        fans.append(result)
    normals=np.frombuffer(data,'<f4',n*3,l['normals']).reshape(-1,3).astype(float)
    moved=set(np.where(np.any(after!=before,axis=1))[0])
    if not moved:return data
    affected={int(v) for t in tri if any(int(v) in moved for v in t) for v in t}
    for i in affected:
        u,v=fans[0][i],fans[1][i];lu,lv=np.linalg.norm(u),np.linalg.norm(v)
        if min(lu,lv)<1.e-12:continue
        u=u/lu;v=v/lv;cross=np.cross(u,v);c=float(np.dot(u,v))
        if c<=-.999:raise ValueError('Normal fan reverses')
        normal=normals[i]
        normals[i]=normal+np.cross(cross,normal)+np.cross(cross,np.cross(cross,normal))/(1+c)
        normals[i]/=np.linalg.norm(normals[i])
    result=bytearray(data);center=(after.min(0)+after.max(0))/2;radius=np.linalg.norm(after-center,axis=1).max()
    struct.pack_into('<4f',result,l['sphere'],*center,radius)
    result[l['positions']:l['normals']]=after.astype('<f4').tobytes()
    result[l['normals']:l['normals']+n*12]=normals.astype('<f4').tobytes()
    # Everything except the head sphere/positions/normals remains byte exact.
    return bytes(result)


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('inspect');p.add_argument('--dff',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--head-frame',default='Shead')
    p=commands.add_parser('edit');p.add_argument('--dff',type=Path,required=True);p.add_argument('--edits',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--max-move',type=float,default=.05)
    p=commands.add_parser('scene');p.add_argument('--dff',type=Path,required=True);p.add_argument('--texture',type=Path,required=True);p.add_argument('--head-texture',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--blender',required=True);p.add_argument('--dragonff',required=True);p.add_argument('--head-frame',default='Shead')
    p=commands.add_parser('compare');p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True);p.add_argument('--references',type=Path);p.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='compare':
        from asset_catalog_character_compare import compare
        print(compare(args.before,args.after,args.out,args.references));return
    data=args.dff.read_bytes()
    if args.out.exists():raise ValueError('Output exists; choose a fresh path')
    if args.out.resolve()==args.dff.resolve():raise ValueError('Source is read only')
    if args.command=='edit':
        if not np.isfinite(args.max_move) or args.max_move<=0 or args.max_move>.1:raise ValueError('Movement bound outside 0..0.1 meters')
        result=edit(data,json.loads(args.edits.read_text()),args.max_move);args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_bytes(result)
        print(json.dumps(dict(source_sha256=digest(data),output_sha256=digest(result),preserved='All bytes outside head sphere/positions/normals')))
    else:
        report=inspect(data,args.head_frame)
        args.out.mkdir(parents=True);(args.out/'head.json').write_text(json.dumps(report,indent=2)+'\n')
        if args.command=='scene':
            env=os.environ.copy();env['DRAGONFF_PATH']=str(Path(args.dragonff).resolve())
            script=Path(__file__).with_name('blender_character.py')
            if not script.is_file():script=Path(sys.prefix)/'share/gta-scout/blender_character.py'
            if not script.is_file():raise ValueError('Scout Blender bridge is missing from this installation')
            extra=['--head-texture',str(args.head_texture.resolve())] if args.head_texture else []
            subprocess.run([args.blender,'--background','--factory-startup','--threads','2','--python-exit-code','1','--python',str(script),'--','--dff',str(args.dff.resolve()),'--texture',str(args.texture.resolve()),'--out',str(args.out.resolve()),*extra],env=env,check=True)
        print(json.dumps({k:v for k,v in report.items() if k not in ('vertices','uv','triangles','layout')},indent=2))


if __name__=='__main__':main()
