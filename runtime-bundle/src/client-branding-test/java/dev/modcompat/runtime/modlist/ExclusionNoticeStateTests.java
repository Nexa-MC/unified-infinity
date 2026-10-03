package dev.modcompat.runtime.modlist;

import java.util.*;
import org.sinytra.connector.infinity.inventory.AdmissionInventory.*;

/** Notification timing/count semantics only; no policy, filesystem, Minecraft or Java service execution. */
public final class ExclusionNoticeStateTests {
    private static int checks;
    private static void check(boolean value, String reason) { if (!value) throw new AssertionError(reason); checks++; }
    private static Snapshot snapshot(List<Exclusion> exclusions) {
        return new Snapshot(1, "test", List.of(), new Counts(0, 0, 0, 0), exclusions);
    }
    public static void main(String[] args) {
        Exclusion first = new Exclusion(new SourceChain("mods/parent.jar", List.of("META-INF/jars/external.jar")),
            "external_api", "external-infrastructure", "Exact recorded reason", Replacement.SELECTED_PROVIDER_PRESENT,
            List.of("selected_api"), true);
        Exclusion second = new Exclusion(new SourceChain("mods/other.jar", List.of()), "external_api", "external-infrastructure",
            "Another source", Replacement.NOT_VERIFIED, List.of(), false);
        Snapshot full = snapshot(List.of(first, second));
        ExclusionNoticeState state = new ExclusionNoticeState();
        check(!state.shouldNotify(true, Optional.empty()), "An unpublished inventory must not settle the notice");
        check(!state.shouldNotify(false, Optional.of(full)), "Do not notify before reaching the main menu");
        check(state.shouldNotify(true, Optional.of(full)), "First successful menu view notifies");
        check(!state.shouldNotify(true, Optional.of(full)), "No repeated toast on later ticks");
        check(!state.shouldNotify(false, Optional.of(full)), "No later world notification");
        check(!state.shouldNotify(true, Optional.of(full)), "Returning to menu does not repeat");
        check(full.exclusions().size() == 2, "Same ID at two original sources is two logical exclusion records");
        check(first.source().embeddedEntries().equals(List.of("META-INF/jars/external.jar")), "Original nested payload retained");
        check(InventoryUiModel.source(first.source()).equals("mods/parent.jar!/META-INF/jars/external.jar"), "Do not substitute entire parent for nested source");
        check(first.selectedReplacementIds().equals(List.of("selected_api")), "Actual provider IDs retained without coverage inference");
        check(first.earlyServiceProvider(), "Early provider metadata flag retained");
        check(full.entries().isEmpty() && full.counts().total() == 0, "Exclusions never become loaded rows or count as providers");
        ExclusionNoticeState empty = new ExclusionNoticeState();
        check(!empty.shouldNotify(true, Optional.of(snapshot(List.of()))), "No toast for a final empty exclusions list");
        check(!empty.shouldNotify(true, Optional.of(full)), "One frozen inventory epoch is settled once");
        check(new ExclusionNoticeState().shouldNotify(true, Optional.of(full)), "A new process state can notify again");
        try { full.exclusions().clear(); throw new AssertionError("Mutable exclusions"); }
        catch (UnsupportedOperationException expected) { checks++; }
        for (int width : new int[]{320, 440, 854}) for (int height : new int[]{180, 240, 480}) {
            var layout = InventoryUiModel.Layout.of(width, height, true);
            int button = layout.buttonWidth();
            check(button > 0, "Positive warning-button width");
            check(20 + button * 3 <= width - 8 - button, "Warnings never overlap Done");
            check(layout.footerY() + 20 <= height, "Persistent warning fits small viewport");
        }
        System.out.println("PASS: " + checks + " frozen exclusion notification/layout contracts");
    }
}
