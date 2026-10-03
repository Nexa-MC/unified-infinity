/* SPDX-License-Identifier: LGPL-2.1-only */
package org.sinytra.connector.forge.config;

import net.neoforged.bus.api.Event;
import net.neoforged.fml.event.IModBusEvent;

/** Events selected by the native owner before dispatch; never relayed from a native listener. */
public class ForgeModConfigEvent extends Event implements IModBusEvent {
    private final ForgeModConfig config;
    ForgeModConfigEvent(ForgeModConfig config) { this.config = config; }
    public ForgeModConfig getConfig() { return config; }
    public static final class Loading extends ForgeModConfigEvent {
        public Loading(ForgeModConfig config) { super(config); }
    }
    public static final class Reloading extends ForgeModConfigEvent {
        public Reloading(ForgeModConfig config) { super(config); }
    }
}
