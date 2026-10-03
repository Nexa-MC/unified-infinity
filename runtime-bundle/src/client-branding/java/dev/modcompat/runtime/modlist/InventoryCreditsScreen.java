package dev.modcompat.runtime.modlist;

import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

/** Full attribution is a separate copyright view; it is not a list of additional loaded providers. */
final class InventoryCreditsScreen extends Screen {
    private final Screen parent;
    private final InventoryUiModel model;
    InventoryCreditsScreen(Screen parent, InventoryUiModel model) {
        super(InventoryDetails.tr("credits_title")); this.parent = parent; this.model = model;
    }
    @Override protected void init() {
        InventoryTextPanel panel = addRenderableWidget(new InventoryTextPanel(minecraft, font,
            new InventoryUiModel.Rect(8, 30, Math.max(1, width - 16), Math.max(1, height - 66))));
        panel.content(InventoryDetails.credits(model));
        int buttonWidth = Math.min(200, Math.max(1, width - 16));
        addRenderableWidget(Button.builder(Component.translatable("gui.back"), b -> onClose())
            .bounds((width - buttonWidth) / 2, height - 26, buttonWidth, 20).build());
    }
    @Override public void render(GuiGraphics graphics, int mouseX, int mouseY, float partialTick) {
        super.render(graphics, mouseX, mouseY, partialTick);
        graphics.drawCenteredString(font, title, width / 2, 10, 0xFFFFFFFF);
    }
    @Override public void onClose() { minecraft.setScreen(parent); }
}
