package org.sinytra.connector.infinity.inventory;

import java.util.*;
import static org.sinytra.connector.infinity.inventory.AdmissionInventory.*;

/** Candidate facts only become rows when the exact selected owner and canonical ID match. */
public final class InventoryReconciler {
    private InventoryReconciler() {}
    public record Key(Object owner, String canonicalId) {
        public Key { Objects.requireNonNull(owner); Objects.requireNonNull(canonicalId); }
        @Override public boolean equals(Object other) {
            return other instanceof Key k && owner == k.owner && canonicalId.equals(k.canonicalId);
        }
        @Override public int hashCode() { return 31 * System.identityHashCode(owner) + canonicalId.hashCode(); }
    }
    public record HostRow(Object owner, String canonicalId, String displayName, String loadedVersion, String runtimeLocation) {}

    public static Snapshot reconcile(String identity, List<HostRow> finalRows, Map<Key, Entry> captured,
                                     List<Exclusion> exclusions) {
        List<Entry> entries = new ArrayList<>();
        for (HostRow row : finalRows) {
            Entry candidate = captured.get(new Key(row.owner(), row.canonicalId()));
            if (candidate == null) {
                entries.add(new Entry(row.canonicalId(), Optional.empty(), row.displayName(), Optional.empty(),
                    Optional.empty(), row.loadedVersion(), Ecosystem.UNKNOWN, Lane.UNKNOWN, Category.UNKNOWN,
                    Optional.empty(), new Provenance(List.of(), row.runtimeLocation(), Optional.empty(), Evidence.UNKNOWN)));
            } else {
                Provenance source = candidate.provenance();
                entries.add(new Entry(row.canonicalId(), candidate.originalId(), row.displayName(), candidate.sourceVersion(),
                    candidate.declaredVersion(), row.loadedVersion(), candidate.ecosystem(), candidate.lane(), candidate.category(),
                    candidate.apiFamily(), candidate.licenses(), new Provenance(source.installationSources(), row.runtimeLocation(),
                    source.originalSha256(), source.evidence())));
            }
        }
        return new Snapshot(1, identity, entries, Counts.of(entries), exclusions);
    }
}
