import os, sys, json, time, pathlib, urllib.parse, concurrent.futures, subprocess, tempfile
import requests
import benchmark_media as bm

ALLOWED=("cdninstagram.com","fbcdn.net","ig.socialapi-v2.workers.dev")
def allowed(url):
    p=urllib.parse.urlparse(url)
    return p.scheme=="https" and not p.username and not p.password and any(p.hostname==x or (x!="ig.socialapi-v2.workers.dev" and (p.hostname or "").endswith("."+x)) for x in ALLOWED)
def download(item,d):
    started=time.monotonic()
    attempts=[]
    for url in item["urls"]:
        if not allowed(url):continue
        try:
            with requests.Session() as s:
                current=url
                for _ in range(4):
                    assert allowed(current)
                    r=s.get(current,stream=True,allow_redirects=False,timeout=(10,25),headers={"User-Agent":"reelbrain-lab/1.0","Accept":"video/*,image/*"})
                    if r.is_redirect:
                        current=urllib.parse.urljoin(current,r.headers["Location"]);r.close();continue
                    break
                with r:
                    attempts.append({"status":r.status_code})
                    if r.status_code!=200:continue
                    ct=r.headers.get("Content-Type","").lower()
                    if not (ct.startswith(("image/","video/")) or "octet-stream" in ct):continue
                    suffix=".mp4" if item["kind"]=="video" else ".jpg"
                    p=d/(str(item["index"]).zfill(2)+suffix)
                    n=0
                    with p.open("wb") as f:
                        for chunk in r.iter_content(65536):
                            n+=len(chunk)
                            if n>35*1024*1024:raise ValueError("size_limit")
                            if time.monotonic()-started>55:raise TimeoutError("download_time_limit")
                            f.write(chunk)
                    info=bm.probe(p)
                    if not info or (item["kind"]=="video" and info["duration_s"]<=0):continue
                    return p,info,{"seconds":round(time.monotonic()-started,3),"attempts":attempts}
        except Exception as e:attempts.append({"error":type(e).__name__})
    return None,None,{"seconds":round(time.monotonic()-started,3),"attempts":attempts}
def main():
    manifest=json.loads(pathlib.Path(sys.argv[1]).read_text())
    for case,items in manifest.items():
        start=time.monotonic();d=bm.ROOT/("bridge-"+case);d.mkdir()
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as e:
            acquired=list(e.map(lambda item:download(item,d),items))
        print("BRIDGE_ACQUISITION",json.dumps({"case":case,"expected":len(items),"received":sum(p is not None for p,i,m in acquired),"seconds":round(time.monotonic()-start,3),"assets":[{"index":item["index"],"kind":item["kind"],**m,"actual":i} for item,(p,i,m) in zip(items,acquired)]}),flush=True)
        results=[]
        for item,(p,i,m) in zip(items,acquired):
            if p is not None:
                try:results.append({"index":item["index"],**bm.analyze(p,i)})
                except Exception as e:results.append({"index":item["index"],"error":type(e).__name__})
        print("BRIDGE_RESULT",json.dumps({"case":case,"expected":len(items),"results":results,"wall_s":round(time.monotonic()-start,3)}),flush=True)
if __name__=="__main__":main()
