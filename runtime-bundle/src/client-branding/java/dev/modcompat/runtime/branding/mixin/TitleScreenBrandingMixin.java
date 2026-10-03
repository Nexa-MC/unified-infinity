package dev.modcompat.runtime.branding.mixin;

import dev.modcompat.runtime.branding.BrandingText;
import java.util.function.BiConsumer;
import net.minecraft.client.gui.screens.TitleScreen;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyArg;

/** Changes only the title screen's supplied text, never global BrandingControl metadata. */
@Mixin(value = TitleScreen.class, remap = false)
abstract class TitleScreenBrandingMixin {
    @ModifyArg(method = "render", at = @At(value = "INVOKE",
            target = "Lnet/neoforged/neoforge/internal/BrandingControl;forEachLine(ZZLjava/util/function/BiConsumer;)V", remap = false),
            index = 2, require = 1, remap = false)
    private BiConsumer<Integer, String> infinity$brandMenu(BiConsumer<Integer, String> original) {
        return (line, text) -> original.accept(line, BrandingText.titleScreenLine(text));
    }
}
