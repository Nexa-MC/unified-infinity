package org.sinytra.connector.infinity.inventory;

import java.io.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.zip.ZipFile;
import java.util.zip.ZipInputStream;
import static org.sinytra.connector.infinity.inventory.AdmissionInventory.*;

/** Launch-owned receipts. Metadata fields, ID prefixes and matching bytes at another path confer no trust. */
public final class TrustedPayloads {
    private static final Map<Path, Receipt> RECEIPTS = new ConcurrentHashMap<>();
    private static Thread registrationOwner;
    private static boolean sealed;
    static synchronized void beginRegistration() {
        if (sealed || registrationOwner != null) throw new IllegalStateException("Admission trust registration already started or sealed");
        registrationOwner = Thread.currentThread();
    }
    static synchronized void sealRegistration() {
        requireRegistration(); registrationOwner = null; sealed = true;
    }
    private static synchronized void requireRegistration() {
        if (sealed || registrationOwner != Thread.currentThread())
            throw new IllegalStateException("Only the bootstrap registration owner may create trusted origins");
    }
    /** Session-only rebinding after it verifies the registered transform/extraction authority. */
    static Receipt bindPinnedCopy(Path known, Path target) throws IOException {
        Receipt receipt = RECEIPTS.get(key(known));
        if (receipt == null || !stillPinned(key(known), receipt)) throw new IOException("No valid pre-authorized source receipt: " + known);
        Path actual = target.toRealPath(); verify(actual, receipt.sha256()); put(actual, receipt); return receipt;
    }
    private TrustedPayloads() {}
    public static final class Root {
        private final Path path;
        private Root(Path path) { this.path = path; }
        public Path path() { return path; }
    }
    public record Receipt(SourceChain source, String sha256, Set<String> primaryIds, Category category, Optional<String> apiFamily) {
        public Receipt { primaryIds = Set.copyOf(primaryIds); Objects.requireNonNull(apiFamily); }
    }
    /** Called by trusted bootstrap using its pinned installation manifest, never values supplied by candidate metadata. */
    public static Root registerRoot(Path path, String expectedSha256, Set<String> primaryIds) throws IOException {
        requireRegistration();
        Path actual = path.toRealPath();
        verify(actual, expectedSha256);
        put(actual, new Receipt(new SourceChain(actual.toString(), List.of()), expectedSha256,
            primaryIds, Category.PLATFORM, Optional.empty()));
        return new Root(actual);
    }
    /** expectedSha256 and primaryIds must come from the trusted build manifest or fixed managed-module pins. */
    public static Receipt registerExtracted(Root root, Path extracted, List<String> entries, String expectedSha256,
                                            Set<String> primaryIds, String apiFamily) throws IOException {
        return registerExtracted(root, extracted, entries, expectedSha256, primaryIds, Category.BUNDLED_API, Optional.of(apiFamily));
    }
    /** Platform support payloads retain their own role and are never folded into the API display summary. */
    public static Receipt registerExtracted(Root root, Path extracted, List<String> entries, String expectedSha256,
                                            Set<String> primaryIds, Category category, Optional<String> apiFamily) throws IOException {
        requireRegistration(); Objects.requireNonNull(root);
        if (category != Category.BUNDLED_API && category != Category.PLATFORM)
            throw new IllegalArgumentException("Managed payload requires API or platform role");
        if (root(root.path).isEmpty() || entries.isEmpty()) throw new IllegalArgumentException("Missing trusted extraction root");
        SourceChain chain = new SourceChain(root.path.toString(), entries);
        verifyEmbedded(root.path, chain.embeddedEntries(), expectedSha256);
        Path actual = extracted.toRealPath();
        verify(actual, expectedSha256);
        Receipt receipt = new Receipt(chain, expectedSha256,
            primaryIds, category, apiFamily);
        put(actual, receipt); return receipt;
    }
    public static Optional<Root> root(Path path) {
        Path key = key(path); Receipt receipt = RECEIPTS.get(key);
        return receipt != null && receipt.category() == Category.PLATFORM && receipt.source().embeddedEntries().isEmpty() && stillPinned(key, receipt)
            ? Optional.of(new Root(key)) : Optional.empty();
    }
    public static Optional<Receipt> find(Path path, Collection<String> primaryIds) {
        Receipt receipt = RECEIPTS.get(key(path));
        return receipt != null && receipt.primaryIds().containsAll(primaryIds) && !primaryIds.isEmpty() && stillPinned(key(path), receipt)
            && (receipt.source().embeddedEntries().isEmpty() || root(Path.of(receipt.source().installationRoot())).isPresent())
            ? Optional.of(receipt) : Optional.empty();
    }
    private static void verifyEmbedded(Path root, List<String> entries, String expected) throws IOException {
        if (entries.size() > 8) throw new IOException("Managed nested chain exceeds 8 levels");
        byte[] payload;
        try (ZipFile archive = new ZipFile(root.toFile())) {
            var entry = archive.getEntry(entries.getFirst());
            if (entry == null) throw new IOException("Managed root has no declared embedded entry " + entries.getFirst());
            try (InputStream input = archive.getInputStream(entry)) { payload = bounded(input); }
        }
        for (String path : entries.subList(1, entries.size())) {
            byte[] next = null;
            try (ZipInputStream archive = new ZipInputStream(new ByteArrayInputStream(payload))) {
                for (var entry = archive.getNextEntry(); entry != null; entry = archive.getNextEntry())
                    if (entry.getName().equals(path)) {
                        if (next != null) throw new IOException("Duplicate managed embedded entry " + path);
                        next = bounded(archive);
                    }
            }
            if (next == null) throw new IOException("Managed chain has no embedded entry " + path);
            payload = next;
        }
        try {
            if (!HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(payload)).equals(expected))
                throw new IOException("Managed source chain pin mismatch");
        } catch (NoSuchAlgorithmException e) { throw new AssertionError(e); }
    }
    private static byte[] bounded(InputStream input) throws IOException {
        byte[] bytes = input.readNBytes(32 * 1024 * 1024 + 1);
        if (bytes.length > 32 * 1024 * 1024) throw new IOException("Managed embedded payload exceeds 32 MiB");
        return bytes;
    }
    // Admission only. Frozen UI snapshots never call this method or reopen archives.
    private static boolean stillPinned(Path path, Receipt receipt) {
        try { verify(path, receipt.sha256()); return true; }
        catch (IOException e) { return false; }
    }
    private static Path key(Path path) {
        try { return path.toRealPath(); } catch (IOException e) { return path.toAbsolutePath().normalize(); }
    }
    private static void put(Path path, Receipt receipt) {
        Receipt previous = RECEIPTS.putIfAbsent(path, receipt);
        if (previous != null && !previous.equals(receipt)) throw new IllegalStateException("Conflicting trusted payload receipt: " + path);
    }
    private static void verify(Path path, String expected) throws IOException {
        if (!expected.matches("[0-9a-f]{64}")) throw new IllegalArgumentException("Invalid SHA-256 pin");
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream input = Files.newInputStream(path)) {
                byte[] buffer = new byte[65536]; int count;
                while ((count = input.read(buffer)) != -1) digest.update(buffer, 0, count);
            }
            if (!HexFormat.of().formatHex(digest.digest()).equals(expected)) throw new IOException("Managed payload pin mismatch: " + path);
        } catch (NoSuchAlgorithmException e) { throw new AssertionError(e); }
    }
}
