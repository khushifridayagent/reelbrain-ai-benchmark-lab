"""Exact-frame inspection core. Evidence is retained separately from semantic conclusions."""
from dataclasses import dataclass
from typing import Callable, Iterable
import hashlib, json, os, time
import cv2
import numpy as np

@dataclass(frozen=True)
class Frame:
    index: int
    timestamp_ms: float
    pixels: np.ndarray

@dataclass(frozen=True)
class Observation:
    text: str
    qr: tuple[str,...]
    ok: bool
    error: str | None = None

def digest(pixels):
    a=np.ascontiguousarray(pixels)
    # Exact color bytes: not grayscale, perceptual hash or a similarity threshold.
    h=hashlib.sha256()
    h.update(str((a.shape,a.dtype.str)).encode());h.update(a.tobytes())
    return h.hexdigest()

class Inspector:
    def __init__(self,read:Callable,max_frames=None, max_seconds=None):
        self.read=read;self.max_frames=max_frames;self.max_seconds=max_seconds
    def scan(self,frames:Iterable[Frame],expected_frames=None):
        start=time.monotonic();obs={};idx=[];exhausted=True;ordered=True
        for frame in frames:
            if ((self.max_frames is not None and len(idx)>=self.max_frames)
                or (self.max_seconds is not None and time.monotonic()-start>=self.max_seconds)):
                exhausted=False;break
            if frame.index!=len(idx):ordered=False
            key=digest(frame.pixels)
            if key not in obs or not obs[key]['ok']:
                try:
                    result=self.read(frame.pixels)
                    obs[key]={'text':result.text,'qr':list(result.qr),'ok':bool(result.ok),'error':result.error}
                except Exception as e:
                    obs[key]={'text':'','qr':[],'ok':False,'error':type(e).__name__}
            idx.append({'frame':frame.index,'timestamp_ms':frame.timestamp_ms,'sha256':key})
        complete=bool(idx) and exhausted and ordered and (expected_frames is None or len(idx)==expected_frames)
        return {'frames_seen':len(idx),'unique_frames':len(obs),'decode_complete':complete,
                'ocr_complete':complete and all(v['ok'] for v in obs.values()),
                'frame_index':idx,'observations':obs,'elapsed_s':round(time.monotonic()-start,3),
                'expected_frames':expected_frames,'sampling':'all_native_frames_exact_duplicates_only'}

def finalize(decode_complete,ocr_complete,providers_complete,review_approved):
    if not decode_complete or not ocr_complete:return 'partial'
    if not providers_complete or not review_approved:return 'needs_review'
    return 'reviewed'

def accept_sender_event(event,recipient,allowlist):
    # Exact string IDs, scoped to the configured receiving account. Never trust usernames.
    if not isinstance(event,dict):return None
    s=event.get('sender');r=event.get('recipient');m=event.get('message')
    if not all(isinstance(x,dict) for x in (s,r,m)):return None
    if r.get('id')!=recipient or s.get('id') not in allowlist:return None
    if m.get('is_echo') or m.get('is_deleted') or not isinstance(m.get('mid'),str) or not m['mid']:return None
    return {'mid':m['mid'],'sender_id':s['id'],'recipient_id':recipient,'text':m.get('text',''),
            'attachments':m.get('attachments',[])}

def video_frames(path):
    cap=cv2.VideoCapture(str(path))
    if not cap.isOpened():cap.release();raise ValueError('video_not_decodable')
    expected=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));fps=cap.get(cv2.CAP_PROP_FPS)
    def iterate():
        i=0
        try:
            while True:
                ok,p=cap.read()
                if not ok:break
                timestamp=cap.get(cv2.CAP_PROP_POS_MSEC)
                if not np.isfinite(timestamp) or (i>0 and timestamp<=0):
                    timestamp=i*1000/fps if fps>0 else -1
                yield Frame(i,round(timestamp,4),p);i+=1
        finally:cap.release()
    return expected or None,fps,iterate()
