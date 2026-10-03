package org.sinytra.connector.quilt;

import org.quiltmc.loader.api.LanguageAdapter;
import org.quiltmc.loader.api.LanguageAdapterException;
import org.quiltmc.loader.api.ModContainer;

/** Uses the host's default Java adapter and target classloader, without storing another entrypoint instance. */
public final class HostLanguageAdapter implements LanguageAdapter {
    public static final HostLanguageAdapter INSTANCE = new HostLanguageAdapter();
    private HostLanguageAdapter() {}
    public <T> T create(ModContainer mod, String value, Class<T> type) throws LanguageAdapterException {
        if (!(mod instanceof QuiltModContainer host)) throw new LanguageAdapterException("Only host-backed Quilt containers are supported");
        try {
            return net.fabricmc.loader.api.LanguageAdapter.getDefault().create(host.host(), value, type);
        } catch (net.fabricmc.loader.api.LanguageAdapterException e) {
            throw new LanguageAdapterException(e.getMessage(), e);
        }
    }
}
