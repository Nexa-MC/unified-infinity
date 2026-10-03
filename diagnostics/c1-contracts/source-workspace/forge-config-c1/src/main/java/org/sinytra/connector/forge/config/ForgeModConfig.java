/* SPDX-License-Identifier: LGPL-2.1-only */
package org.sinytra.connector.forge.config;

/** Stable Forge identity around the single tracked native record. No raw-data API is admitted. */
public final class ForgeModConfig {
    private final net.neoforged.fml.config.ModConfig owner;
    private final ForgeConfigSpec spec;

    ForgeModConfig(net.neoforged.fml.config.ModConfig owner, ForgeConfigSpec spec) {
        this.owner = owner;
        this.spec = spec;
    }

    public Type getType() { return Type.COMMON; }
    public String getFileName() { return owner.getFileName(); }
    public String getModId() { return owner.getModId(); }
    public IForgeConfigSpec<?> getSpec() { return spec; }

    // Only COMMON's field is proposed for C1 admission. Other enum APIs remain closed.
    public enum Type { COMMON, CLIENT, SERVER }
}
