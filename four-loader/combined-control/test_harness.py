"""Offline control tests only. Does not start Java, Minecraft, or any game process."""
import copy
import json
import pathlib
import tempfile
import unittest
import zipfile
from unittest.mock import patch
import common
import run

class CombinedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = common.ROOT
        cls.qcreate = (root / 'four-loader/quilt-unified-control/logs/unified-quilt-probe-ordered/unified-create-1.log').read_bytes()
        cls.qreopen = (root / 'four-loader/quilt-unified-control/logs/unified-quilt-probe-ordered/unified-reopen-1.log').read_bytes()
        cls.ccreate = (root / 'logs/unified-forge-clumps-26b/create.log').read_bytes()
        cls.creopen = (root / 'logs/unified-forge-clumps-26b/reopen.log').read_bytes()

    def test_exact_approved_input_hashes(self):
        self.assertEqual(len(common.INPUTS), 9)
        for path, expected in common.INPUTS.items():
            self.assertEqual(common.sha(common.ROOT / path), expected, path)

    def test_only_combined_isolated_names(self):
        self.assertTrue(common.valid_profile('unified-combined-98d-first'))
        for name in ('../unified-combined-x', 'unified-forge-clumps-26b', 'unified-combined-x/y', 'unified-combined-'):
            self.assertFalse(common.valid_profile(name))

    def test_dual_ready_barrier(self):
        good = ['Done (1.0s)! For help, type help', 'NATIVE_QUILT_PROBE PASS stage=ready_to_save ticks=5', 'UNIFIED_CLUMPS_PROBE PASS stage=ready_to_save xp=72']
        self.assertTrue(common.both_ready(good))
        for index in range(3):
            self.assertFalse(common.both_ready(good[:index] + good[index + 1:]))

    def test_real_individual_logs_satisfy_combined_probe_parser(self):
        # A parser regression test only; concatenation is NOT combined runtime evidence.
        for phase, raw in [('create', self.qcreate + self.ccreate), ('reopen', self.qreopen + self.creopen)]:
            self.assertTrue(common.probe_evidence(raw, phase)['passed'])

    def test_duplicate_quilt_stage_fails(self):
        raw = self.qcreate + self.ccreate + b'\nNATIVE_QUILT_PROBE PASS stage=init count=1\n'
        self.assertFalse(common.probe_evidence(raw, 'create')['passed'])

    def test_duplicate_clumps_stage_fails(self):
        raw = self.qcreate + self.ccreate + b'\nUNIFIED_CLUMPS_PROBE PASS stage=merge xp=72\n'
        self.assertFalse(common.probe_evidence(raw, 'create')['passed'])

    def test_probe_failure_is_not_hidden_by_pass_markers(self):
        for prefix in ('NATIVE_QUILT_PROBE FAIL', 'UNIFIED_CLUMPS_PROBE FAIL'):
            self.assertFalse(common.probe_evidence(self.qcreate + self.ccreate + ('\n' + prefix + '\n').encode(), 'create')['passed'])

    def test_old_wrong_quilt_order_still_fails(self):
        old = (common.ROOT / 'four-loader/quilt-unified-control/logs/unified-create-1.log').read_bytes()
        self.assertFalse(common.probe_evidence(old + self.ccreate, 'create')['passed'])

    def test_phase_mismatch_fails(self):
        self.assertFalse(common.probe_evidence(self.qcreate + self.ccreate, 'reopen')['passed'])

    def test_host_shape_exactly_one_bus_and_two_forge_inputs(self):
        evidence = run.check_runtime_shape(self.ccreate, 'create')
        self.assertTrue(evidence['forge_two_originals_exactly_once'])
        self.assertTrue(evidence['one_host_mixin_service'])
        self.assertTrue(evidence['native_host_launch'])
        self.assertFalse(run.check_runtime_shape(self.ccreate * 2, 'create')['one_host_mixin_service'])
        self.assertEqual(run.check_runtime_shape(self.creopen, 'reopen')['forge_cache_hits'], 2)

    def server(self):
        return run.CombinedServer(common.ROOT / 'run/unified-combined-test', {'mods': {}}, 'reopen', 600, pathlib.Path('/tmp/unused-combined.log'))

    def test_java_stored_world_type_colon_escape(self):
        stored = common.mixed.properties(common.ROOT / 'run/unified-combined-98d-retry1/server.properties')
        self.assertEqual(stored['level-type'], r'minecraft\:normal')
        self.assertTrue(run.property_matches('level-type', stored['level-type'], 'minecraft:normal'))
        for actual in ('minecraft:flat', r'minecraft\:flat', r'minecraft\\:normal', 'normal'):
            self.assertFalse(run.property_matches('level-type', actual, 'minecraft:normal'))
        self.assertFalse(run.property_matches('server-ip', '0.0.0.0', '127.0.0.1'))
        self.assertFalse(run.property_matches('online-mode', 'false', 'true'))

    def test_cannot_control_before_both_probes(self):
        with self.assertRaises(AssertionError):
            self.server().command('tick freeze')

    def test_force_add_becomes_read_only_and_missing_fails(self):
        server = self.server()
        server.probe_barrier_passed = True
        with patch.object(common.mixed.Server, 'command', return_value=['Chunk at [0, 0] in Overworld is marked for force loading']) as command:
            server.command('forceload add 0 0')
            command.assert_called_once_with('forceload query 0 0')
        self.assertEqual(server.forced_queries, 1)
        with patch.object(common.mixed.Server, 'command', return_value=['Chunk at [0, 0] is not marked for force loading']):
            with self.assertRaises(AssertionError):
                server.command('forceload add 0 0')

    def test_force_query_matches_official_vanilla_language(self):
        path = common.ROOT / 'run/neoforge-native/libraries/net/minecraft/server/1.21.1-20240808.144430/server-1.21.1-20240808.144430-extra.jar'
        with zipfile.ZipFile(path) as archive:
            lang = json.loads(archive.read('assets/minecraft/lang/en_us.json'))
        reply = lang['commands.forceload.query.success'] % ('[0, 0]', 'Overworld')
        server = self.server()
        server.probe_barrier_passed = True
        with patch.object(common.mixed.Server, 'command', return_value=[reply]):
            server.command('forceload add 0 0')
        self.assertEqual(server.forced_queries, 1)

    def test_freeze_needs_acknowledgement(self):
        server = self.server()
        server.probe_barrier_passed = True
        with patch.object(common.mixed.Server, 'command', return_value=['The game is frozen']):
            server.command('tick freeze')
        self.assertTrue(server.freeze_acknowledged)
        with patch.object(common.mixed.Server, 'command', return_value=['Unknown command']):
            with self.assertRaises(AssertionError):
                server.command('tick freeze')

    def test_saved_native_chunk_baseline_reused(self):
        targets = common.canonical_targets(common.ROOT / 'run/mixed-pack-source-acceptance-v1-neoforge')
        self.assertEqual(len(targets), 9)
        self.assertTrue(all(row['native_equal'] for row in targets))

    def test_existing_saved_clumps_and_quilt_evidence(self):
        clumps = common.clumps_world.verify(common.ROOT / 'run/unified-forge-clumps-26b', common.CLUMPS_MARKER)
        self.assertEqual(clumps['orb']['weighted_xp'], 72)
        self.assertEqual(clumps['orb']['original_orb_multiplicity'], 6)
        self.assertTrue(common.quilt_world.verify(common.ROOT / 'run/unified-quilt-probe-ordered')['passed'])

if __name__ == '__main__':
    unittest.main()
