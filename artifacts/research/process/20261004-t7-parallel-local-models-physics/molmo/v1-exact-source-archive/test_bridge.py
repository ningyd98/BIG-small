"""Real online-boundary checks; no model/network/GPU mocks."""
import base64,io,struct,unittest,json,tempfile,subprocess,sys,os,hashlib
from pathlib import Path
from datetime import UTC,datetime
from PIL import Image
from cloud_edge_robot_arm.vision.observations import RGBDObservation
import native_bridge as b

class BridgeBoundaryTests(unittest.TestCase):
 def test_duplicate_and_unknown_case_filter_rejected(self):
  cases=[{'case_id':'a','instruction':'one'},{'case_id':'b','instruction':'two'}]
  for requested in (['typo'],['a','a'],[]):
   with self.subTest(requested=requested),self.assertRaises(ValueError):b.select_cases(cases,requested)
  with self.assertRaises(ValueError):b.select_cases([cases[0],cases[0]],None)
 def test_selected_case_order_is_frozen_as_requested(self):
  cases=[{'case_id':'a','instruction':'one'},{'case_id':'b','instruction':'two'}]
  self.assertEqual(b.select_cases(cases,['b','a']),[cases[1],cases[0]])
 def test_raw_json_file_is_exclusive_and_first_result_preserved(self):
  with tempfile.TemporaryDirectory() as tmp:
   file=Path(tmp)/'raw.json';b.write_exclusive_json(file,{'raw_text':'first result'})
   with self.assertRaises(FileExistsError):b.write_exclusive_json(file,{'raw_text':'second result'})
   self.assertEqual(json.loads(file.read_text()),{'raw_text':'first result'})
 def test_existing_run_output_is_rejected_before_protocol_write(self):
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp)/'run';out.mkdir()
   with self.assertRaises(FileExistsError):b.freeze_run_output(out,{'case_ids':['a']},bank=True)
   self.assertEqual(list(out.iterdir()),[])
 def test_protocol_is_frozen_before_any_raw_result(self):
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp)/'run';protocol={'allocation':[{'case_id':'a','transport_sha256':'0'*64}]}
   b.freeze_run_output(out,protocol,bank=True)
   self.assertTrue((out/'protocol.json').is_file())
   self.assertEqual(json.loads((out/'protocol.json').read_text())['allocation'],[{'case_id':'a','transport_sha256':'0'*64}])
   self.assertEqual([p.name for p in out.iterdir()],['protocol.json'])
 def test_cli_unknown_filter_fails_before_weights_or_gpu_load(self):
  with tempfile.TemporaryDirectory() as tmp:
   bank=Path(tmp)/'bank';bank.mkdir();(bank/'bank-manifest.json').write_text(json.dumps({'cases':[{'case_id':'a','instruction':'one'}]}))
   out=Path(tmp)/'run'
   command=[sys.executable,str(Path(b.__file__).resolve()),'--model','Molmo2-4B','--mode','screen','--bank',str(bank),'--cases','typo','--gpu-lease','CPU_TEST_ONLY','--out',str(out)]
   result=subprocess.run(command,capture_output=True,text=True,env={**os.environ,'CUDA_VISIBLE_DEVICES':''})
   self.assertNotEqual(result.returncode,0)
   self.assertIn('unknown requested case IDs',result.stderr)
   self.assertFalse(out.exists())
 def test_two_images_are_rgb_then_depth_and_metadata_never_enters_text(self):
  image=Image.new('RGB',(2,2),'red');out=io.BytesIO();image.save(out,format='PNG')
  obs=RGBDObservation(frame_id='private-frame-marker',captured_at=datetime(2026,10,4,tzinfo=UTC),sim_time_s=0,width=2,height=2,rgb_png_base64=base64.b64encode(out.getvalue()).decode(),depth_float32_base64=base64.b64encode(struct.pack('<ffff',1,1,1,1)).decode(),intrinsics=(1,1,0,0),camera_to_world=(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1),source='mujoco_camera')
  messages=b.build_messages('把红色方块放入绿色区域。',obs,'target')
  self.assertIsInstance(messages,list)
  self.assertEqual(len(messages),1)
  parts=messages[0]['content'];images=[p['image'] for p in parts if p['type']=='image'];texts=[p['text'] for p in parts if p['type']=='text']
  self.assertEqual(len(images),2)
  self.assertEqual([x.size for x in images],[(2,2),(2,2)])
  self.assertEqual([x.getpixel((0,0)) for x in images],[(255,0,0),(1,1,1)])
  self.assertIn('把红色方块放入绿色区域。',texts[0])
  self.assertNotIn('private-frame-marker',' '.join(texts))
  evidence=b.actual_image_evidence(messages,obs)
  expected={'image_count':2,'images':[{'index':0,'role':'RGB','size':[2,2],'mode':'RGB','decoded_rgb_pixel_sha256':hashlib.sha256(bytes([255,0,0])*4).hexdigest()},
             {'index':1,'role':'DEPTH','size':[2,2],'mode':'RGB','decoded_rgb_pixel_sha256':hashlib.sha256(bytes([1,1,1])*4).hexdigest()}],
             'observation_binding':{'frame_id':'private-frame-marker','observation_id':'private-frame-marker','checksum_sha256':obs.checksum_sha256}}
  self.assertEqual(evidence,expected)
 def test_inference_requires_explicit_nonempty_gpu_lease(self):
  with self.assertRaises(ValueError):b.require_gpu_lease(None)
  with self.assertRaises(ValueError):b.require_gpu_lease('')

if __name__=='__main__':unittest.main()

class AttemptEvidenceTests(unittest.TestCase):
 def test_completed_call_and_generated_raw_survive_later_failure(self):
  with tempfile.TemporaryDirectory() as tmp:
   journal=b.AttemptJournal(Path(tmp)/'attempts','a'*64)
   first=b.run_recorded_call(lambda:{'raw_text':'first raw','raw_token_ids':[7]},journal,'case.target',{'image_count':2})
   self.assertEqual(first['raw_token_ids'],[7])
   def later():
    journal.record('case.destination','generated',{'raw_text':'second raw','raw_token_ids':[8]})
    raise RuntimeError('decoder failed after generation')
   with self.assertRaisesRegex(RuntimeError,'decoder failed'):
    b.run_recorded_call(later,journal,'case.destination',{'image_count':2})
   self.assertEqual(json.loads((journal.directory/'case.target.completed.json').read_text())['payload']['raw_text'],'first raw')
   self.assertEqual(json.loads((journal.directory/'case.destination.generated.json').read_text())['payload']['raw_token_ids'],[8])
   error=json.loads((journal.directory/'case.destination.failed.json').read_text())
   self.assertEqual(error['payload']['exception_type'],'RuntimeError')
   self.assertEqual(error['protocol_sha256'],'a'*64)
   self.assertFalse((journal.directory/'case.destination.completed.json').exists())
 def test_journal_entries_and_directory_are_exclusive(self):
  with tempfile.TemporaryDirectory() as tmp:
   directory=Path(tmp)/'attempts';journal=b.AttemptJournal(directory,'b'*64)
   journal.record('model','started',{'ready':True})
   with self.assertRaises(FileExistsError):journal.record('model','started',{'ready':False})
   with self.assertRaises(FileExistsError):b.AttemptJournal(directory,'b'*64)
   self.assertEqual(json.loads((directory/'model.started.json').read_text())['payload'],{'ready':True})
