"""Source/static checks only; do not count these as compilation or real-game acceptance."""
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
UI = ROOT / "src/client-branding/java/dev/modcompat/runtime/modlist"

class BuiltInListSourceTests(unittest.TestCase):
    def test_exact_supported_client_hook(self):
        source = (UI / "UnifiedModListEvents.java").read_text()
        self.assertNotIn('EventBusSubscriber', source)
        self.assertNotIn('SubscribeEvent', source)
        self.assertIn('public static synchronized void initialize()', source)
        self.assertIn('NeoForge.EVENT_BUS.addListener(UnifiedModListEvents::opening)', source)
        self.assertIn('if (initialized) throw new IllegalStateException', source)
        self.assertIn('event.getNewScreen().getClass() != ModListScreen.class', source)
        self.assertIn('event.setNewScreen(new UnifiedModListScreen(event.getCurrentScreen()', source)
        self.assertIn('AdmissionSession.current().selectedSnapshot()', source)
        self.assertNotIn('freeze(', source)

    def test_no_archive_scan_or_fake_provider(self):
        source = "\n".join(p.read_text() for p in UI.glob("*.java"))
        for forbidden in ['new ModContainer(', 'implements IModInfo', 'new ZipFile(', 'Files.walk(', 'JarFile(', 'modmenu', 'AdmittedModCatalog']:
            self.assertNotIn(forbidden, source)
        self.assertNotRegex(source, r'getModId\(\)\.(startsWith|contains)')

    def test_translations_complete(self):
        locale = ROOT / 'src/client-branding/resources/assets/mod_compat_runtime/lang'
        en = json.loads((locale / 'en_us.json').read_text())
        zh = json.loads((locale / 'zh_cn.json').read_text())
        self.assertEqual(en.keys(), zh.keys())
        for key in en:
            self.assertEqual(en[key].count('%s'), zh[key].count('%s'), key)
        source = "\n".join(p.read_text() for p in UI.glob('*.java'))
        for key in re.findall(r'(?:tr|field)\("([a-z_]+)"', source):
            self.assertIn('unified_infinity.mods.' + key, en, key)

    def test_model_dependency_compile_only(self):
        source = (ROOT / 'client-branding.gradle').read_text()
        self.assertIn('files(unifiedFml) + files(clientLibraries) + files(admissionModel)', source)
        self.assertNotIn('from(unifiedFml)', source)
        self.assertNotIn('from(admissionModel)', source)
        self.assertNotIn('runtimeOnly', source)
        self.assertIn("dependsOn 'testInventoryUi'", source)

    def test_explicit_product_lifecycle(self):
        source = (ROOT / 'src/main/java/dev/modcompat/runtime/bundle/RuntimeBundle.java').read_text()
        self.assertNotIn('@Mod', source)
        self.assertNotIn('fml.common.Mod', source)
        self.assertIn('implements GameCompatibilityComponent', source)
        self.assertIn('public RuntimeBundle() { }', source)
        self.assertIn('initialize(IEventBus internalBus, Dist side)', source)
        self.assertIn('phase == LifecyclePhase.CLIENT_SETUP', source)
        self.assertIn('if (dist != Dist.CLIENT) throw', source)
        self.assertIn('UnifiedModListEvents.initialize()', source)
        self.assertNotIn('require(mods, "connector")', source)
        self.assertNotIn('Class.forName', source)
        self.assertNotIn('ServiceLoader', source)

    def test_metadata_only_host_capability(self):
        source = (ROOT / 'src/main/resources/META-INF/neoforge.mods.toml').read_text()
        self.assertIn('modLoader="unified_internal"', source)
        self.assertIn('loaderVersion="[1]"', source)
        self.assertIn('modId="mod_compat_runtime"', source)
        self.assertIn('config="unified-infinity.client-branding.mixins.json"', source)
        self.assertIn('Original upstream implementation, authorship and licenses remain credited.', source)
        self.assertNotIn('modId="unified_infinity_api"', source)

    def test_menu_counts_use_final_snapshot_only(self):
        source = (ROOT / 'src/client-branding/java/dev/modcompat/runtime/branding/mixin/TitleScreenBrandingMixin.java').read_text()
        self.assertIn('AdmissionSession.current().selectedSnapshot().map(Snapshot::counts)', source)
        self.assertIn('unified_infinity.branding.menu_user_count', source)
        self.assertIn('font.width(COPYRIGHT_TEXT)', source)
        self.assertIn('budget, font::width', source)
        self.assertIn('button.getX() - 8', source)
        self.assertNotIn('ModList.get()', source)
        self.assertNotIn('Files.', source)
        text = (ROOT / 'src/client-branding/java/dev/modcompat/runtime/branding/BrandingText.java').read_text()
        self.assertNotIn('original.substring', text)
        self.assertIn('counts.userMods()', text)
        self.assertIn('counts.bundledApi()', text)
        self.assertIn('counts.platform()', text)
        self.assertIn('counts.unknown()', text)
        self.assertIn('COMPACT_NAME', text)
        self.assertIn('measure.applyAsInt(candidate)', text)
        details = (UI / 'InventoryDetails.java').read_text()
        self.assertIn('model.snapshot().entries().stream().filter(entry -> entry.category() == Category.PLATFORM)', details)
        self.assertIn('identity(lines, entry)', details)

    def test_real_menu_count_localizations(self):
        locale = ROOT / 'src/client-branding/resources/assets/mod_compat_runtime/lang'
        en = json.loads((locale / 'en_us.json').read_text())
        zh = json.loads((locale / 'zh_cn.json').read_text())
        key = 'unified_infinity.branding.menu_user_count'
        self.assertEqual(en[key] % 5, '5 user mods')
        self.assertEqual(zh[key] % 5, '5 个用户模组')
        self.assertNotIn('unified_infinity.branding.menu_counts', en)

    def test_visible_exclusions_use_only_frozen_notices(self):
        events = (UI / 'UnifiedModListEvents.java').read_text()
        self.assertIn('SystemToast.multiline', events)
        self.assertIn('ClientTickEvent.Post', events)
        self.assertIn('minecraft.screen instanceof TitleScreen', events)
        self.assertIn('exclusionNotice.shouldNotify(true, snapshot)', events)
        self.assertIn('snapshot.orElseThrow().exclusions().size()', events)
        screen = (UI / 'UnifiedModListScreen.java').read_text()
        self.assertIn('new InventoryNoticesScreen(this, model.snapshot())', screen)
        self.assertIn('tr("exclusions_button", model.snapshot().exclusions().size())', screen)
        details = (UI / 'InventoryDetails.java').read_text()
        for field in ['snapshot.exclusions()', 'exclusion.originalId()', 'exclusion.reason()', 'exclusion.ruleId()', 'exclusion.source()', 'exclusion.selectedReplacementIds()']:
            self.assertIn(field, details)
        self.assertIn('exclusions_replacement_caution', details)
        self.assertIn('exclusions_unchanged', details)
        self.assertNotIn('Files.', events + details)
        self.assertNotIn('new ModContainer', events + details)

    def test_native_config_and_literal_rendering(self):
        source = (UI / 'UnifiedModListScreen.java').read_text()
        self.assertIn('IConfigScreenFactory.getForMod(container.getModInfo())', source)
        self.assertIn('factory.createScreen(container, this)', source)
        self.assertIn('list.setScrollAmount(0)', source)
        details = (UI / 'InventoryDetails.java').read_text()
        self.assertIn('Component.literal(InventoryUiModel.plain', details)
        self.assertNotIn('newChatWithLinks', details)
        self.assertNotIn('Component.Serializer', details)

if __name__ == '__main__': unittest.main()
