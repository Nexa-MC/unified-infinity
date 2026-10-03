package org.sinytra.connector.forge.loader;

import java.lang.annotation.ElementType;
import java.lang.module.ModuleFinder;
import java.lang.reflect.Proxy;
import java.nio.file.Path;
import java.util.*;
import net.neoforged.bus.api.EventPriority;
import net.neoforged.fml.*;
import net.neoforged.fml.event.lifecycle.FMLCommonSetupEvent;
import net.neoforged.neoforgespi.language.*;
import net.neoforged.neoforgespi.locating.IModFile;
import org.objectweb.asm.Type;

public final class ForgeLoaderFacadeTest {
    private static int checks;
    public static void main(String[] args) throws Exception {
        var provider = new ForgeModLanguageLoader();
        check(provider.name().equals("unified_forge_52"), "distinct provider name");
        check(provider.version().equals("1.0.0"), "adapter ABI version");
        Path jar = Path.of(args[0]);
        var finder = ModuleFinder.of(jar);
        var configuration = ModuleLayer.boot().configuration().resolve(finder, ModuleFinder.of(), Set.of("forge.facade.fixtures"));
        ModuleLayer layer = ModuleLayer.boot().defineModulesWithOneLoader(configuration, ForgeLoaderFacadeTest.class.getClassLoader());
        IModFile file = proxy(IModFile.class, Map.of("getFilePath", jar));
        IModFileInfo fileInfo = proxy(IModFileInfo.class, Map.of("moduleName", "forge.facade.fixtures", "getFile", file));
        IModInfo info = proxy(IModInfo.class, Map.of("getModId", "facade_test", "getOwningFile", fileInfo, "getLoader", provider));
        System.clearProperty("unified.forge.facade.test.initialized");
        var container = load(provider, info, layer, "ContextOnly");
        var fixture = type(layer, "ContextOnly");
        // The owning module is resolved without initializing the entrypoint.
        check(System.getProperty("unified.forge.facade.test.initialized") == null, "entrypoint load has no initialization side effects");
        construct(container);
        check("yes".equals(System.getProperty("unified.forge.facade.test.initialized")), "entrypoint initializes at construction");
        check(fixture.getField("constructions").getInt(null) == 1, "context constructor once");
        check(fixture.getField("sameContext").getBoolean(null), "static context matches injected context");
        check(fixture.getField("activeContainer").getBoolean(null), "context bus is active host container bus");
        expect(container, IllegalStateException.class, "duplicate construction rejected");
        check(fixture.getField("constructions").getInt(null) == 1, "duplicate constructor was not invoked");
        var queue = new DeferredWorkQueue("Forge facade test");
        var event = new FMLCommonSetupEvent(container, queue);
        for (var phase : EventPriority.values()) container.acceptEvent(phase, event);
        check(fixture.getField("setup").getInt(null) == 1, "host per-phase bus posts setup once");
        check(fixture.getField("work").getInt(null) == 0, "host work stays deferred");
        queue.runTasks();
        check(fixture.getField("work").getInt(null) == 1, "host queue runs work once");
        check(fixture.getField("workThread").get(null) == Thread.currentThread(), "host queue owns execution thread");
        check(fixture.getField("workSameContext").getBoolean(null), "host deferred queue restores the same per-mod context");
        var both = load(provider, info, layer, "ContextFirst"); construct(both);
        check(type(layer, "ContextFirst").getField("context").getInt(null) == 1, "context constructor takes precedence");
        check(type(layer, "ContextFirst").getField("zero").getInt(null) == 0, "zeroarg fallback not used when context constructor exists");
        var zero = load(provider, info, layer, "ZeroArg"); construct(zero);
        check(type(layer, "ZeroArg").getField("constructions").getInt(null) == 1, "zeroarg constructor fallback");
        check(type(layer, "ZeroArg").getField("sameContext").getBoolean(null), "zeroarg static context");
        expect(load(provider, info, layer, "PrivateContext"), IllegalAccessException.class, "nonpublic context does not cause zeroarg fallback");
        check(type(layer, "PrivateContext").getField("zero").getInt(null) == 0, "private context does not invoke zeroarg");
        var throwing = load(provider, info, layer, "Throwing");
        var cause = expect(throwing, IllegalStateException.class, "constructor exception unwrapped");
        check(cause.getMessage().equals("own-constructor-cause"), "original exception detail retained");
        expect(throwing, IllegalStateException.class, "failed constructor not retried");
        check(type(layer, "Throwing").getField("attempts").getInt(null) == 1, "failed constructor attempted exactly once");
        expect(load(provider, info, layer, "Unsupported"), NoSuchMethodException.class, "unsupported constructor rejected");
        try { provider.loadMod(info, new ModFileScanData(), layer); throw new AssertionError("empty scan accepted"); }
        catch (ModLoadingException expected) { check(expected.getIssues().getFirst().affectedMod() == info, "missing entrypoint attributed"); }
        var duplicate = scan("ContextOnly"); duplicate.getAnnotations().addAll(scan("ZeroArg").getAnnotations());
        try { provider.loadMod(info, duplicate, layer); throw new AssertionError("duplicate scan accepted"); }
        catch (ModLoadingException expected) { check(expected.getIssues().getFirst().cause().getMessage().contains("exactly one"), "duplicate entrypoints rejected"); }
        var wrongAnnotation = new ModFileScanData();
        wrongAnnotation.getAnnotations().add(new ModFileScanData.AnnotationData(Type.getObjectType("net/neoforged/fml/common/Mod"), ElementType.TYPE, Type.getObjectType("org/sinytra/connector/forge/loader/fixture/ForgeEntrypoints$ContextOnly"), "", Map.of("value", "facade_test")));
        try { provider.loadMod(info, wrongAnnotation, layer); throw new AssertionError("native annotation claimed"); }
        catch (ModLoadingException expected) { check(true, "native annotation not claimed"); }
        var danglingScan = scan("ContextOnly");
        danglingScan.getAnnotations().add(new ModFileScanData.AnnotationData(Type.getType(ForgeMod.class), ElementType.TYPE,
            Type.getObjectType("missing/Mod"), "", Map.of("value", "missing_metadata")));
        IModFile validationFile = proxy(IModFile.class, Map.of("getFilePath", jar, "getModInfos", List.of(info), "getScanResult", danglingScan));
        var issues = new ArrayList<ModLoadingIssue>();
        provider.validate(validationFile, List.of(container), issues::add);
        check(issues.size() == 1, "validation reports only dangling entrypoint");
        check(issues.getFirst().affectedModFile() == validationFile, "dangling entrypoint attributed to owning file");
        check(issues.getFirst().translationArgs().getFirst().equals("missing_metadata"), "dangling entrypoint identifies missing mod id");
        System.clearProperty("unified.forge.facade.test.initialized");
        System.out.println("PASS: " + checks + " Forge loader/context/lifecycle checks (no game launch)");
    }
    private static Class<?> type(ModuleLayer layer, String nested) {
        return Class.forName(layer.findModule("forge.facade.fixtures").orElseThrow(), "org.sinytra.connector.forge.loader.fixture.ForgeEntrypoints$" + nested);
    }
    private static ModFileScanData scan(String nested) {
        var scan = new ModFileScanData();
        scan.getAnnotations().add(new ModFileScanData.AnnotationData(Type.getType(ForgeMod.class), ElementType.TYPE, Type.getObjectType("org/sinytra/connector/forge/loader/fixture/ForgeEntrypoints$" + nested), "", Map.of("value", "facade_test")));
        return scan;
    }
    private static ForgeModContainer load(ForgeModLanguageLoader provider, IModInfo info, ModuleLayer layer, String nested) {
        return (ForgeModContainer) provider.loadMod(info, scan(nested), layer);
    }
    private static void construct(ForgeModContainer container) {
        ModLoadingContext.get().setActiveContainer(container);
        try { container.constructMod(); }
        finally { ModLoadingContext.get().setActiveContainer(null); }
    }
    private static Throwable expect(ForgeModContainer container, Class<? extends Throwable> kind, String label) {
        try { construct(container); throw new AssertionError(label); }
        catch (ModLoadingException expected) {
            var issue = expected.getIssues().getFirst();
            check(kind.isInstance(issue.cause()), label);
            check(issue.affectedMod() == container.getModInfo(), label + " attribution");
            return issue.cause();
        }
    }
    private static void check(boolean condition, String label) { if (!condition) throw new AssertionError(label); checks++; }
    @SuppressWarnings("unchecked")
    private static <T> T proxy(Class<T> kind, Map<String, Object> values) {
        return (T) Proxy.newProxyInstance(kind.getClassLoader(), new Class<?>[]{kind}, (p,m,a) -> switch (m.getName()) {
            case "equals" -> p == a[0]; case "hashCode" -> System.identityHashCode(p); case "toString" -> kind.getSimpleName();
            default -> values.get(m.getName());
        });
    }
}
