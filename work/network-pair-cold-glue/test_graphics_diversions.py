"""Production parser checks with text fixtures; no simulated CI or graphics."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock
import graphics_runner as g

class InstalledDiversionParserTests(unittest.TestCase):
    def setUp(self):
        self.source, self.target, _ = g.LIBC_LOADER_DIVERSION
        self.canonical = Path(self.source).resolve(strict=True)
        self.metadata = (f'diversion by libc6 from: {self.source}\n'
                         f'diversion by libc6 to: {self.target}\n')
        self.database = '\n'.join(g.LIBC_LOADER_DIVERSION) + '\n'
        self.records = lambda: g.parse_diversion_database(self.database)

    def parse(self, text, records=None, candidate=None, canonical=None):
        return g.parse_package_search(text, canonical or self.canonical,
                                      candidate or self.source, records or self.records)

    def resolve(self, outputs, package=None, records=None):
        def search(candidate):
            return SimpleNamespace(returncode=0 if candidate in outputs else 1,
                                   stdout=outputs.get(candidate, ''))
        return g.resolve_package_owner(self.canonical, self.source, search,
            package or (lambda name: name.split(':')[0] + ':amd64=2.39-0ubuntu8'),
            records or self.records)

    def test_exact_metadata_pair_corroborated_but_not_an_owner(self):
        names, diversion = self.parse(self.metadata)
        self.assertEqual(names, set())
        self.assertEqual(diversion, g.LIBC_LOADER_DIVERSION)

    def test_real_resolver_accepts_separate_canonical_direct_owner(self):
        self.assertEqual(self.resolve({self.source: self.metadata,
            str(self.canonical): f'libc6:amd64: {self.canonical}\n'}), 'libc6:amd64=2.39-0ubuntu8')

    def test_real_resolver_accepts_direct_alias_owner_with_pair(self):
        self.assertTrue(self.resolve({self.source: self.metadata +
                                     f'libc6:amd64: {self.source}\n'}).startswith('libc6:amd64='))

    def test_no_destination_resolution_required_for_no_rename(self):
        real_resolve, real_exists = Path.resolve, Path.exists
        def resolve(path, *args, **kwargs):
            self.assertNotEqual(str(path), self.target)
            return real_resolve(path, *args, **kwargs)
        def exists(path):
            self.assertNotEqual(str(path), self.target)
            return real_exists(path)
        with mock.patch.object(Path, 'resolve', resolve), mock.patch.object(Path, 'exists', exists):
            self.parse(self.metadata)

    def test_normal_owner_does_not_load_diversion_database(self):
        load = mock.Mock(side_effect=AssertionError('No diversion database required'))
        self.assertEqual(self.parse(f'libc6:amd64: {self.source}\n', records=load)[0], {'libc6:amd64'})
        load.assert_not_called()

    def test_equivalent_canonical_owner_spelling_is_preserved(self):
        self.assertEqual(self.parse(f'libc6:amd64: {self.canonical}\n')[0], {'libc6:amd64'})

    def test_diversion_cannot_replace_direct_ownership(self):
        with self.assertRaisesRegex(ValueError, 'Missing/ambiguous owner'):
            self.resolve({self.source: self.metadata})

    def test_wrong_direct_owner_and_architecture_rejected(self):
        for identity in ('base-files:amd64=1', 'libc6:all=1', 'libc-bin:amd64=1'):
            with self.subTest(identity=identity), self.assertRaisesRegex(ValueError, 'differs'):
                self.resolve({self.source: self.metadata + f'libc6:amd64: {self.source}\n'},
                             package=lambda name: identity)

    def test_conflicting_direct_owners_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Missing/ambiguous owner'):
            self.resolve({self.source: self.metadata + f'libc6:amd64: {self.source}\n',
                          str(self.canonical): f'base-files: {self.canonical}\n'})

    def test_unpaired_duplicate_malformed_local_unrelated_rejected(self):
        bad = [self.metadata.splitlines()[0] + '\n', self.metadata.splitlines()[1] + '\n',
               self.metadata + self.metadata, self.metadata.replace('from:', 'from :'),
               self.metadata.replace('by libc6', 'by LOCAL'),
               self.metadata.replace('by libc6', 'by libc6:amd64'),
               self.metadata.replace('by libc6 to:', 'by base-files to:'),
               self.metadata.replace('by libc6', 'by base-files'),
               self.metadata.replace('diversion by libc6', 'local diversion'),
               self.metadata.replace('.usr-is-merged', '.distrib'),
               self.metadata.replace(' to:', ' from:')]
        for output in bad:
            with self.subTest(output=output), self.assertRaises(ValueError): self.parse(output)

    def test_unverified_diversion_records_rejected(self):
        wrong = (self.source, self.target, 'base-files')
        for records in ([], [wrong], [g.LIBC_LOADER_DIVERSION] * 2,
                        [g.LIBC_LOADER_DIVERSION, (self.target, '/other', 'libc6')]):
            with self.subTest(records=records), self.assertRaises(ValueError):
                self.parse(self.metadata, records=lambda: records)

    def test_database_local_cannot_corroborate_package_diversion(self):
        local = self.database.rsplit('libc6', 1)[0] + ':\n'
        with self.assertRaises(ValueError):
            self.parse(self.metadata, records=lambda: g.parse_diversion_database(local))

    def test_wrong_canonical_or_query_target_rejected(self):
        for kwargs in ({'canonical': Path('/usr/bin/python3')}, {'candidate': str(self.canonical)}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): self.parse(self.metadata, **kwargs)

    def test_ambiguous_or_unrelated_direct_owner_rows_rejected(self):
        for line in (f'libc6:amd64, base-files: {self.source}\n',
                     'libc6:amd64: /usr/bin/python3\n', f'LOCAL: {self.source}\n',
                     f'libc6:i386: {self.source}\n', 'not an owner\n'):
            with self.subTest(line=line), self.assertRaises(ValueError): self.parse(line)

    def test_database_complete_triples_and_unique_paths_required(self):
        for text in (self.database + 'orphan\n', self.database * 2,
                     self.database + f'{self.target}\n/other\nbase-files\n',
                     self.database.replace(self.source, 'relative', 1),
                     self.database.replace('libc6', 'LOCAL'),
                     self.database.replace(self.target, self.source),
                     self.database.replace(self.target, '/tmp/../other')):
            with self.subTest(text=text), self.assertRaises(ValueError): g.parse_diversion_database(text)

    def test_database_bound_and_untrusted_loader_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'bound'): g.parse_diversion_database('x' * (g.MIB + 1))
        load = mock.Mock(side_effect=ValueError('Untrusted installed file ownership/mode'))
        with self.assertRaisesRegex(ValueError, 'Untrusted'): self.parse(self.metadata, records=load)

if __name__ == '__main__': unittest.main()
