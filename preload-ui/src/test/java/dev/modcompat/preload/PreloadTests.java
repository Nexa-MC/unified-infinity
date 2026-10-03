package dev.modcompat.preload;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.ServiceLoader;
import net.neoforged.neoforgespi.earlywindow.ImmediateWindowProvider;

public final class PreloadTests {
    private static int passed;
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
        passed++; System.out.println("PASS " + message);
    }
    private static String event(long seq, String completed, String total) {
        return "{\"stage\":\"transform\",\"status\":\"running\",\"completed\":"+completed+",\"total\":"+total+",\"elapsedMs\":123,\"sequence\":"+seq+"}";
    }
    public static void main(String[] args) throws Exception {
        check(!ProgressSnapshot.WAITING.determinate(), "unknown work remains indeterminate");
        var known = ProgressFileReader.parse(event(1, "4", "8"));
        check(known.determinate() && known.fraction() == .5, "actual count yields stage-only fraction");
        check(known.detail().contains("current stage only"), "denominator scope explicit");
        check(!ProgressFileReader.parse(event(2, "0", "0")).determinate(), "zero total is not artificial complete");
        check(!ProgressFileReader.parse(event(2, "3", "null")).determinate(), "count without total is indeterminate");
        var commit = new ProgressSnapshot("commit", "complete", 8L, 8L, 400, 4, null);
        check(commit.detail().contains("waiting for Minecraft"), "commit completion is not Minecraft completion");
        for (String bad : new String[] {event(1,"9","8"), event(1,"-1","8"), event(1,"1.5","8"), event(1,"999999999999999999999999","8")}) {
            try { ProgressFileReader.parse(bad); throw new AssertionError("Accepted invalid count"); }
            catch (IllegalArgumentException | ArithmeticException expected) { check(true, "reject invalid count"); }
        }
        Path temp = Files.createTempDirectory(Path.of("build"), "telemetry-test-"); Path file = temp.resolve("progress.json");
        var reader = new ProgressFileReader(file, 0);
        check(reader.poll(0).equals(ProgressSnapshot.WAITING), "missing telemetry is nonfatal");
        Files.writeString(file, event(1,"2","8"));
        check(reader.poll(1).equals(ProgressSnapshot.WAITING) && reader.reads()==1, "read throttled within 100 ms");
        check(reader.poll(100_000_000).completed()==2, "next real observation accepted");
        Files.writeString(file, event(0,"1","8"));
        check(reader.poll(200_000_000).completed()==2, "older sequence ignored");
        Files.writeString(file, "{partially written");
        check(reader.poll(300_000_000).completed()==2, "malformed observation preserves valid state");
        Files.writeString(file, "x".repeat(ProgressFileReader.MAX_BYTES+1));
        check(reader.poll(400_000_000).completed()==2, "oversized observation bounded and ignored");
        Files.writeString(file, event(9,"5","8")); Files.setLastModifiedTime(file, FileTime.fromMillis(100));
        check(new ProgressFileReader(file,200).poll(0).equals(ProgressSnapshot.WAITING), "old launch file ignored");
        var normal = new FramePacer(false); var reduced = new FramePacer(true);
        check(normal.intervalNanos() >= 33_333_333 && reduced.intervalNanos()==100_000_000, "render limits 30/10 Hz");
        check(normal.due(0) && !normal.due(1), "no catch-up render burst");
        var image = TextLayer.render(known,true);
        check(image.getWidth()==960 && image.getHeight()==540 && (image.getRGB(0,0)>>>24)==0, "own typography rasterizes headlessly to alpha texture");
        var disabledQa = new QaRecorder(null);
        disabledQa.captureSource(known, p -> { throw new AssertionError("Disabled QA called exporter"); });
        disabledQa.event("test", known);
        check(!disabledQa.enabled(), "normal provider QA path performs no export or I/O");
        Path qaDir = temp.resolve("qa-evidence"); var qa = new QaRecorder(qaDir);
        java.util.concurrent.atomic.AtomicInteger exports = new java.util.concurrent.atomic.AtomicInteger();
        qa.captureSource(ProgressSnapshot.WAITING, p -> exports.incrementAndGet());
        check(exports.get()==0, "QA never presents waiting state as a source event");
        qa.captureSource(known, p -> exports.incrementAndGet());
        qa.captureSource(ProgressFileReader.parse(event(99,"6","8")), p -> exports.incrementAndGet());
        check(exports.get()==1, "QA captures once per observed stage/status rather than every count");
        check(Files.readString(qaDir.resolve("lifecycle.jsonl")).contains("sourceSnapshot"), "QA binds captured frame audit to observed source snapshot");
        check(!InfinityWindowProvider.graphicsDisabled(new String[]{"--launchTarget","forgeclient"}), "AWT headless flag does not falsely disable GLFW client graphics");
        check(InfinityWindowProvider.graphicsDisabled(new String[]{"--launchTarget","forgeserver"}), "server target disables graphics independently of AWT");
        System.setProperty("unified.infinity.headless", "true");
        check(InfinityWindowProvider.graphicsDisabled(new String[]{"--launchTarget","forgeclient"}), "explicit Infinity headless flag still suppresses graphics");
        System.clearProperty("unified.infinity.headless");
        var providers = ServiceLoader.load(ImmediateWindowProvider.class).stream().filter(p -> p.type().getName().equals(InfinityWindowProvider.class.getName())).toList();
        check(providers.size()==1, "real FML SPI descriptor resolves our provider");
        var provider = (InfinityWindowProvider) providers.getFirst().get();
        check(provider.name().equals("unifiedinfinity"), "SPI name matches FML config");
        provider.initialize(new String[]{"--launchTarget","forgeserver"}).run();
        provider.periodicTick(); provider.updateModuleReads(ModuleLayer.boot());
        check(provider.getGLVersion().equals("0.0"), "server initialization loads no native GLFW context or game class");
        check(!provider.positionWindow(java.util.Optional.empty(),i->{},i->{},i->{},i->{}), "headless mode declines window ownership");
        provider.close(); provider.close(); check(true,"headless close is idempotent");
        System.out.println("RESULT: " + passed + " assertions passed; graphical client/handoff not exercised by this suite");
    }
}
