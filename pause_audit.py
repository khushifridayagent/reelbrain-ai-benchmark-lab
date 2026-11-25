"""Native-frame audit, not a production pipeline. No source media is persisted."""
import os,cv2,numpy as np,time,json,subprocess,concurrent.futures,re,pathlib
import benchmark_media as bm
os.environ['OMP_THREAD_LIMIT']='1'
cv2.setNumThreads(1)
def run_audit(case,p):
    start=time.monotonic(); cap=cv2.VideoCapture(str(p)); fps=cap.get(cv2.CAP_PROP_FPS); expected=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));prev=None;oldprev=None;count=0;old_ids=set();tile_ids=set();unique=set();candidates=[];all_changed=0;last=None
    step=max(1,int(fps/10))
    while True:
        ok,f=cap.read()
        if not ok:break
        g=cv2.cvtColor(f,cv2.COLOR_BGR2GRAY);small=cv2.resize(g,(120,120))
        if count%step==0:
            if oldprev is None or cv2.absdiff(small,oldprev).mean()>3:
                old_ids.add(count);oldprev=small
        if prev is None:
            tile_ids.add(count)
        else:
            delta=cv2.absdiff(g,prev)
            # Native pixels; count localized changes, without relying on whole-frame mean.
            mask=(delta>25).astype(np.uint8)
            h,w=mask.shape;pad=np.pad(mask,((0,(-h)%48),(0,(-w)%64)))
            tilemax=int(pad.reshape(pad.shape[0]//48,48,pad.shape[1]//64,64).sum(axis=(1,3)).max())
            if tilemax>=8:tile_ids.add(count)
            if np.any(delta):all_changed+=1
        # Compare every decoded frame, no frame skipping.
        prev=g;count+=1
    cap.release()
    print('NATIVE_AUDIT',json.dumps({'case':case,'fps':fps,'container_frames':expected,'decoded_frames':count,'duration_s':count/fps,'old_10fps_selected':len(old_ids),'native_tile_candidates':len(tile_ids),'pixel_changed_frames':all_changed,'new_candidates_not_in_old':len(tile_ids-old_ids),'scan_s':round(time.monotonic()-start,3)}),flush=True)
def main():
    for case in ('reel1','reel2'):
        r=bm.acquire(case,bm.CASES[case])
        if not r['assets']:
            print('NATIVE_AUDIT',json.dumps({'case':case,'acquired':False}),flush=True);continue
        p,info=r['assets'][0];run_audit(case,p)
if __name__=='__main__':main()
