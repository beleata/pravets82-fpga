"""Fetch the exact external game data used by the SPI file adapter.

Stored only in ignored build/karateka. No downloaded host code is executed.
"""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
SOURCES=[
    ('prodos.po','https://raw.githubusercontent.com/a2-4am/4cade/main/res/dsk/karateka%20PRODOS%20%28san%20inc%20pack%29.po',
     '12c7990fb427f464d8ba9aa366514f505127d63d2351949318d201dae72e3efe'),
    ('appleiigo.rom','https://raw.githubusercontent.com/skryl/rhdl/8dc75799ba4e02045237760c3cd95827f14db387/examples/apple2/software/roms/appleiigo.rom',
     '6cb7e317e0036e4e006bc1c32fa79858d6d5c030a31a52d76a301c71020a10dd')]

def main():
    folder=ROOT/'build/karateka';folder.mkdir(parents=True,exist_ok=True);records=[]
    for name,url,sha in SOURCES:
        target=folder/name
        data=target.read_bytes() if target.exists() else urllib.request.urlopen(url,timeout=30).read()
        if hashlib.sha256(data).hexdigest()!=sha:raise RuntimeError('External data changed: '+name)
        if not target.exists():target.write_bytes(data)
        records.append(dict(file=name,url=url,size=len(data),sha256=sha))
        print(name,len(data),sha)
    (folder/'runtime-sources.json').write_text(json.dumps(records,indent=2)+'\n')

if __name__=='__main__':main()
