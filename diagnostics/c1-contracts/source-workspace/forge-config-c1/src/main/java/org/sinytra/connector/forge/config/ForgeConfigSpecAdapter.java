/* SPDX-License-Identifier: LGPL-2.1-only */
package org.sinytra.connector.forge.config;

import com.electronwill.nightconfig.core.CommentedConfig;
import com.electronwill.nightconfig.core.UnmodifiableCommentedConfig;
import com.electronwill.nightconfig.core.UnmodifiableConfig;
import java.util.Objects;
import net.neoforged.fml.ModContainer;
import net.neoforged.fml.config.ConfigRegistrationPolicy;
import net.neoforged.fml.config.ConfigTracker;
import net.neoforged.fml.config.IConfigSpec;
import net.neoforged.fml.config.ModConfig;
import net.neoforged.fml.event.config.ModConfigEvent;

/** Composition is required: Forge correct(CommentedConfig) returns int, native returns void. */
public final class ForgeConfigSpecAdapter implements IConfigSpec, ConfigRegistrationPolicy {
    private final ForgeConfigSpec spec;
    private ModConfig owner;
    private ForgeModConfig facade;

    public ForgeConfigSpecAdapter(IForgeConfigSpec<?> spec) {
        Objects.requireNonNull(spec, "spec");
        if (spec.getClass() != ForgeConfigSpec.class) {
            throw new UnsupportedOperationException("C1 requires exact ForgeConfigSpec; custom specs/subclasses are unsupported");
        }
        this.spec = (ForgeConfigSpec) spec;
    }

    public static void register(ConfigTracker tracker, ModContainer container, ForgeModConfig.Type type,
                                IForgeConfigSpec<?> spec, String fileName) {
        if (type != ForgeModConfig.Type.COMMON) throw new UnsupportedOperationException("C1 supports COMMON only: " + type);
        var adapter = new ForgeConfigSpecAdapter(spec);
        if (adapter.isEmpty()) return;
        if (fileName == null) tracker.registerConfig(ModConfig.Type.COMMON, adapter, container);
        else tracker.registerConfig(ModConfig.Type.COMMON, adapter, container, fileName);
    }

    @Override public boolean isEmpty() { return spec.isEmpty(); }
    @Override public void validateSpec(ModConfig config) {
        if (config.getType() != ModConfig.Type.COMMON || owner != null) {
            throw new UnsupportedOperationException("C1 adapter binds to one COMMON owner");
        }
        owner = config;
        facade = new ForgeModConfig(config, spec);
    }
    @Override public boolean isCorrect(UnmodifiableCommentedConfig config) {
        // Native can provide an immutable view. Never downcast it to a mutable config.
        return spec.isCorrect(copy(config));
    }
    private static CommentedConfig copy(UnmodifiableConfig source) {
        var result = CommentedConfig.inMemory();
        for (var entry : source.entrySet()) {
            Object value = entry.getValue();
            result.set(java.util.List.of(entry.getKey()), value instanceof UnmodifiableConfig nested ? copy(nested) : value);
            if (source instanceof UnmodifiableCommentedConfig commented) {
                result.setComment(java.util.List.of(entry.getKey()), commented.getComment(java.util.List.of(entry.getKey())));
            }
        }
        return result;
    }
    @Override public void correct(CommentedConfig config) { spec.correct(config); }
    @Override public void acceptConfig(ILoadedConfig loaded) {
        if (loaded == null) spec.attachOwner(null, null, null);
        else spec.attachOwner(loaded.config(), loaded::save,
            (mutation, successfulCommit) -> ConfigRegistrationPolicy.mutateAndSave(owner, mutation, successfulCommit));
    }
    @Override public boolean recoverReadFailure() { return false; }
    @Override public boolean backupOnCorrection(boolean initialLoad) { return !initialLoad; }
    @Override public boolean validateCreatedFile() { return true; }
    @Override public boolean notifyAfterSave() { return false; }
    @Override public boolean saveAfterInitialLoad() { return true; }
    @Override public void dispatchEvent(ModConfig config, ModContainer container, ModConfigEvent event) {
        if (config != owner) throw new IllegalStateException("Wrong config owner");
        if (event instanceof ModConfigEvent.Loading) container.acceptEvent(new ForgeModConfigEvent.Loading(facade));
        else if (event instanceof ModConfigEvent.Reloading) container.acceptEvent(new ForgeModConfigEvent.Reloading(facade));
        // COMMON has no public unload lifecycle in C1. Owner disposal only detaches state.
    }
}
