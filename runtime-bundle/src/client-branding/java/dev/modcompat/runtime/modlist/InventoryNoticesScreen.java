package dev.modcompat.runtime.modlist;

import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import org.sinytra.connector.infinity.inventory.AdmissionInventory.Snapshot;

/** Read-only evidence from the same frozen admission snapshot, not a second policy or provider list. */
final class InventoryNoticesScreen extends Screen {
    private final Screen parent;
    private final Snapshot snapshot;
    InventoryNoticesScreen(Screen parent, Snapshot snapshot) {
        super(InventoryDetails.tr("exclusions_title")); this.parent = parent; this.snapshot = snapshot;
    }
    @Override protected void init() {
        InventoryTextPanel panel = addRenderableWidget(new InventoryTextPanel(minecraft, font,
            new InventoryUiModel.Rect(8, 30, Math.max(1, width - 16), Math.max(1, height - 66))));
        panel.content(InventoryDetails.exclusions(snapshot));
        int buttonWidth = Math.min(200, Math.max(1, width - 16));
        addRenderableWidget(Button.builder(Component.translatable("gui.back"), b -> onClose())
            .bounds((width - buttonWidth) / 2, height - 26, buttonWidth, 20).build());
    }
    @Override public void render(GuiGraphics graphics, int mouseX, int mouseY, float partialTick) {
        super.render(graphics, mouseX, mouseY, partialTick);
        graphics.drawCenteredString(font, font.plainSubstrByWidth(title.getString(), Math.max(1, width - 16)), width / 2, 10, 0xFFFFD580);
    }
    @Override public void onClose() { minecraft.setScreen(parent); }
}
