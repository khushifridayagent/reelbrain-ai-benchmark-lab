"""Local evidence worker: no publication, no production access, no automatic DB writes."""
import argparse, json, pathlib, tempfile, subprocess, shutil, os, re, time, hashlib
from concurrent.futures import ThreadPoolExecutor
import cv2, numpy as np
from .core import Inspector, Observation, video_frames, finalize

def run_ocr(pixels):
    """Preserve original text and add targeted enlarged evidence. Do not autocorrect URLs."""
    try:
        ok,encoded=cv2.imencode('.png',pixels)
        if not ok:return Observation('',(),False,'encode_failed')
        def read(img,psm):
            ok,b=cv2.imencode('.png',img)
            if not ok:raise ValueError('encode_failed')
            p=subprocess.run(['tesseract','stdin','stdout','-l',os.getenv('RB_OCR_LANG','eng+hin'),'--psm',str(psm)],
                             input=b.tobytes(),capture_output=True,timeout=30)
            if p.returncode:raise RuntimeError('tesseract_failed')
            return p.stdout.decode('utf-8',errors='replace').strip()
        original=read(pixels,11)
        # Inspect regions with separate OCR regardless of whether a URL was detected.
        h,w=pixels.shape[:2]; extra=[]
        for y0,y1 in [(0,(h+1)//2),(max(0,h//2-h//12),h)]:
            crop=pixels[y0:y1]
            zoom=cv2.resize(crop,None,fx=1.5,fy=1.5,interpolation=cv2.INTER_CUBIC)
            txt=read(zoom,11)
            if txt and txt not in extra and txt!=original:extra.append(txt)
        qr=set();det=cv2.QRCodeDetector()
        try:
            found,values,_,_=det.detectAndDecodeMulti(pixels)
            if found:qr.update(x for x in values if x)
        except cv2.error:pass
        try:
            val,_,_=det.detectAndDecode(pixels)
            if val:qr.add(val)
        except cv2.error:pass
        return Observation('\n'.join([original]+extra),tuple(sorted(qr)),True)
    except Exception as e:return Observation('',(),False,type(e).__name__)

def inspect_media(path,max_frames=None,max_seconds=None):
    path=pathlib.Path(path)
    if path.suffix.lower() in ('.jpg','.jpeg','.png','.webp'):
        from .core import Frame
        im=cv2.imread(str(path))
        if im is None:raise ValueError('image_not_decodable')
        expected,fps,frames=1,None,iter([Frame(0,0,im)])
    else:expected,fps,frames=video_frames(path)
    result=Inspector(run_ocr,max_frames,max_seconds).scan(frames,expected)
    result['fps']=fps
    result['source_sha256']=hashlib.file_digest(path.open('rb'),'sha256').hexdigest()
    result['state']=finalize(result['decode_complete'],result['ocr_complete'],False,False)
    # URL candidates are evidence, never verified hyperlinks; preserve exact characters.
    for v in result['observations'].values():
        v['url_candidates']=[{'raw':s,'status':'unverified'} for s in sorted(set(re.findall(r'https?://[^\s<>"\x27]+|github\.com/[^\s<>"\x27]+',v['text'])))]
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('--out',required=True)
    p.add_argument('--max-frames',type=int);p.add_argument('--max-seconds',type=float)
    a=p.parse_args()
    r=inspect_media(a.source,a.max_frames,a.max_seconds)
    out=pathlib.Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    temp=out.with_suffix(out.suffix+'.tmp')
    with temp.open('w',encoding='utf-8') as f:json.dump(r,f,ensure_ascii=False)
    os.replace(temp,out)
    print(json.dumps({k:r[k] for k in ('state','frames_seen','unique_frames','decode_complete','ocr_complete','elapsed_s')}))
if __name__=='__main__':main()
