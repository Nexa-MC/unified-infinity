/* TEST DOUBLE ONLY, self-authored MIT; no Minecraft or QSL ABI claim. */
package org.quiltmc.qsl.networking.impl;
import net.minecraft.class_2539;
import net.minecraft.class_2598;
import net.minecraft.class_8710;
/** The fixture toggles lookup presence; it neither registers nor decodes codecs. */
public final class PayloadTypeRegistryImpl<T> {
    public boolean available = true;
    public int lookups;
    public class_2539 getPhase() { return class_2539.PLAY; }
    public class_2598 getSide() { return class_2598.SERVERBOUND; }
    public Object get(class_8710.class_9154<?> id) { lookups++; return available ? this : null; }
}
