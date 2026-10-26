import unittest
import ci_entry as c

class Budget(unittest.TestCase):
    def test_job_work_and_absolute_cutoff_both_bound(self):
        cutoff=c.anchor.utc(c.anchor.CUTOFF_UTC)
        self.assertEqual(c.budget({'capturedMonotonic':100},now=200,wall=cutoff-3000),1720)
        self.assertEqual(c.budget({'capturedMonotonic':100},now=200,wall=cutoff-240),260)
    def test_cleanup_reserve_cannot_be_spent(self):
        with self.assertRaises(ValueError):c.budget({'capturedMonotonic':100},now=200,wall=c.anchor.utc(c.anchor.CUTOFF_UTC)-239)
    def test_round_envelope(self):
        self.assertEqual(c.anchor.JOB_SECONDS,1800)
        self.assertEqual(c.anchor.utc(c.anchor.CUTOFF_UTC)-c.anchor.utc(c.anchor.START_UTC),2700)
        self.assertEqual(c.anchor.utc(c.anchor.CUTOFF_UTC)-c.anchor.JOB_SECONDS-c.anchor.CANCELLATION_SECONDS,c.anchor.utc('2026-10-26T01:19:00Z'))

if __name__=='__main__':unittest.main()
