package dev.modcompat.runtime.modlist;

import java.util.Optional;
import org.sinytra.connector.infinity.inventory.AdmissionInventory.Snapshot;

/** One informational notification per process; an absent final snapshot is not an empty result. */
public final class ExclusionNoticeState {
    private boolean settled;
    public boolean shouldNotify(boolean atMainMenu, Optional<Snapshot> snapshot) {
        if (settled || !atMainMenu || snapshot.isEmpty()) return false;
        settled = true;
        return !snapshot.orElseThrow().exclusions().isEmpty();
    }
}
