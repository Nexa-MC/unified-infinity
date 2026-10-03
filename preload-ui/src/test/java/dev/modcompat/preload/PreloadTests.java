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
        responsiveGeometry(known);
        nonblockingTelemetry(known);
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

    private static void responsiveGeometry(ProgressSnapshot state) {
        for (int[] size : new int[][] {{960,540,960,540}, {1180,812,1180,812}, {1364,1024,1364,1024}, {320,320,320,320},
                {320,900,320,900}, {1920,320,1920,320}, {960,540,1920,1080}, {1000,700,1500,1050},
                {3840,2160,7680,4320}, {1,1,1,1}, {1,1000,1,1000}, {Integer.MAX_VALUE,1,Integer.MAX_VALUE,1}}) {
            var layout = ResponsiveLayout.of(size[0], size[1], size[2], size[3]);
            check(layout.pixelWidth() > 0 && layout.pixelHeight() > 0
                    && layout.pixelWidth() <= ResponsiveLayout.MAX_TEXTURE_EDGE && layout.pixelHeight() <= ResponsiveLayout.MAX_TEXTURE_EDGE
                    && (long) layout.pixelWidth() * layout.pixelHeight() <= ResponsiveLayout.MAX_TEXTURE_PIXELS,
                    "raster allocation bounded at " + java.util.Arrays.toString(size));
            check(layout.iconX() >= layout.margin() && layout.iconX() + layout.iconSize() <= layout.width() - layout.margin()
                    && layout.iconTop() > layout.headerLine() && layout.titleBaseline() > layout.iconTop() + layout.iconSize()
                    && layout.detailBaseline() + 16 < layout.footerLine(), "anchored geometry has no collisions at " + java.util.Arrays.toString(size));
            check(layout.barX() >= layout.margin() - .001 && layout.barX() + layout.barWidth() <= layout.width() - layout.margin() + .001,
                    "progress stays inside viewport margins");
        }
        check(!ResponsiveLayout.drawable(960,540,0,0) && !ResponsiveLayout.drawable(0,540,960,540)
                && !ResponsiveLayout.drawable(960,540,-1,540), "zero/minimized/negative geometry never divides or allocates");
        try { ResponsiveLayout.of(960,540,0,0); throw new AssertionError("zero framebuffer accepted"); }
        catch (IllegalArgumentException expected) { check(true, "zero framebuffer rejected before rendering"); }
        var base = ResponsiveLayout.of(960,540,960,540); var hidpi = ResponsiveLayout.of(960,540,1920,1080);
        check(base.width() == hidpi.width() && base.iconSize() == hidpi.iconSize() && base.titleBaseline() == hidpi.titleBaseline(),
                "HiDPI changes raster density without stretching logical UI");
        var narrow = ResponsiveLayout.of(320,320,320,320);
        check(narrow.stackedFooter() && narrow.compact() && !base.stackedFooter(), "narrow footer reflows into readable separate rows");
        var narrowImage = TextLayer.render(state, true, narrow);
        check(narrowImage.getWidth() == 320 && narrowImage.getHeight() == 320, "compact typography uses responsive raster");
        var canvas = new TextLayer.Canvas();
        var first = canvas.render(state, true, base);
        Object storage = ((java.awt.image.DataBufferInt) first.getRaster().getDataBuffer()).getData();
        var resized = canvas.render(state, true, narrow);
        check(storage == ((java.awt.image.DataBufferInt) resized.getRaster().getDataBuffer()).getData(),
                "continuous text resize reuses bounded pixel storage");
        check(resized.getRGB(0, 0) == 0 && resized.getRGB(160, 160) == narrowImage.getRGB(160, 160),
                "reused text canvas clears old pixels and preserves raster semantics");
        var g = narrowImage.createGraphics();
        try {
            g.setFont(new java.awt.Font(java.awt.Font.SANS_SERIF, java.awt.Font.PLAIN, 13));
            var lines = TextLayer.wrap(g, "Compatibility stages complete · waiting for Minecraft", narrow.contentWidth(), 2);
            check(lines.size() == 2 && lines.stream().allMatch(line -> g.getFontMetrics().stringWidth(line) <= narrow.contentWidth()),
                    "long stage detail wraps without entering margins");
        } finally { g.dispose(); }
        var stats = new ResponsivenessStats(); stats.poll(1); stats.poll(150_000_001);
        stats.frame(1, 2); stats.frame(150_000_001, 170_000_001);
        check(stats.summary().contains("frameGapsOver100ms=1") && stats.summary().contains("eventPollGapMaxMs=150.0"),
                "diagnostics expose long frames and event-pump gaps separately");
    }

    private static void nonblockingTelemetry(ProgressSnapshot state) throws Exception {
        var entered = new java.util.concurrent.CountDownLatch(1);
        var release = new java.util.concurrent.CountDownLatch(1);
        var finished = new java.util.concurrent.CountDownLatch(1);
        var sampler = new ProgressSampler(now -> {
            entered.countDown();
            try {
                // Model a slow operation which does not finish immediately on interruption.
                try { release.await(3, java.util.concurrent.TimeUnit.SECONDS); }
                catch (InterruptedException expected) { release.await(3, java.util.concurrent.TimeUnit.SECONDS); }
            } catch (InterruptedException expected) { Thread.currentThread().interrupt(); }
            finally { finished.countDown(); }
            return state;
        });
        try {
            sampler.start();
            check(entered.await(2, java.util.concurrent.TimeUnit.SECONDS), "telemetry sampler starts without native graphics");
            check(sampler.latest() == ProgressSnapshot.WAITING, "snapshot access never waits for a pending telemetry read");
            sampler.close();
            check(finished.getCount() == 1, "sampler shutdown does not join a stalled filesystem read");
        } finally { release.countDown(); sampler.close(); }
        check(finished.await(2, java.util.concurrent.TimeUnit.SECONDS), "released telemetry worker finishes after shutdown");
    }
}
