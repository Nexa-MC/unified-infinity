package dev.modcompat.runtime.branding.mixin;

import dev.modcompat.runtime.branding.BrandingText;
import java.util.function.BiConsumer;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.components.PlainTextButton;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.network.chat.Component;
import org.sinytra.connector.infinity.inventory.AdmissionInventory.Counts;
import org.sinytra.connector.infinity.inventory.AdmissionInventory.Snapshot;
import org.sinytra.connector.infinity.inventory.AdmissionSession;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyArg;

/** Changes only the title screen's supplied text, never global BrandingControl metadata. */
@Mixin(value = TitleScreen.class, remap = false)
abstract class TitleScreenBrandingMixin {
    // Pinned 1.21.1 field, verified as private static final Component in the exact prepared client.
    @Shadow @Final private static Component COPYRIGHT_TEXT;
    @ModifyArg(method = "render", at = @At(value = "INVOKE",
            target = "Lnet/neoforged/neoforge/internal/BrandingControl;forEachLine(ZZLjava/util/function/BiConsumer;)V", remap = false),
            index = 2, require = 1, remap = false)
    private BiConsumer<Integer, String> infinity$brandMenu(BiConsumer<Integer, String> original) {
        // One immutable successful snapshot per render; no scan or count inferred from other loader views.
        Counts counts = AdmissionSession.isInstalled()
            ? AdmissionSession.current().selectedSnapshot().map(Snapshot::counts).orElse(null) : null;
        TitleScreen screen = (TitleScreen) (Object) this;
        var font = Minecraft.getInstance().font;
        // Vanilla init positions its real copyright PlainTextButton at width - measured text - 2.
        // Include a 6px gap after our x=2 footer; also honor a moved actual footer widget.
        int available = Math.max(0, screen.width - font.width(COPYRIGHT_TEXT) - 10);
        for (var child : screen.children()) {
            if (child instanceof PlainTextButton button && button.getY() + button.getHeight() >= screen.height - 2)
                available = Math.min(available, Math.max(0, button.getX() - 8));
        }
        final int budget = available;
        return (line, text) -> original.accept(line, BrandingText.titleScreenLine(text, counts,
            userMods -> Component.translatable("unified_infinity.branding.menu_user_count", userMods).getString(),
            budget, font::width));
    }
}
