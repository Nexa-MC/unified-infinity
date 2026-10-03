/* Unified Infinity installation-backed legacy views. SPDX-License-Identifier: LGPL-2.1-only */
package net.neoforged.fml.loading.unified;

import java.nio.file.Path;
import java.util.ArrayList;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.ModContainer;
import net.neoforged.neoforgespi.language.*;
import org.sinytra.connector.infinity.inventory.AdmissionSession;

/** Real IDs/versions from pinned implementation metadata; no @Mod scan, constructor or ordinary mod bus. */
public final class InternalCapabilityLanguageLoader implements IModLanguageLoader {
    @Override public String name() { return "unified_internal"; }
    @Override public String version() { return "1"; }
    @Override public ModContainer loadMod(IModInfo info, ModFileScanData ignored, ModuleLayer gameLayer) {
        var session = AdmissionSession.current();
        var file = info.getOwningFile().getFile();
        var permitted = new ArrayList<Path>(session.installedComponents("COMPATIBILITY_GAME"));
        permitted.addAll(session.installedComponents("PRODUCT_GAME"));
        var origins = session.sourcePathsForRuntimeObject(file);
        if (origins.size() != 1 || !permitted.contains(origins.getFirst()) || !session.permitsRuntimeObject(file))
            throw new IllegalStateException("unified_internal is reserved for exact installed implementation metadata");
        return new CapabilityView(info);
    }
    public static boolean isCapabilityView(ModContainer container) { return container instanceof CapabilityView; }
    private static final class CapabilityView extends ModContainer {
        CapabilityView(IModInfo info) { super(info); }
        @Override public IEventBus getEventBus() { return null; }
    }
}
