"""Read-only classic PC GTA metadata adapter; emits no game binaries/pixels."""
import argparse
import hashlib
import json
import struct
from pathlib import Path


def relative_file(root, name):
    parts = name.replace('\\', '/').split('/')
    if any(p in ('..', '') for p in parts) or Path(name).is_absolute():
        raise ValueError('Unsafe game-relative path: '+name)
    current = root
    for part in parts:
        matches = [p for p in current.iterdir() if p.name.casefold() == part.casefold()]
        if len(matches) != 1:
            raise ValueError('Missing or ambiguous path: '+name)
        current = matches[0]
    if not current.resolve().is_relative_to(root.resolve()):
        raise ValueError('Source escapes game root')
    return current


def chunks(data, start=0, end=None):
    end = len(data) if end is None else end
    while start < end:
        if end-start < 12:
            raise ValueError('Truncated RenderWare header')
        kind, size, version = struct.unpack_from('<III', data, start)
        stop = start+12+size
        if stop > end:
            raise ValueError('RenderWare chunk outside parent bounds')
        yield kind, start+12, stop
        start = stop


def txd_names(data):
    if len(data)<12: raise ValueError('Truncated TXD')
    kind, size, _ = struct.unpack_from('<III', data)
    if kind != 0x16 or size > len(data)-12: raise ValueError('Invalid TXD dictionary')
    result=[]; declared=None
    for kind, begin, end in chunks(data, 12, 12+size):
        if kind == 1:
            if end-begin<4: raise ValueError('Truncated TXD structure')
            declared=struct.unpack_from('<H',data,begin)[0]
        if kind != 0x15: continue
        structures=[(a,b) for k,a,b in chunks(data,begin,end) if k==1]
        if len(structures)!=1: raise ValueError('Native texture structure missing/ambiguous')
        a,b=structures[0]
        if b-a<72: raise ValueError('Truncated native texture metadata')
        platform=struct.unpack_from('<I',data,a)[0]
        if platform not in (8,9): raise ValueError('Only PC D3D8/9 TXDs supported')
        name=data[a+8:a+40].split(b'\0')[0].decode('ascii')
        if not name: raise ValueError('Empty native texture name')
        result.append(name)
    if declared is None or declared!=len(result): raise ValueError('Native texture count mismatch')
    if len(set(result))!=len(result): raise ValueError('Repeated native texture names in dictionary')
    return result


def img_entries(path):
    with path.open('rb') as stream:
        header=stream.read(8)
        if header[:4]!=b'VER2':
            # III/VC store the 32-byte directory beside the sector-only IMG.
            directory=relative_file(path.parent,path.stem+'.dir')
            rows=directory.read_bytes();size=path.stat().st_size
            if len(rows)%32:raise ValueError('Truncated IMG v1 directory')
            names=set()
            for index in range(0,len(rows),32):
                sector,sectors=struct.unpack_from('<II',rows,index)
                name=rows[index+8:index+32].split(b'\0')[0].decode('ascii')
                if not name or '/' in name or '\\' in name or name in ('.','..'):raise ValueError('Invalid IMG entry name')
                if name.casefold() in names:raise ValueError('Repeated IMG entry name')
                names.add(name.casefold())
                offset,length=sector*2048,sectors*2048
                if not length or offset+length>size:raise ValueError('IMG entry out of bounds')
                yield name,offset,length
            return
        if len(header)!=8:raise ValueError('Truncated IMG v2 header')
        count=struct.unpack_from('<I',header,4)[0]; size=path.stat().st_size
        if count>(size-8)//32: raise ValueError('Invalid IMG directory count')
        for index in range(count):
            row=stream.read(32); sector,sectors,archive_sectors=struct.unpack_from('<IHH',row)
            name=row[8:].split(b'\0')[0].decode('ascii')
            length=(sectors or archive_sectors)*2048; offset=sector*2048
            if offset<8+count*32 or offset+length>size: raise ValueError('IMG entry out of bounds')
            if '/' in name or '\\' in name: raise ValueError('Invalid IMG entry name')
            yield name,offset,length


