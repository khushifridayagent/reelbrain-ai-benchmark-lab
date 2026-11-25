import unittest, tempfile, pathlib, numpy as np, cv2, json
from native_intelligence.core import Inspector, Frame, Observation, accept_sender_event, finalize
class CoreTests(unittest.TestCase):
    def test_one_frame_and_chroma_changes_are_inspected(self):
        a=np.zeros((48,64,3),dtype=np.uint8); b=a.copy(); b[10,10]=[255,0,0]
        c=a.copy();c[20,20]=[0,0,255]
        calls=[]
        def read(p): calls.append(p.copy()); return Observation("one-frame" if np.array_equal(p,b) else "other",(),True)
        r=Inspector(read).scan([Frame(0,0,a),Frame(1,16.67,b),Frame(2,33.33,a),Frame(3,50,c)])
        self.assertEqual(r['frames_seen'],4);self.assertEqual(len(calls),3)
        self.assertEqual(r['frame_index'][1]['timestamp_ms'],16.67)
        self.assertEqual(r['observations'][r['frame_index'][1]['sha256']]['text'],'one-frame')
        self.assertTrue(r['ocr_complete'])
    def test_ocr_failure_does_not_count_as_complete(self):
        a=np.zeros((4,4,3),np.uint8)
        r=Inspector(lambda x:Observation('',(),False)).scan([Frame(0,0,a)])
        self.assertFalse(r['ocr_complete'])
    def test_incomplete_frame_count_and_budget_are_explicit(self):
        a=np.zeros((4,4,3),np.uint8)
        r=Inspector(lambda x:Observation('ok',(),True),max_frames=1).scan([Frame(0,0,a),Frame(1,33,a)],expected_frames=2)
        self.assertFalse(r['decode_complete']); self.assertFalse(r['ocr_complete'])
    def test_no_unverified_promotion(self):
        self.assertEqual(finalize(True,True,True,False),'needs_review')
        self.assertEqual(finalize(True,True,False,True),'needs_review')
        self.assertEqual(finalize(False,True,True,True),'partial')
        self.assertEqual(finalize(True,True,True,True),'reviewed')
    def test_dm_allowlist_exact_account_and_sender(self):
        event={'sender':{'id':'11'},'recipient':{'id':'99'},'message':{'mid':'m1','attachments':[{'type':'ig_reel','payload':{'url':'https://www.instagram.com/reel/abc/','video_id':'42'}}]}}
        self.assertEqual(accept_sender_event(event,'99',{'11','22','33'})['mid'],'m1')
        self.assertIsNone(accept_sender_event(event,'99',{'22'}))
        self.assertIsNone(accept_sender_event(event,'98',{'11'}))
        event['message']['is_echo']=True
        self.assertIsNone(accept_sender_event(event,'99',{'11'}))
if __name__=='__main__':unittest.main()
