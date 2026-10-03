package dev.modcompat.runtime.modlist;

import java.util.*;
import net.minecraft.ChatFormatting;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.components.ObjectSelectionList;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import net.neoforged.fml.ModContainer;
import net.neoforged.fml.ModList;
import net.neoforged.neoforge.client.gui.IConfigScreenFactory;
import org.lwjgl.glfw.GLFW;
import org.sinytra.connector.infinity.inventory.AdmissionInventory.Snapshot;
import org.sinytra.connector.infinity.inventory.InventoryDisplay.*;
import static dev.modcompat.runtime.modlist.InventoryDetails.*;

/** The built-in Mods destination. UI aggregate rows never become providers or ModContainers. */
public final class UnifiedModListScreen extends Screen {
    private final Screen parent;
    private final InventoryUiModel model;
    private ModRows list;
    private InventoryTextPanel details;
    private EditBox search;
    private Button config;

    public UnifiedModListScreen(Screen parent, Optional<Snapshot> snapshot) {
        super(tr("title"));
        this.parent = parent;
        this.model = snapshot.map(InventoryUiModel::new).orElse(null);
    }
    @Override protected void init() {
        boolean hasExclusions = model != null && !model.snapshot().exclusions().isEmpty();
        InventoryUiModel.Layout layout = InventoryUiModel.Layout.of(width, height, hasExclusions);
        double previousScroll = list == null ? 0 : list.getScrollAmount();
        details = addRenderableWidget(new InventoryTextPanel(minecraft, font, layout.details()));
        list = addRenderableWidget(new ModRows(layout.list()));
        var searchBounds = layout.search();
        search = addRenderableWidget(new EditBox(font, searchBounds.x(), searchBounds.y(), searchBounds.width(), searchBounds.height(), tr("search")));
        search.setMaxLength(InventoryUiModel.MAX_QUERY);
        search.setHint(tr("search"));
        search.setValue(model == null ? "" : model.query());
        search.setResponder(value -> {
            if (model != null && model.query(value)) {
                list.reload();
                list.setScrollAmount(0);
                updateDetails();
            }
        });
        var sortBounds = layout.sort();
        Button sort = addRenderableWidget(Button.builder(sortText(), button -> {
            model.nextSort();
            button.setMessage(sortText());
            list.reload();
            list.setScrollAmount(0);
            list.revealSelection();
        }).bounds(sortBounds.x(), sortBounds.y(), sortBounds.width(), sortBounds.height()).build());
        int buttonWidth = layout.buttonWidth(), y = layout.footerY();
        config = addRenderableWidget(Button.builder(tr("config"), button -> openConfig()).bounds(8, y, buttonWidth, 20).build());
        Button credits = addRenderableWidget(Button.builder(tr("credits_button"), button -> minecraft.setScreen(new InventoryCreditsScreen(this, model)))
            .bounds(14 + buttonWidth, y, buttonWidth, 20).build());
        if (hasExclusions) addRenderableWidget(Button.builder(
                tr("exclusions_button", model.snapshot().exclusions().size()).copy().withStyle(ChatFormatting.YELLOW),
                button -> minecraft.setScreen(new InventoryNoticesScreen(this, model.snapshot())))
            .bounds(20 + buttonWidth * 2, y, buttonWidth, 20).build());
        addRenderableWidget(Button.builder(Component.translatable("gui.done"), button -> onClose())
            .bounds(width - 8 - buttonWidth, y, buttonWidth, 20).build());
        search.active = sort.active = credits.active = model != null;
        list.reload();
        list.setClampedScrollAmount(previousScroll);
        updateDetails();
    }
    private Component sortText() { return tr("sort." + (model == null ? "loaded" : model.sort().name().toLowerCase(Locale.ROOT))); }
    private void updateDetails() {
        config.active = selectedContainer().flatMap(container -> IConfigScreenFactory.getForMod(container.getModInfo())).isPresent();
        if (model == null) details.content(List.of(tr("unavailable")));
        else if (model.selected() == null && !model.snapshot().exclusions().isEmpty()) details.content(List.of(
            tr("exclusions_intro", model.snapshot().exclusions().size()), tr("exclusions_unchanged"),
            tr("exclusions_open_details"), tr("select")));
        else details.content(InventoryDetails.selected(model.selected()));
    }
    private Optional<? extends ModContainer> selectedContainer() {
        if (model == null || !(model.selected() instanceof ModRow row)) return Optional.empty();
        return ModList.get().getModContainerById(row.entry().canonicalId());
    }
    private void openConfig() {
        selectedContainer().ifPresent(container -> IConfigScreenFactory.getForMod(container.getModInfo()).ifPresent(factory -> {
            try {
                Screen target = factory.createScreen(container, this);
                if (target != null) minecraft.setScreen(target);
            } catch (RuntimeException error) {
                System.getLogger(UnifiedModListScreen.class.getName()).log(System.Logger.Level.ERROR,
                    "Native config screen failed for " + container.getModId(), error);
                List<Component> lines = new ArrayList<>(InventoryDetails.selected(model.selected()));
                lines.add(tr("config_error"));
                details.content(lines);
            }
        }));
    }
    @Override public void render(GuiGraphics graphics, int mouseX, int mouseY, float partialTick) {
        super.render(graphics, mouseX, mouseY, partialTick);
        graphics.drawCenteredString(font, title, width / 2, 8, 0xFFFFFFFF);
        Component counts = model == null ? tr("unavailable_short") : tr("counts", model.projection().counts().userMods(),
            model.projection().counts().loadedLogicalMods(), model.projection().counts().collapsedApiModules(), model.rows().size());
        graphics.drawString(font, font.plainSubstrByWidth(counts.getString(), Math.max(1, width - 16)), 8, 26, 0xFFCBD5E1, false);
        if (model != null && model.rows().isEmpty()) graphics.drawString(font, tr("no_results"), list.getX() + 6, list.getY() + 8, 0xFFCBD5E1, false);
    }
    @Override public boolean keyPressed(int key, int scanCode, int modifiers) {
        if (key == GLFW.GLFW_KEY_F && hasControlDown() && search.active) {
            setFocused(search); search.setFocused(true); return true;
        }
        if (key == GLFW.GLFW_KEY_DOWN && search.isFocused() && !list.children().isEmpty()) {
            search.setFocused(false); setFocused(list); list.choose(0); return true;
        }
        return super.keyPressed(key, scanCode, modifiers);
    }
    @Override public void onClose() { minecraft.setScreen(parent); }

