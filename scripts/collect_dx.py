#!/usr/bin/env python3
"""Collect public DX-cluster spots; never fabricate reception reports."""
import datetime as dt, json, os, re, socket, time
from pathlib import Path
OUT=Path("data/dx-spots.json")
PAT=re.compile(r"DX de\s+(\S+):\s+(\d+(?:\.\d+)?)\s+(\S+)\s+(.+?)\s+(\d{4})Z",re.I)
def collect():
    spots=[]; errors=[]
    for host,port in [("dxc.nc7j.com",7373),("cluster.dl9gtb.de",8000)]:
        try:
            with socket.create_connection((host,port),timeout=12) as sock:
                sock.settimeout(3)
                sock.sendall(b"N0CALL-99\r\n")
                until=time.monotonic()+40; buf=""
                while time.monotonic()<until:
                    try: data=sock.recv(8192)
                    except socket.timeout: continue
                    if not data: break
                    buf+=data.decode("utf-8","replace")
                    lines=buf.split("\n");buf=lines.pop()
                    for line in lines:
                        m=PAT.search(line)
                        if not m: continue
                        spotter,khz,dx,comment,utc=m.groups()
                        freq=float(khz)/1000
                        if not 1.8<=freq<=30: continue
                        mode=next((x for x in ("FT8","FT4","RTTY","PSK31","CW","SSB","USB","LSB","AM") if re.search(r"\b"+x+r"\b",comment,re.I)),"Non indicato")
                        spots.append(dict(frequency_mhz=round(freq,4),mode=mode,dx=dx,spotter=spotter,utc=utc,comment=comment.strip()[:110],source=host))
                if spots: break
        except (OSError,ValueError) as e: errors.append(host+": "+str(e)[:100])
    return spots,errors
def main():
    now=dt.datetime.now(dt.timezone.utc)
    spots,errors=collect()
    existing={}
    if OUT.exists():
        try: existing=json.loads(OUT.read_text())
        except (ValueError,OSError): pass
    previous=existing.get("spots",[])
    for x in spots:
        hhmm=x["utc"]; h,m=int(hhmm[:2]),int(hhmm[2:])
        t=now.replace(hour=h,minute=m,second=0,microsecond=0)
        if t>now+dt.timedelta(minutes=5):t-=dt.timedelta(days=1)
        x["timestamp"]=t.isoformat().replace("+00:00","Z")
    combined=spots+previous
    unique={}
    for x in combined:
        try:
            t=dt.datetime.fromisoformat(x["timestamp"].replace("Z","+00:00"))
            if now-t>dt.timedelta(hours=2) or t>now+dt.timedelta(minutes=5):continue
            key=(x["dx"],x["frequency_mhz"],x["timestamp"],x["spotter"])
            unique[key]=x
        except (KeyError,ValueError,TypeError):continue
    result={"checked_at":now.isoformat().replace("+00:00","Z"),"status":"ok" if spots else "unavailable","new_spots":len(spots),"errors":errors,"spots":sorted(unique.values(),key=lambda x:x["timestamp"],reverse=True)[:250]}
    OUT.parent.mkdir(exist_ok=True,parents=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
if __name__=="__main__":main()
