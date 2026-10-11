"""Create a local reference/original/edited head contact sheet, with provenance."""
import json
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw
from asset_catalog_character import digest


def compare(before,after,out,references=None):
    out=Path(out)
    if out.exists():raise ValueError('Output exists')
    reports=[json.loads(Path(path).read_text()) for path in (before,after)]
    source_maps=[];provenance=[]
    for report in reports:
        source={row['view']:row for row in report['views']}
        if set(source)!={'front','profile','rear'}:raise ValueError('Expected front/profile/rear evidence')
        for row in source.values():
            path=Path(row['path']);data=path.read_bytes()
            if digest(data)!=row['sha256']:raise ValueError('Render evidence changed')
            provenance.append(dict(path=str(path),sha256=row['sha256']))
        source_maps.append(source)
    refs=json.loads(Path(references).read_text()) if references else None
    if refs is not None and set(refs)!={'front','profile','rear'}:raise ValueError('Expected three reference views')
    cols=3 if refs else 2;tile=384;margin=20;label=38
    sheet=Image.new('RGB',(cols*(tile+margin)+margin,3*(tile+label+margin)+margin),'#202329');draw=ImageDraw.Draw(sheet)
    for row,name in enumerate(('front','profile','rear')):
        inputs=[]
        if refs:
            ref=refs[name];path=Path(ref['path']);data=path.read_bytes();image=Image.open(path);image.load()
            crop=ref.get('crop',[0,0,image.width,image.height])
            if len(crop)!=4 or any(not isinstance(v,int) for v in crop) or not(0<=crop[0]<crop[2]<=image.width and 0<=crop[1]<crop[3]<=image.height):raise ValueError('Invalid reference crop')
            provenance.append(dict(path=str(path),sha256=digest(data),crop=crop));inputs.append(('Reference',image.crop(crop)))
        for title,source in zip(('Original','Edited'),source_maps):
            with Image.open(source[name]['path']) as image:inputs.append((title,image.copy()))
        for col,(title,image) in enumerate(inputs):
            x=margin+col*(tile+margin);y=margin+row*(tile+label+margin)
            draw.text((x,y),name.title()+' - '+title,fill='white')
            fit=ImageOps.contain(image.convert('RGB'),(tile,tile),Image.Resampling.NEAREST)
            sheet.paste(fit,(x+(tile-fit.width)//2,y+label+(tile-fit.height)//2))
    out.mkdir(parents=True);sheet.save(out/'comparison.png')
    report=dict(schema='scout-head-comparison-v1',sources=provenance,comparison_sha256=digest((out/'comparison.png').read_bytes()),scope='Visual contact sheet. Reference perspective/pose/lighting can differ; no automatic likeness verdict.')
    (out/'comparison-report.json').write_text(json.dumps(report,indent=2)+'\n')
    return out/'comparison.png'
