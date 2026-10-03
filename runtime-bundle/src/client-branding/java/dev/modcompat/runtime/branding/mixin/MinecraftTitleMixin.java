package dev.modcompat.runtime.branding.mixin;

import dev.modcompat.runtime.branding.BrandingText;
import net.minecraft.client.Minecraft;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** Window presentation only; does not alter networking or upstream mod identity. */
@Mixin(value = Minecraft.class, remap = false)
abstract class MinecraftTitleMixin {
    @Inject(method = "createTitle", at = @At("RETURN"), cancellable = true, require = 1, remap = false)
    private void infinity$brandWindow(CallbackInfoReturnable<String> result) {
        result.setReturnValue(BrandingText.windowTitle(result.getReturnValue()));
    }
}
