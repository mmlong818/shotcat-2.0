import json,urllib.request,urllib.error,time
from pathlib import Path
from http_util import get_all
B="http://localhost:8000/api/v1"
def call(m,p,b=None,t=40):
    data=json.dumps(b).encode() if b is not None else None
    r=urllib.request.Request(B+p,data=data,headers={"Content-Type":"application/json"} if data else {},method=m)
    try:
        with urllib.request.urlopen(r,timeout=t) as x:return x.status,json.loads(x.read())
    except urllib.error.HTTPError as e:
        try:return e.code,json.loads(e.read().decode() or "{}")
        except:return e.code,{}
def items(p):return get_all(B,p)
pid="proj_echo"
dbshots=sorted(items(f"/studio/shots?chapter_id=proj_echo_ch01&page_size=100"),key=lambda s:s.get("index",0))
js=json.load(open(Path(__file__).with_name(f"shots-{pid}.json"),encoding="utf-8")).get("shots",[])
chars=items(f"/studio/entities/character?project_id={pid}&page_size=100")
name2id={c["name"]:c["id"] for c in chars}
print("DB镜头",len(dbshots),"json镜头",len(js),"角色",list(name2id))
linked=0
for i,ds in enumerate(dbshots):
    if i>=len(js):break
    for k,nm in enumerate(js[i].get("characters",[]) or []):
        cid=name2id.get(nm)
        if not cid:continue
        for _t in range(6):
            c,_=call("POST","/studio/shot-character-links",{"shot_id":ds["id"],"character_id":cid,"index":k})
            if c!=400:break
            time.sleep(1.0)
        if c<400:linked+=1
print("已建角色关联",linked,"条")
