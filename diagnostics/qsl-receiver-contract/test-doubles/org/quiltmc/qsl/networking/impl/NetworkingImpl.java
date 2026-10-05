/* TEST DOUBLE ONLY, self-authored MIT; no Minecraft or QSL ABI claim. */
package org.quiltmc.qsl.networking.impl;
import net.minecraft.class_8710;
public final class NetworkingImpl {
    public static boolean isReservedCommonChannel(class_8710.class_9154<?> id) {
        return id.toString().equals("minecraft:register") || id.toString().equals("minecraft:unregister");
    }
}
