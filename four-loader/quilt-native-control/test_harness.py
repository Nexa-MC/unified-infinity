import unittest
from run_native import parse
SHA='a364850812d3d519087263d71a83a0a8c8db3387673d847ce665111ca5b33d24'
def valid(phase='create'):
 return ('NATIVE_QUILT_PROBE CLASS_DEFINED\n'+ '\n'.join('NATIVE_QUILT_PROBE PASS stage='+stage for stage in [f'pre_launch count=1 native_id=unified-quilt-probe group=dev.infinity.probes version=0.1.0+native sha256={SHA}','init count=1','method_reference count=1','server_init count=1','automatic_ready count=1',f'ready phase={phase} marker=native_quilt_qsl_alpha5_v1 read_before_write={str(phase=="reopen").lower()}',f'ready_to_save ticks=5 mixin_ticks=5 auto_ready=1 phase={phase}','stopped ticks=6'])+'\nStarting Minecraft server on 127.0.0.1:25621\nDone (1.1s)! For help, type help\nSaved the game\nAll dimensions are saved\n').encode()
class HarnessValidation(unittest.TestCase):
 def test_pass_fields(self):
  for phase in ('create','reopen'):
   report=parse(valid(phase),phase,SHA)
   self.assertEqual(set(report['stage_counts'].values()),{1})
   for key in ('entrypoint_order_valid','original_jar_identity_verified','saved_data_phase_verified','qsl_and_mixin_tick_verified','server_ready','save_acknowledged','all_dimensions_saved','no_probe_failure','loopback_binding_verified'):self.assertTrue(report[key],key)
 def test_detects_duplicate(self):
  self.assertEqual(parse(valid()+b'NATIVE_QUILT_PROBE PASS stage=init count=1\n','create',SHA)['stage_counts']['init'],2)
 def test_detects_wrong_identity(self):self.assertFalse(parse(valid(),'create','bad')['original_jar_identity_verified'])
 def test_detects_no_mixins(self):self.assertFalse(parse(valid().replace(b'mixin_ticks=5',b'mixin_ticks=0'),'create',SHA)['qsl_and_mixin_tick_verified'])
 def test_reopen_requires_read_before_write(self):self.assertFalse(parse(valid(),'reopen',SHA)['saved_data_phase_verified'])
 def test_order(self):
  data=valid().replace(b'stage=init ',b'stage=placeholder ').replace(b'stage=method_reference ',b'stage=init ').replace(b'stage=placeholder ',b'stage=method_reference ')
  self.assertFalse(parse(data,'create',SHA)['entrypoint_order_valid'])
if __name__=='__main__':unittest.main()
