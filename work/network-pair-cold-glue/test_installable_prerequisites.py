import unittest
from unittest import mock
import runner_dependencies as r
class InstallablePrerequisites(unittest.TestCase):
    def setUp(self):
        self.paths=[r.CANONICAL,r.PACKAGE_PATHS['libegl1'],r.PACKAGE_PATHS['libegl-mesa0']]
        self.rows=[{'path':p,'reason':'missing'} for p in self.paths]
        self.candidates=r.load_candidates()
    def test_only_exact_missing_pinned_paths_deferred(self):
        with mock.patch.object(r.os.path,'lexists',return_value=False):
            self.assertEqual(r.prerequisite_blockers(self.rows,self.candidates),[])
    def test_postinstall_missing_path_remains_blocker(self):
        with mock.patch.object(r.os.path,'lexists',return_value=False):
            self.assertEqual(r.prerequisite_blockers(self.rows,[]),self.rows)
    def test_existing_untrusted_or_dangling_path_remains_blocker(self):
        with mock.patch.object(r.os.path,'lexists',return_value=True):
            self.assertEqual(r.prerequisite_blockers(self.rows,self.candidates),self.rows)
    def test_unknown_and_unpinned_missing_paths_remain_blockers(self):
        rows=[{'path':'/usr/lib/unknown.so'},{'path':r.PACKAGE_PATHS['libgles2']},{'input':'runner'}]
        with mock.patch.object(r.os.path,'lexists',return_value=False):
            self.assertEqual(r.prerequisite_blockers(rows,self.candidates),rows)
    def test_same_name_without_missing_candidate_is_not_deferred(self):
        with mock.patch.object(r.os.path,'lexists',return_value=False):
            self.assertEqual(r.prerequisite_blockers(self.rows,[{'Package':'libegl1'}]),[self.rows[0],self.rows[2]])
