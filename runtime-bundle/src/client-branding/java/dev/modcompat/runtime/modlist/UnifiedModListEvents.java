package dev.modcompat.runtime.modlist;

import java.util.Optional;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.client.gui.components.toasts.SystemToast;
import net.neoforged.neoforge.client.event.ClientTickEvent;
import org.sinytra.connector.infinity.inventory.AdmissionInventory.Snapshot;
import net.neoforged.neoforge.client.event.ScreenEvent;
import net.neoforged.neoforge.client.gui.ModListScreen;
import net.neoforged.neoforge.common.NeoForge;
import org.sinytra.connector.infinity.inventory.AdmissionSession;

/** Explicit late client product hook. FML's installation-pinned GAME component calls initialize once. */
public final class UnifiedModListEvents {
    private static boolean initialized;
    private static final ExclusionNoticeState exclusionNotice = new ExclusionNoticeState();
    private static final SystemToast.SystemToastId EXCLUSION_TOAST = new SystemToast.SystemToastId(10000L);
    private UnifiedModListEvents() { }

    /** Called only in the loader-owned client setup phase; never through an ordinary mod annotation. */
    public static synchronized void initialize() {
        if (initialized) throw new IllegalStateException("Unified mod-list client component initialized twice");
        NeoForge.EVENT_BUS.addListener(UnifiedModListEvents::opening);
        NeoForge.EVENT_BUS.addListener(UnifiedModListEvents::tick);
        initialized = true;
    }

    private static void tick(ClientTickEvent.Post event) {
        Minecraft minecraft = Minecraft.getInstance();
        if (!(minecraft.screen instanceof TitleScreen)) return;
        Optional<Snapshot> snapshot = AdmissionSession.isInstalled() ? AdmissionSession.current().selectedSnapshot() : Optional.empty();
        if (exclusionNotice.shouldNotify(true, snapshot)) {
            int skipped = snapshot.orElseThrow().exclusions().size();
            minecraft.getToasts().addToast(SystemToast.multiline(minecraft, EXCLUSION_TOAST,
                InventoryDetails.tr("exclusions_toast_title", skipped), InventoryDetails.tr("exclusions_toast_body")));
        }
    }

    private static void opening(ScreenEvent.Opening event) {
        if (event.getNewScreen() == null || event.getNewScreen().getClass() != ModListScreen.class) return;
        // The event's current screen is the title/pause/caller screen. Config/credits return directly to our instance.
        event.setNewScreen(new UnifiedModListScreen(event.getCurrentScreen(), AdmissionSession.isInstalled() ? AdmissionSession.current().selectedSnapshot() : Optional.empty()));
    }
}
