package dev.infinity.quilttooltipprobe;

import net.minecraft.class_2561;
import net.minecraft.class_5684;
import org.quiltmc.loader.api.minecraft.ClientOnly;
import org.quiltmc.qsl.tooltip.api.ConvertibleTooltipData;

/** Common-side data: the implementing method must be stripped on dedicated servers. */
public final class CommonTooltipData implements ConvertibleTooltipData {
    public final String label;
    public final boolean returnNull;
    public int conversions;

    public CommonTooltipData(String label, boolean returnNull) {
        this.label = label;
        this.returnNull = returnNull;
    }

    @Override
    @ClientOnly
    public class_5684 toComponent() {
        conversions++;
        return returnNull ? null : class_5684.method_32662(class_2561.method_43470(label).method_30937());
    }
}