def inventory(game, output, extra_ides=(), extra_archives=(), game_id='sa'):
    game=Path(game).resolve(); output=Path(output).resolve()
    if output.exists(): raise ValueError('Output exists; choose a new directory to preserve prior snapshots')
    if output.is_relative_to(game): raise ValueError('Output must be outside the game installation')
    if game_id not in ('sa','iii','vc'):raise ValueError('Unsupported game')
    dat=relative_file(game,{'sa':'data/gta.dat','iii':'data/gta3.dat','vc':'data/gta_vc.dat'}[game_id])
    ides=[relative_file(game,'data/default.ide')]
    for line in dat.read_text(encoding='latin1').splitlines():
        line=line.split('#',1)[0].strip()
        if line.upper().startswith('IDE '): ides.append(relative_file(game,line[4:].strip()))
    ides += [Path(p).resolve() for p in extra_ides]
    models={}; provenance=[]
    for ide in dict.fromkeys(ides):
        data=ide.read_bytes(); provenance.append({'path':str(ide),'sha256':hashlib.sha256(data).hexdigest()})
        section=''
        for line in data.decode('latin1').splitlines():
            line=line.split('#',1)[0].strip()
            if not line: continue
            if ',' not in line: section='' if line.lower()=='end' else line.lower(); continue
            if section not in ('objs','tobj','anim','cars','peds','weap','hier'): continue
            cols=[p.strip() for p in line.split(',')]
            if len(cols)<3: raise ValueError('Short model row in '+str(ide))
            model_id=int(cols[0]); record={'id':model_id,'name':cols[1],'dff':cols[1],'txd':cols[2], 'source':ide.name,'ide':str(ide),'section':section,'tags':[]}
            if model_id in models and any(models[model_id][field]!=record[field] for field in ('name','txd')): raise ValueError('Conflicting model ID '+str(model_id))
            models[model_id]=record
    folder=relative_file(game,'models')
    archives=sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower()=='.img')+[Path(p).resolve() for p in extra_archives]
    textures=[]; failures=[]
    def read_dictionary(data, name, source):
        try:
            for texture in txd_names(data): textures.append({'name':texture,'txd':name,'source':source})
        except (ValueError,UnicodeError,struct.error) as error: failures.append({'source':source,'txd':name,'error':str(error)})
    for archive in dict.fromkeys(archives):
        try:
            entries=list(img_entries(archive))
            with archive.open('rb') as stream:
                for name,offset,length in entries:
                    if not name.lower().endswith('.txd'): continue
                    if length>64*1024*1024: raise ValueError('TXD larger than 64 MiB bound')
                    stream.seek(offset); read_dictionary(stream.read(length),name[:-4],str(archive))
        except (ValueError,UnicodeError,struct.error) as error: failures.append({'source':str(archive),'error':str(error)})
    for path in sorted(folder.rglob('*')):
        if path.is_file() and path.suffix.lower()=='.txd': read_dictionary(path.read_bytes(),path.stem,str(path))
    result={'adapter':'classic-pc-'+game_id+'-v2','game':game_id,'gameRoot':str(game),'models':len(models),'textures':len(textures),'failures':failures,'sourceIDEs':provenance,
            'scope':'Active game DAT IDEs plus default.ide and explicit extras; IMG v1/v2 and loose PC TXD metadata. Mod Loader priority is not resolved. No rendered evidence, semantic labels, placement graph, or standalone DFF/clothing census.'}
    for name, value in [('models/data/models.json',{'models':list(models.values())}),('textures/data/textures.json',{'textures':textures}),('source-report.json',result)]:
        target=output/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_text(json.dumps(value,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-root',required=True);parser.add_argument('--out',required=True)
    parser.add_argument('--game',choices=('sa','iii','vc'),default='sa')
    parser.add_argument('--ide',action='append',default=[]);parser.add_argument('--archive',action='append',default=[])
    args=parser.parse_args()
    print(json.dumps(inventory(args.game_root,args.out,args.ide,args.archive,args.game),indent=2))

if __name__=='__main__': main()
