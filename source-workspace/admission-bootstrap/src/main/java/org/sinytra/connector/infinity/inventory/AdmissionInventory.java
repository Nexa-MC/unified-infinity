package org.sinytra.connector.infinity.inventory;

import java.util.*;

/** Immutable presentation facts. This is neither discovery nor a second dependency resolver. */
public final class AdmissionInventory {
    private AdmissionInventory() {}
    public enum Ecosystem { FABRIC, QUILT, FORGE, NEOFORGE, UNKNOWN }
    public enum Lane { FABRIC_PROJECTION, NATIVE_QUILT, FORGE_ADAPTER, NATIVE_HOST, GAME, UNKNOWN }
    public enum Category { USER_MOD, BUNDLED_API, PLATFORM, UNKNOWN }
    public enum Evidence { ORIGINAL_INTAKE, MANAGED_PINNED_EXTRACTION, SELECTED_HOST, UNKNOWN }
    public enum Replacement { NOT_VERIFIED, NO_API_REPLACEMENT, SELECTED_PROVIDER_PRESENT }

    /** embeddedEntries are archive-relative entries, never extracted temporary filesystem paths. */
    public record SourceChain(String installationRoot, List<String> embeddedEntries) {
        public SourceChain {
            Objects.requireNonNull(installationRoot);
            embeddedEntries = List.copyOf(embeddedEntries);
            for (String entry : embeddedEntries) {
                if (entry.isBlank() || entry.startsWith("/") || entry.contains("\\")
                    || Arrays.asList(entry.split("/")).contains(".."))
                    throw new IllegalArgumentException("Invalid embedded source entry: " + entry);
            }
        }
        public SourceChain nested(String entry) {
            List<String> next = new ArrayList<>(embeddedEntries); next.add(entry);
            return new SourceChain(installationRoot, next);
        }
    }
    public record Provenance(List<SourceChain> installationSources, String runtimeLocation,
                             Optional<String> originalSha256, Evidence evidence) {
        public Provenance {
            installationSources = List.copyOf(installationSources);
            Objects.requireNonNull(runtimeLocation); Objects.requireNonNull(originalSha256); Objects.requireNonNull(evidence);
        }
    }
    public record Entry(String canonicalId, Optional<String> originalId, String displayName,
                        Optional<String> sourceVersion, Optional<String> declaredVersion, String loadedVersion,
                        Ecosystem ecosystem, Lane lane, Category category, Optional<String> apiFamily,
                        List<String> licenses, Provenance provenance) {
        public Entry {
            Objects.requireNonNull(canonicalId); Objects.requireNonNull(originalId); Objects.requireNonNull(displayName);
            Objects.requireNonNull(sourceVersion); Objects.requireNonNull(declaredVersion); Objects.requireNonNull(loadedVersion);
            Objects.requireNonNull(ecosystem); Objects.requireNonNull(lane); Objects.requireNonNull(category);
            Objects.requireNonNull(apiFamily); Objects.requireNonNull(provenance); licenses = List.copyOf(licenses);
        }
        public Entry(String canonicalId, Optional<String> originalId, String displayName, Optional<String> sourceVersion,
                     Optional<String> declaredVersion, String loadedVersion, Ecosystem ecosystem, Lane lane,
                     Category category, Optional<String> apiFamily, Provenance provenance) {
            this(canonicalId, originalId, displayName, sourceVersion, declaredVersion, loadedVersion, ecosystem, lane,
                category, apiFamily, List.of(), provenance);
        }
        /** ID aliases are search terms, not additional inventory entries. */
        public boolean matches(String query) {
            String q = query.toLowerCase(Locale.ROOT);
            return displayName.replaceAll("§.", "").toLowerCase(Locale.ROOT).contains(q)
                || canonicalId.toLowerCase(Locale.ROOT).contains(q)
                || originalId.map(id -> id.toLowerCase(Locale.ROOT).contains(q)).orElse(false);
        }
    }
    public record Counts(int userMods, int bundledApi, int platform, int unknown) {
        public int total() { return userMods + bundledApi + platform + unknown; }
        public static Counts of(List<Entry> entries) {
            int user = 0, api = 0, platform = 0, unknown = 0;
            for (Entry entry : entries) switch (entry.category()) {
                case USER_MOD -> user++;
                case BUNDLED_API -> api++;
                case PLATFORM -> platform++;
                case UNKNOWN -> unknown++;
            }
            return new Counts(user, api, platform, unknown);
        }
    }
    /** A present provider is not a claim that every consumer's version/API requirement is satisfied. */
    public record Exclusion(SourceChain source, String originalId, String ruleId, String reason,
                            Replacement replacement, List<String> selectedReplacementIds,
                            boolean earlyServiceProvider) {
        public Exclusion {
            Objects.requireNonNull(source); Objects.requireNonNull(originalId); Objects.requireNonNull(ruleId);
            Objects.requireNonNull(reason); Objects.requireNonNull(replacement);
            selectedReplacementIds = List.copyOf(selectedReplacementIds);
        }
    }
    public record Snapshot(int schemaVersion, String coreBuildIdentity, List<Entry> entries,
                           Counts counts, List<Exclusion> exclusions) {
        public Snapshot {
            entries = List.copyOf(entries); exclusions = List.copyOf(exclusions);
            Objects.requireNonNull(coreBuildIdentity); Objects.requireNonNull(counts);
            if (!counts.equals(Counts.of(entries))) throw new IllegalArgumentException("Counts must equal final admitted rows");
            Set<String> ids = new HashSet<>();
            for (Entry entry : entries) if (!ids.add(entry.canonicalId()))
                throw new IllegalArgumentException("Final host inventory contains duplicate ID " + entry.canonicalId());
        }
        public List<Entry> search(String query) { return entries.stream().filter(e -> e.matches(query)).toList(); }
    }
}
