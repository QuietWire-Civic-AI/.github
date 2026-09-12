#!/usr/bin/env python3
"""Build a public-only atlas from explicit public curation and fresh anonymous API data.
No private catalog, authentication token, or private relationship is read here.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
import re
import sys
import urllib.request

ORG='QuietWire-Civic-AI'
NAME=re.compile(r'^[A-Za-z0-9_.-]{1,100}$')
class PublicError(ValueError): pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise PublicError('Unexpected public API redirect')

def anonymous_repositories():
    rows=[]; ids=set()
    for page in range(1,101):
        url=f'https://api.github.com/orgs/{ORG}/repos?type=public&per_page=100&page={page}&sort=full_name&direction=asc'
        req=urllib.request.Request(url,headers={'Accept':'application/vnd.github+json','User-Agent':'QuietWire-Public-Atlas/1'})
        # Deliberately no environment token, netrc, cookies, or Authorization header.
        with urllib.request.build_opener(NoRedirect).open(req,timeout=30) as res:
            raw=res.read(8_000_001)
            if len(raw)>8_000_000: raise PublicError('Public listing too large')
            batch=json.loads(raw)
        if not isinstance(batch,list): raise PublicError('Invalid public listing')
        for r in batch:
            if r.get('private') is not False or r.get('visibility')!='public' or r.get('owner',{}).get('login','').lower()!=ORG.lower() or r['id'] in ids:
                raise PublicError('Non-public, foreign, or repeated repository in public input')
            ids.add(r['id']); rows.append({'id':r['id'],'name':r['name'],'visibility':'public','archived':r['archived']})
        if len(batch)<100: return rows
    raise PublicError('Public pagination incomplete')

def project(curation, observations):
    if set(curation)!={'schema','organization','repositories'} or curation['schema']!='quietwire.public-curation/v1' or curation['organization']!=ORG:
        raise PublicError('Unsupported public curation schema')
    current={}; names=set()
    for r in observations:
        if set(r)!={'id','name','visibility','archived'} or r['visibility']!='public' or type(r['archived']) is not bool or type(r['id']) is not int or r['id']<=0 or not isinstance(r['name'],str) or not NAME.fullmatch(r['name']):
            raise PublicError('Invalid public observation')
        if r['id'] in current or r['name'].lower() in names: raise PublicError('Duplicate public observation')
        current[r['id']]=r; names.add(r['name'].lower())
    rows=[]; seen=set(); seen_names=set()
    for c in curation['repositories']:
        if set(c)!={'id','name','summary','approved_at'} or type(c['id']) is not int or c['id']<=0 or not isinstance(c['name'],str) or not NAME.fullmatch(c['name']):
            raise PublicError('Unexpected public curation fields')
        if c['id'] in seen or c['name'].lower() in seen_names: raise PublicError('Duplicate public curation')
        seen.add(c['id']); seen_names.add(c['name'].lower())
        if not isinstance(c['summary'],str) or not 1<=len(c['summary'])<=1000 or any(ord(x)<32 for x in c['summary']):
            raise PublicError('Invalid public description')
        try:
            if not isinstance(c['approved_at'],str) or dt.date.fromisoformat(c['approved_at']).isoformat()!=c['approved_at']: raise ValueError()
        except ValueError:
            raise PublicError('Invalid publication review date') from None
        r=current.get(c['id'])
        if r is None: continue  # No longer anonymously public: omit, never fall back.
        rows.append({'id':r['id'],'name':r['name'],'url':f'https://github.com/{ORG}/{r["name"]}',
                     'summary':c['summary'],'archived':r['archived']})
    return {'schema':'quietwire.public-repository-atlas/v1','organization':ORG,'scope':'public','repositories':sorted(rows,key=lambda r:r['name'].lower()),'relations':[]}

def safe(value):
    return value.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('|','&#124;').replace('[','&#91;').replace(']','&#93;').replace('`','&#96;')

def outputs(data):
    lines=['# QuietWire Civic AI','','QuietWire works on Civic AI, provenance, and human/AI collaboration. This is the public repository entrance.', '',
           '**Start with the scope and status in each repository.** A public repository may contain historical, experimental, or demonstration material; its presence is not proof of a production service.', '',
           'For machines: [public Atlas JSON](https://github.com/QuietWire-Civic-AI/.github/blob/main/atlas/public.json). For contributors: [agent navigation](https://github.com/QuietWire-Civic-AI/.github/blob/main/AGENTS.md).', '',
           '## Public repository map','','This map contains only explicitly curated repositories verified in an anonymous GitHub listing. It does not enumerate restricted repositories or imply that additional access should be requested.', '',
           '| Repository | Purpose |','|---|---|']
    for r in data['repositories']:
        suffix=' GitHub marks this repository archived.' if r['archived'] else ''
        lines.append(f'| [{r["name"]}]({r["url"]}) | {safe(r["summary"]+suffix)} |')
    lines += ['','## Boundaries','','Discovery is not execution authority. Read the repository-local README and agent instructions. Verify current source and runtime separately. Respect the access provided by the human or organization you are working with.','','Updates are proposed through reviewable pull requests. No repository code is executed to generate this map.']
    return {'atlas/public.json':json.dumps(data,indent=2,sort_keys=True)+'\n','profile/README.md':'\n'.join(lines)+'\n'}

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--root',type=Path,default=Path.cwd()); a=p.parse_args()
    c=json.loads((a.root/'atlas/curation.json').read_text())
    data=project(c,anonymous_repositories())
    # Only write after the entire observation and projection succeeds.
    for name,body in outputs(data).items():
        path=a.root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(body)
    print(f'Public atlas: {len(data["repositories"])} verified, explicitly curated repositories')
if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('Public refresh stopped; no partial API listing is published: '+type(exc).__name__,file=sys.stderr); sys.exit(1)
