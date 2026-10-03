package dev.modcompat.preload;

import com.google.gson.Gson;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Set;

/** Opt-in, bounded QA evidence only. A null destination does no I/O. */
final class QaRecorder {
    @FunctionalInterface interface Exporter { void export(Path path) throws IOException; }
    private final Path directory;
    private final Set<String> captured = new HashSet<>();
    private final Gson gson = new Gson();
    private boolean ioFailed;
    QaRecorder(Path directory) { this.directory = directory; }
    boolean enabled() { return directory != null && !ioFailed; }
    synchronized void event(String event, ProgressSnapshot state) {
        if (!enabled()) return;
        try {
            Files.createDirectories(directory);
            var record = new LinkedHashMap<String, Object>();
            record.put("event", event); record.put("observedAtEpochMs", System.currentTimeMillis());
            if (state != null) record.put("sourceSnapshot", state);
            Files.writeString(directory.resolve("lifecycle.jsonl"), gson.toJson(record) + "\n", StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND);
            System.out.println("INFINITY_UI_QA " + event + (state == null ? "" : " source=" + state.stage() + "/" + state.status() + " sequence=" + state.sequence()));
        } catch (IOException | RuntimeException failure) { disable(failure); }
    }
    synchronized void captureSource(ProgressSnapshot state, Exporter exporter) {
        if (!enabled() || state.sequence() < 0 || state.stage().equals("waiting")) return;
        capture("source-" + state.stage() + "-" + state.status(), state, exporter);
    }
    synchronized void capture(String label, ProgressSnapshot state, Exporter exporter) {
        if (!enabled() || captured.size() >= 16 || !captured.add(label)) return;
        try {
            exporter.export(directory.resolve(label + ".png"));
            event("frame-" + label, state);
        } catch (IOException | RuntimeException failure) { disable(failure); }
    }
    private void disable(Exception failure) {
        ioFailed = true;
        System.err.println("INFINITY_UI_QA disabled after " + failure.getClass().getSimpleName());
    }
}
