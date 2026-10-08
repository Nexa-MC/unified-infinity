"""Small source-only checks for merging already verified producer identities."""
import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import finalize_pair as f

class FinalizerChecks(unittest.TestCase):
    def test_pin_conflict_rejected(self):
        a={'path':'/same','bytes':1,'sha256':'a'*64};b=dict(a,sha256='b'*64)
        with self.assertRaisesRegex(ValueError,'Conflicting'):
            f.merge_pins([a],[b])

    def test_identical_pin_deduplication(self):
        a={'path':'/same','bytes':1,'sha256':'a'*64}
        self.assertEqual(f.merge_pins([a],[dict(a)]),[a])

    def test_owned_root_stays_narrow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);child=root/'child';child.mkdir()
            self.assertEqual(f.add_owned_root([str(root)],child),[str(root)])
            with self.assertRaisesRegex(ValueError,'broaden'):
                f.add_owned_root([str(child)],root)

    def test_changed_owner_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(f.os,'geteuid',return_value=999999):
                with self.assertRaisesRegex(ValueError,'owned'):
                    f.add_owned_root([],Path(tmp))

    def test_root_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'real';target.mkdir();alias=root/'alias';alias.symlink_to(target)
            with self.assertRaisesRegex(ValueError,'canonical'):
                f.add_owned_root([],alias)

    def test_unmeasured_graphics_rejected(self):
        base={'schema':'prepared-network-ci-pair-v2','status':'NEEDS_ACTUAL_GRAPHICS_NOT_EXECUTABLE'}
        with self.assertRaisesRegex(ValueError,'Actual graphics-ready'):
            f.bind(base,{'schema':1,'status':'SOURCE_ONLY','pair_acceptance':False},{},'review')

    def test_unapproved_reference_rejected(self):
        base={'schema':'prepared-network-ci-pair-v2','status':'NEEDS_ACTUAL_GRAPHICS_NOT_EXECUTABLE'}
        ready={'schema':1,'status':'GRAPHICS_PREFLIGHT_READY','pair_acceptance':False}
        with self.assertRaisesRegex(ValueError,'authorization'):
            f.bind(base,ready,{},'')

if __name__=='__main__':unittest.main()
