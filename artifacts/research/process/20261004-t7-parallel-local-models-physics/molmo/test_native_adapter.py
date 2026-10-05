"""Parser boundary tests: wrong image/units/absence/evidence must fail closed."""
import math, unittest
import native_adapter as a

class NativeBoundaryTests(unittest.TestCase):
 def test_task_metrics_sum_all_calls_and_take_peak_vram(self):
  calls=[{'input_token_count':900,'output_token_count':10,'latency_s':2.5,'inference_s':2.0,'max_memory_allocated_bytes':100,'max_memory_reserved_bytes':150},
         {'input_token_count':910,'output_token_count':12,'latency_s':3.0,'inference_s':2.6,'max_memory_allocated_bytes':120,'max_memory_reserved_bytes':160},
         {'input_token_count':920,'output_token_count':40,'latency_s':4.0,'inference_s':3.4,'max_memory_allocated_bytes':110,'max_memory_reserved_bytes':155}]
  got=a.task_metrics(calls,10.0)
  self.assertEqual(got,{'task_latency_s':10.0,'model_inference_total_s':8.0,'call_latency_total_s':9.5,'model_call_count':3,'input_tokens_total':2730,'output_tokens_total':62,'peak_torch_allocated_bytes':120,'peak_torch_reserved_bytes':160})
 def test_mixed_absence_and_points_are_not_accepted(self):
  points=a.parse_molmo2('<points coords="1 1 500 500"/>',2)
  self.assertEqual(a.localization_result('ABSENT <points coords="1 1 500 500"/>',points,[1])['status'],'invalid')
 def test_model_skill_sequence_must_not_be_fabricated(self):
  target={'status':'localized','point':[250,750]};dest={'status':'localized','point':[500,250]}
  evidence={'target_label':'cube','target_present':True,'destination_present':True,'reported_confidence':0.7,'observed_scene':'cube'}
  with self.assertRaises(a.NativeProtocolError):a.build_visual_decision(target,dest,evidence)
 def test_molmo2_preserves_normalized_points_and_one_based_image_ids(self):
  got=a.parse_molmo2('<points label="red cube" coords="1 1 125 750;2 1 900 250"/>',2)
  self.assertEqual([(p.image_index,p.object_id,p.normalized_1000) for p in got],[(0,1,(125,750)),(1,1,(900,250))])
 def test_molmo2_rejects_out_of_range_without_coordinate_repair(self):
  with self.assertRaises(a.NativeProtocolError):a.parse_molmo2('<points coords="1 1 1001 500"/>',2)
 def test_molmo2_rejects_invalid_image_and_unstructured_numbers(self):
  for raw in ('<points coords="0 1 500 500"/>','The point is 500, 500','<points coords="3 1 500 500"/>'):
   with self.subTest(raw=raw),self.assertRaises(a.NativeProtocolError):a.parse_molmo2(raw,2)
 def test_molmopoint_pixels_are_converted_once_and_order_is_object_image(self):
  got=a.convert_molmopoint([[9,0,80,180],[4,1,160,60]],[(320,240),(320,240)])
  self.assertEqual([(p.image_index,p.object_id,p.normalized_1000) for p in got],[(0,9,(250,750)),(1,4,(500,250))])
 def test_molmopoint_rejects_nonfinite_oob_and_unknown_image(self):
  for row in ([1,0,math.nan,50],[1,0,321,50],[1,2,50,50],[1,0,-1,50]):
   with self.subTest(row=row),self.assertRaises(a.NativeProtocolError):a.convert_molmopoint([row],[(320,240),(320,240)])
 def test_no_points_is_only_absence_with_explicit_model_refusal(self):
  self.assertEqual(a.localization_result('ABSENT',[],[1])['status'],'absent')
  for raw in ('', 'I am not sure', 'red cube'):
   self.assertEqual(a.localization_result(raw,[],[1])['status'],'unavailable')
 def test_depth_only_points_cannot_become_rgb_grounding(self):
  points=a.convert_molmopoint([[1,1,80,60]],[(320,240),(320,240)])
  self.assertEqual(a.localization_result('point',points,[7])['status'],'unavailable')
 def test_multiple_rgb_points_and_absence_contradiction_fail_closed(self):
  points=a.parse_molmo2('<points coords="1 1 250 250 2 750 750"/>',2)
  self.assertEqual(a.localization_result('point',points,[1])['status'],'ambiguous')
  self.assertEqual(a.localization_result('ABSENT',points[:1],[1])['status'],'invalid')
 def test_missing_model_confidence_blocks_complete_decision(self):
  target={'status':'localized','point':[250,750]};dest={'status':'localized','point':[500,250]}
  with self.assertRaises(a.NativeProtocolError):a.build_visual_decision(target,dest,{'target_label':'red cube','target_present':True,'destination_present':True,'observed_scene':'A red cube and green square'})
 def test_model_evidence_retains_label_confidence_and_reason(self):
  target={'status':'localized','point':[250,750]};dest={'status':'localized','point':[500,250]}
  evidence={'skills':['HOME','MOVE_ABOVE','APPROACH','GRASP','LIFT','MOVE_TO_REGION','PLACE','RELEASE','RETREAT','HOME'],'target_label':'small red cube','target_present':True,'destination_present':True,'reported_confidence':0.73,'observed_scene':'A red cube lies before a green square.'}
  got=a.build_visual_decision(target,dest,evidence)
  self.assertEqual((got['target_pixel'],got['destination_pixel'],got['reported_confidence'],got['target_label']),([250,750],[500,250],0.73,'small red cube'))
  self.assertEqual(got['reason'],'A red cube lies before a green square.')
 def test_negative_evidence_never_yields_a_pick_plan(self):
  target={'status':'absent','point':None};dest={'status':'localized','point':[500,250]}
  evidence={'skills':[],'target_label':'purple cube','target_present':False,'destination_present':True,'reported_confidence':0.12,'observed_scene':'No purple cube is visible.'}
  got=a.build_visual_decision(target,dest,evidence)
  self.assertEqual((got['target_pixel'],got['destination_pixel'],got['skills']),(None,None,[]))
 def test_conflicting_presence_and_nonmodel_confidence_rejected(self):
  target={'status':'absent','point':None};dest={'status':'localized','point':[500,250]}
  evidence={'skills':[],'target_label':'cube','target_present':True,'destination_present':True,'reported_confidence':0.9,'observed_scene':'cube'}
  with self.assertRaises(a.NativeProtocolError):a.build_visual_decision(target,dest,evidence)
  for conf in (True,float('nan'),1.1):
   bad={**evidence,'target_present':False,'reported_confidence':conf}
   with self.assertRaises(a.NativeProtocolError):a.build_visual_decision(target,dest,bad)

if __name__=='__main__':unittest.main()
