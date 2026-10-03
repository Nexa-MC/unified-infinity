package dev.modcompat.preload;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

/** Bounded atomic-snapshot reader. No file watcher, loader imports, or worker pool. */
public final class ProgressFileReader {
    public static final long POLL_NANOS = 100_000_000L;
    public static final int MAX_BYTES = 16_384;
    private final Path path;
    private final long notBeforeMillis;
    private long nextPoll;
    private ProgressSnapshot latest = ProgressSnapshot.WAITING;
    private long reads;
    public ProgressFileReader(Path path, long notBeforeMillis) {
        this.path = path;
        this.notBeforeMillis = notBeforeMillis;
    }
    public synchronized ProgressSnapshot poll(long nowNanos) {
        if (path == null || nowNanos < nextPoll) return latest;
        nextPoll = nowNanos + POLL_NANOS;
        reads++;
        try {
            if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
                    || Files.getLastModifiedTime(path, LinkOption.NOFOLLOW_LINKS).toMillis() < notBeforeMillis)
                return latest;
            // Size check plus limited channel read prevents a concurrent replacement/growth from causing an unbounded allocation.
            try (SeekableByteChannel channel = Files.newByteChannel(path, StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS)) {
                if (channel.size() > MAX_BYTES) return latest;
                ByteBuffer bytes = ByteBuffer.allocate(MAX_BYTES + 1);
                while (bytes.hasRemaining() && channel.read(bytes) > 0) { }
                if (bytes.position() > MAX_BYTES) return latest;
                bytes.flip();
                ProgressSnapshot candidate = parse(StandardCharsets.UTF_8.decode(bytes).toString());
                if (candidate.sequence() > latest.sequence()) latest = candidate;
            }
        } catch (IOException | RuntimeException ignored) {
            // Missing/malformed/temporarily unavailable telemetry must never abort game startup.
        }
        return latest;
    }
    public long reads() { return reads; }
    public static ProgressSnapshot parse(String json) {
        JsonObject value = JsonParser.parseString(json).getAsJsonObject();
        String error = value.has("error") && !value.get("error").isJsonNull() ? value.get("error").getAsString() : null;
        if (error != null) error = error.replaceAll("[^a-zA-Z0-9_.$]", "").substring(0, Math.min(80, error.replaceAll("[^a-zA-Z0-9_.$]", "").length()));
        return new ProgressSnapshot(value.get("stage").getAsString(), value.get("status").getAsString(),
                count(value, "completed"), count(value, "total"), integer(value, "elapsedMs"), integer(value, "sequence"), error);
    }
    private static Long count(JsonObject o, String name) {
        return !o.has(name) || o.get(name).isJsonNull() ? null : integer(o, name);
    }
    private static long integer(JsonObject o, String name) {
        // Exact integer conversion rejects fractions and overflow rather than silently truncating.
        return o.get(name).getAsBigDecimal().longValueExact();
    }
}
