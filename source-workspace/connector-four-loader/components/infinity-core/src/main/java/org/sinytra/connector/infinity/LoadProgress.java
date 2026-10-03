package org.sinytra.connector.infinity;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

/** Small latest-state IPC contract. ConnectorLocator alone owns the ordered phase boundaries. */
public final class LoadProgress {
    public static final String FILE_PROPERTY = "unified.infinity.progressFile";
    public enum Stage { DISCOVER, RESOLVE, TRANSFORM, COMMIT }

    private static Stage stage;
    private static String status = "running";
    private static Integer completed;
    private static Integer total;
    private static final long started = System.nanoTime();
    private static long sequence;
    private static long lastPublishAttempt;
    private static boolean warned;
    private static String error;

    private LoadProgress() {}

    public static synchronized void begin(Stage next) {
        stage = next;
        status = "running";
        completed = null;
        total = null;
        error = null;
        publish(true);
    }

    public static synchronized void finish(Integer actualOutputs) {
        if (stage == null || status.equals("failed")) return;
        status = "complete";
        if (actualOutputs != null) completed = total = actualOutputs;
        publish(true);
    }

    public static synchronized void transformUnits(int count, int cached) {
        if (stage != Stage.TRANSFORM || !status.equals("running")) return;
        if (count < 0 || cached < 0 || cached > count) throw new IllegalArgumentException("Invalid progress units");
        completed = cached;
        total = count;
        publish(true);
    }

    public static synchronized void transformedOne() {
        if (stage != Stage.TRANSFORM || !status.equals("running") || completed == null) return;
        completed++;
        if (completed > total) throw new IllegalStateException("Transformation completion exceeds input count");
        publish(completed.equals(total));
    }

    public static synchronized void fail(Throwable failure) {
        if (stage == null) return;
        status = "failed";
        // Never leak input paths, exception messages or mod contents to a UI snapshot.
        error = failure.getClass().getSimpleName().replaceAll("[^a-zA-Z0-9_$]", "");
        publish(true);
    }

    private static void publish(boolean force) {
        sequence++;
        String location = System.getProperty(FILE_PROPERTY);
        if (location == null || location.isBlank()) return;
        long now = System.nanoTime();
        if (!force && now - lastPublishAttempt < 100_000_000L) return;
        lastPublishAttempt = now;
        Path temp = null;
        try {
            Path destination = Path.of(location);
            if (!destination.isAbsolute()) throw new IOException("Progress destination must be absolute");
            Files.createDirectories(destination.getParent());
            temp = Files.createTempFile(destination.getParent(), ".infinity-progress-", ".tmp");
            String json = "{\"stage\":\"" + stage.name().toLowerCase(java.util.Locale.ROOT)
                + "\",\"status\":\"" + status + "\",\"completed\":" + completed + ",\"total\":" + total
                + ",\"elapsedMs\":" + Math.max(0, (System.nanoTime() - started) / 1_000_000L)
                + ",\"sequence\":" + sequence + (error == null ? "" : ",\"error\":\"" + error + "\"") + "}\n";
            Files.writeString(temp, json, StandardCharsets.UTF_8);
            try {
                Files.move(temp, destination, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException e) {
                // A partial snapshot is worse than a stale one; do not fall back to non-atomic writes.
                throw new IOException("Atomic progress replacement unsupported", e);
            }
        } catch (IOException | RuntimeException e) {
            if (!warned) {
                System.err.println("[Unified Infinity] Progress snapshot unavailable (" + e.getClass().getSimpleName() + ")");
                warned = true;
            }
        } finally {
            if (temp != null) {
                try { Files.deleteIfExists(temp); } catch (IOException ignored) {}
            }
        }
    }
}
