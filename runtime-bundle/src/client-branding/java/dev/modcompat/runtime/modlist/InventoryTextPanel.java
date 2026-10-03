package dev.modcompat.runtime.modlist;

import com.mojang.blaze3d.vertex.Tesselator;
import java.util.*;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.client.gui.ComponentPath;
import net.minecraft.client.gui.navigation.FocusNavigationEvent;
import net.minecraft.client.gui.navigation.ScreenRectangle;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.narration.NarrationElementOutput;
import net.minecraft.client.gui.narration.NarratedElementType;
import net.minecraft.network.chat.Component;
import net.minecraft.util.FormattedCharSequence;
import net.neoforged.neoforge.client.gui.widget.ScrollPanel;
import org.lwjgl.glfw.GLFW;

/** Literal, wrapped, bounded detail/credit text with wheel, scrollbar and keyboard scrolling. */
final class InventoryTextPanel extends ScrollPanel {
    private final Font font;
    private List<FormattedCharSequence> lines = List.of();
    private Component narration = Component.empty();
    private boolean focused;

    InventoryTextPanel(Minecraft minecraft, Font font, InventoryUiModel.Rect rect) {
        super(minecraft, rect.width(), rect.height(), rect.y(), rect.x());
        this.font = font;
    }
    void content(List<Component> paragraphs) {
        List<FormattedCharSequence> wrapped = new ArrayList<>();
        for (Component paragraph : paragraphs) {
            // Only components constructed from local translations and literal sanitized metadata reach here.
            wrapped.addAll(font.split(paragraph, Math.max(1, width - 18)));
            wrapped.add(FormattedCharSequence.EMPTY);
        }
        lines = List.copyOf(wrapped);
        StringBuilder spoken = new StringBuilder();
        for (Component paragraph : paragraphs) {
            if (spoken.length() >= 16384) break;
            spoken.append(InventoryUiModel.plain(paragraph.getString(), 16384 - spoken.length())).append('\n');
        }
        narration = Component.literal(spoken.toString());
        scrollDistance = 0;
    }
    @Override protected int getContentHeight() { return Math.max(height - border, lines.size() * font.lineHeight + 8); }
    @Override protected int getScrollAmount() { return font.lineHeight * 3; }
    @Override protected void drawPanel(GuiGraphics graphics, int right, int y, Tesselator tessellator, int mouseX, int mouseY) {
        int first = Math.max(0, (top - y) / font.lineHeight);
        int last = Math.min(lines.size(), first + height / font.lineHeight + 3);
        for (int i = first; i < last; i++) graphics.drawString(font, lines.get(i), left + 5, y + i * font.lineHeight, 0xFFE2E8F0, false);
    }
    @Override public boolean mouseScrolled(double x, double y, double horizontal, double vertical) {
        return isMouseOver(x, y) && super.mouseScrolled(x, y, horizontal, vertical);
    }
    @Override public boolean keyPressed(int key, int scan, int modifiers) {
        if (!focused) return false;
        float next = switch (key) {
            case GLFW.GLFW_KEY_DOWN -> scrollDistance + getScrollAmount();
            case GLFW.GLFW_KEY_UP -> scrollDistance - getScrollAmount();
            case GLFW.GLFW_KEY_PAGE_DOWN -> scrollDistance + height - font.lineHeight;
            case GLFW.GLFW_KEY_PAGE_UP -> scrollDistance - height + font.lineHeight;
            case GLFW.GLFW_KEY_HOME -> 0;
            case GLFW.GLFW_KEY_END -> getContentHeight();
            default -> Float.NaN;
        };
        if (Float.isNaN(next)) return false;
        scrollDistance = Math.max(0, Math.min(next, getContentHeight() - height + border));
        return true;
    }
    @Override public boolean mouseClicked(double x, double y, int button) {
        if (!isMouseOver(x, y)) return false;
        boolean handled = super.mouseClicked(x, y, button);
        if (button == 0) { setFocused(true); return true; }
        return handled;
    }
    @Override public ComponentPath nextFocusPath(FocusNavigationEvent event) {
        return focused ? null : ComponentPath.leaf(this);
    }
    @Override public ScreenRectangle getRectangle() { return new ScreenRectangle(left, top, width, height); }
    @Override public void setFocused(boolean focused) { this.focused = focused; }
    @Override public boolean isFocused() { return focused; }
    @Override public NarrationPriority narrationPriority() { return focused ? NarrationPriority.FOCUSED : NarrationPriority.NONE; }
    @Override public void updateNarration(NarrationElementOutput output) { output.add(NarratedElementType.TITLE, narration); }
}