    private final class ModRows extends ObjectSelectionList<ModRows.Item> {
        private boolean refreshing;
        ModRows(InventoryUiModel.Rect rect) {
            super(UnifiedModListScreen.this.minecraft, rect.width(), rect.height(), rect.y(), UnifiedModListScreen.this.font.lineHeight * 3 + 8);
            setX(rect.x());
        }
        @Override public int getRowWidth() { return Math.max(1, getWidth() - 12); }
        @Override protected int getScrollbarPosition() { return getRight() - 6; }
        void reload() {
            Row selected = model == null ? null : model.selected();
            refreshing = true;
            clearEntries();
            if (model == null) { refreshing = false; return; }
            for (Row row : model.rows()) {
                Item item = new Item(row); addEntry(item);
                if (row.equals(selected)) super.setSelected(item);
            }
            if (selected == null) super.setSelected(null);
            refreshing = false;
            model.select(selected);
            clampScrollAmount();
        }
        void revealSelection() { if (getSelected() != null) ensureVisible(getSelected()); }
        void choose(int index) {
            if (children().isEmpty()) return;
            Item item = children().get(Math.max(0, Math.min(index, children().size() - 1)));
            setSelected(item); ensureVisible(item);
        }
        @Override public void setSelected(Item item) {
            super.setSelected(item);
            if (refreshing) return;
            if (model != null) model.select(item == null ? null : item.row);
            if (config != null) updateDetails();
        }
        @Override public boolean keyPressed(int key, int scanCode, int modifiers) {
            int index = children().indexOf(getSelected());
            int page = Math.max(1, getHeight() / itemHeight);
            int next = switch (key) {
                case GLFW.GLFW_KEY_DOWN -> index + 1;
                case GLFW.GLFW_KEY_UP -> Math.max(0, index - 1);
                case GLFW.GLFW_KEY_HOME -> 0;
                case GLFW.GLFW_KEY_END -> children().size() - 1;
                case GLFW.GLFW_KEY_PAGE_DOWN -> index + page;
                case GLFW.GLFW_KEY_PAGE_UP -> Math.max(0, index - page);
                default -> Integer.MIN_VALUE;
            };
            if (next == Integer.MIN_VALUE) return super.keyPressed(key, scanCode, modifiers);
            choose(next); return true;
        }
        final class Item extends ObjectSelectionList.Entry<Item> {
            private final Row row;
            Item(Row row) { this.row = row; }
            @Override public Component getNarration() { return literal(row.displayName() + ", " + row.compatibilityType()); }
            @Override public void render(GuiGraphics graphics, int index, int top, int left, int entryWidth, int entryHeight,
                                         int mouseX, int mouseY, boolean hovered, float partialTick) {
                int available = Math.max(1, entryWidth - 8);
                String subtitle = row instanceof ModRow mod ? mod.entry().canonicalId() + " · " + InventoryUiModel.version(mod.entry())
                    : tr("api_modules", ((ApiSummaryRow) row).logicalModuleCount()).getString();
                draw(graphics, row.displayName(), left + 3, top + 2, available, 0xFFFFFFFF);
                draw(graphics, subtitle, left + 3, top + 2 + font.lineHeight, available, 0xFFADBACE);
                draw(graphics, row.compatibilityType(), left + 3, top + 2 + font.lineHeight * 2, available, 0xFF7DD3FC);
            }
            private void draw(GuiGraphics graphics, String text, int x, int y, int available, int color) {
                graphics.drawString(font, font.plainSubstrByWidth(InventoryUiModel.plain(text, 1024), available), x, y, color, false);
            }
            @Override public boolean mouseClicked(double x, double y, int button) {
                if (button != 0) return false;
                ModRows.this.setSelected(this); return true;
            }
            @Override public void setFocused(boolean focused) { if (focused) ModRows.this.setSelected(this); }
            @Override public boolean isFocused() { return ModRows.this.getSelected() == this; }
        }
    }
}
