import unittest
from unittest.mock import Mock

from run_parity import LIFECYCLE, REGISTER, Server


class PositiveAssertionTests(unittest.TestCase):
    def server(self, output):
        server = Server.__new__(Server)
        server.output = output
        server.deadline = float("inf")
        server.proc = Mock()
        server.proc.poll.return_value = 0
        server.proc.returncode = 0
        server.pump = Mock()
        server.command = Mock(return_value=0)
        return server

    def test_all_required_readiness_markers_pass(self):
        self.server(f'{REGISTER}\n{LIFECYCLE}\nDone (1.0s)! For help\n').ready()

    def test_missing_registration_marker_fails_even_after_clean_exit(self):
        with self.assertRaises(RuntimeError):
            self.server(f'{LIFECYCLE}\nDone (1.0s)! For help\n').ready()

    def test_missing_lifecycle_marker_fails_even_after_clean_exit(self):
        with self.assertRaises(RuntimeError):
            self.server(f'{REGISTER}\nDone (1.0s)! For help\n').ready()

    def test_missing_ready_marker_fails_even_after_clean_exit(self):
        with self.assertRaises(RuntimeError):
            self.server(f'{REGISTER}\n{LIFECYCLE}\n').ready()

    def test_exact_console_stack_passes(self):
        self.server('0, 64, 0 has the following block data: [{count: 7, Slot: 0b, id: "infinity_registry_probe:test_item"}]').stack()

    def test_missing_console_stack_fails(self):
        with self.assertRaises(RuntimeError):
            self.server('Done (1.0s)! For help').stack()

    def test_wrong_console_stack_id_fails(self):
        with self.assertRaises(AssertionError):
            self.server('0, 64, 0 has the following block data: [{count: 7, Slot: 0b, id: "minecraft:air"}]').stack()

    def test_wrong_console_stack_count_fails(self):
        with self.assertRaises(AssertionError):
            self.server('0, 64, 0 has the following block data: [{count: 1, Slot: 0b, id: "infinity_registry_probe:test_item"}]').stack()


if __name__ == "__main__":
    unittest.main()
