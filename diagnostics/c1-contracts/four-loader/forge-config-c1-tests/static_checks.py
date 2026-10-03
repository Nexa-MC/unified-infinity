#!/usr/bin/env python3
"""No JVM: immutable input, ownership and isolation checks for the unmerged C1 proposal."""
import hashlib,json,pathlib,re,unittest,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[2]
WORK=ROOT/'source-workspace/forge-config-c1'
SRC=WORK/'src/main/java'
class StaticChecks(unittest.TestCase):
 def test_frozen_base(self):
  manifest=json.loads((WORK/'base-manifest.json').read_text())
  archive=ROOT/manifest['archive']
  self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),manifest['archive_sha256'])
  with zipfile.ZipFile(archive) as z:
   self.assertEqual(len(z.namelist()),736)
   for item in manifest['selected']:
    self.assertEqual((WORK/'base'/item['path']).read_bytes(),z.read(item['archive_member']))
    self.assertEqual(hashlib.sha256((ROOT/item['archive_member']).read_bytes()).hexdigest(),item['sha256'])
 def test_no_parallel_owner(self):
  facade='\n'.join(p.read_text() for p in (SRC/'org/sinytra/connector/forge/config').glob('*.java'))
  for forbidden in ['FileWatcher','new ConfigTracker(', 'Files.write','TomlParser','TomlWriter','ThreadLocal','@Mod(']:self.assertNotIn(forbidden,facade)
  self.assertIn('implements IConfigSpec, ConfigRegistrationPolicy',facade)
  self.assertNotIn('implements ILoadedConfig',facade)
 def test_native_changes_are_narrow(self):
  changed=[]
  for p in (WORK/'base').rglob('*.java'):
   rel=p.relative_to(WORK/'base')
   if p.read_bytes()!=(SRC/rel).read_bytes():changed.append(rel.as_posix())
  self.assertEqual(sorted(changed),sorted(['net/neoforged/fml/config/ConfigTracker.java','net/neoforged/fml/config/LoadedConfig.java','net/neoforged/fml/config/ModConfig.java','org/sinytra/connector/forge/loader/ForgeModLoadingContext.java','org/sinytra/connector/forge/transform/Forge52Symbols.java']))
 def test_actual_return_conflict_preserved(self):
  facade=(SRC/'org/sinytra/connector/forge/config/ForgeConfigSpec.java').read_text()
  native=(SRC/'net/neoforged/fml/config/IConfigSpec.java').read_text()
  self.assertIn('public int correct(CommentedConfig config)',facade)
  self.assertIn('void correct(CommentedConfig config)',native)
 def test_exact_transformer_delta(self):
  rel='org/sinytra/connector/forge/transform/Forge52Symbols.java'
  original=(WORK/'base'/rel).read_text();candidate=(SRC/rel).read_text()
  proposal=json.loads((ROOT/'four-loader/forge-config-c1-tests/boundary/proposed-allowlist.json').read_text())
  for section,key in [('METHODS','methods'),('FIELDS','fields')]:
   def members(s):
    body=re.search(r'Set<String> '+section+r' = Set\.of\((.*?)\n    \);',s,re.S).group(1)
    return set(re.findall(r'"([^"\n]+)"',body))
   self.assertEqual(members(candidate),members(original)|{x['transformer_key'] for x in proposal[key]})
  for entry in proposal['types']:
   self.assertIn('Map.entry("'+entry['owner']+'", "'+entry['target']+'")',candidate)
  self.assertIn('forge52-mojmap-slice-4-common-config-c1-unmerged',candidate)
 def test_provenance(self):
  p=json.loads((ROOT/'docs/api-coverage/forge-config/provenance.json').read_text())
  rows=p['files']
  self.assertTrue(rows,'Expected pinned source provenance')
  for row in rows:self.assertEqual(hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest(),row['sha256'])
if __name__=='__main__':unittest.main(verbosity=2)
