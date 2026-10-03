/* Unified Infinity internal source-fusion contract. SPDX-License-Identifier: LGPL-2.1-only */
package net.neoforged.fml.loading.unified;

import net.neoforged.api.distmarker.Dist;
import net.neoforged.bus.api.IEventBus;
import org.jetbrains.annotations.ApiStatus;

/** GAME-only implementation initialized explicitly by FML, without an ordinary @Mod constructor. */
@ApiStatus.Internal
public interface GameCompatibilityComponent {
    enum LifecyclePhase { COMMON_SETUP, CLIENT_SETUP, DEDICATED_SERVER_SETUP, ENQUEUE_IMC, PROCESS_IMC, LOAD_COMPLETE }
    void initialize(IEventBus internalBus, Dist dist);
    default void onLifecycle(LifecyclePhase phase) {}
}
