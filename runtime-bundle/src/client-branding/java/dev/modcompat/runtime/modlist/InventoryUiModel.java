package dev.modcompat.runtime.modlist;

import java.util.*;
import org.sinytra.connector.infinity.inventory.AdmissionInventory.*;
import org.sinytra.connector.infinity.inventory.InventoryDisplay;
import org.sinytra.connector.infinity.inventory.InventoryDisplay.*;

/** Client presentation state over a final immutable snapshot. No discovery, files or containers. */
public final class InventoryUiModel {
    public static final int MAX_QUERY = 128;
    public enum Sort { LOADED, NAME_ASC, NAME_DESC }
    public record Rect(int x, int y, int width, int height) { }
    public record Layout(Rect search, Rect sort, Rect list, Rect details, int footerY, int buttonWidth) {
        public static Layout of(int width, int height) { return of(width, height, false); }
        public static Layout of(int width, int height, boolean hasExclusions) {
            int margin = 8, usable = Math.max(1, width - 2 * margin), top = 68;
            int content = Math.max(2, height - top - 36);
            int sortWidth = Math.min(92, usable / 3);
            Rect list, details;
            if (width >= 440) {
                int listWidth = Math.min(280, usable * 2 / 5);
                list = new Rect(margin, top, listWidth, content);
                details = new Rect(margin + listWidth + 8, top, Math.max(1, usable - listWidth - 8), content);
            } else {
                int listHeight = Math.max(1, (content - 6) / 2);
                list = new Rect(margin, top, usable, listHeight);
                details = new Rect(margin, top + listHeight + 6, usable, Math.max(1, content - listHeight - 6));
            }
            return new Layout(new Rect(margin, 42, Math.max(1, usable - sortWidth - 6), 20),
                new Rect(width - margin - sortWidth, 42, sortWidth, 20), list, details,
                Math.max(top + content + 6, height - 26), Math.max(1, (usable - (hasExclusions ? 18 : 12)) / (hasExclusions ? 4 : 3)));
        }
    }
    private final Snapshot snapshot;
    private final Projection projection;
    private List<Row> visible;
    private String query = "";
    private Sort sort = Sort.LOADED;
    private Row selected;

    public InventoryUiModel(Snapshot snapshot) {
        this.snapshot = Objects.requireNonNull(snapshot);
        projection = InventoryDisplay.project(snapshot);
        visible = projection.rows();
    }
    public Snapshot snapshot() { return snapshot; }
    public Projection projection() { return projection; }
    public List<Row> rows() { return visible; }
    public String query() { return query; }
    public Sort sort() { return sort; }
    public Row selected() { return selected; }
    public void select(Row row) { selected = row != null && visible.contains(row) ? row : null; }
    /** The caller must reset list/detail scroll when this returns true. */
    public boolean query(String value) {
        String next = plain(value, MAX_QUERY).strip();
        if (next.codePointCount(0, next.length()) > MAX_QUERY) next = next.substring(0, next.offsetByCodePoints(0, MAX_QUERY));
        if (query.equals(next)) return false;
        FilterResult result = InventoryDisplay.filter(projection, query, next);
        query = next;
        if (result.clearSelection()) selected = null;
        visible = sorted(result.rows());
        return result.resetScrollToTop();
    }
    public void nextSort() {
        sort = Sort.values()[(sort.ordinal() + 1) % Sort.values().length];
        visible = sorted(visible);
        if (!visible.contains(selected)) selected = null;
    }
    private List<Row> sorted(List<Row> rows) {
        if (sort == Sort.LOADED) return InventoryDisplay.filter(projection, query, query).rows();
        Comparator<Row> names = Comparator.comparing(row -> plain(row.displayName(), 512).toLowerCase(Locale.ROOT));
        return rows.stream().sorted(sort == Sort.NAME_ASC ? names : names.reversed()).toList();
    }
    public static String version(Entry entry) { return entry.sourceVersion().orElse(entry.loadedVersion()); }
    public static String source(SourceChain chain) {
        return chain.installationRoot() + (chain.embeddedEntries().isEmpty() ? "" : "!/" + String.join("!/", chain.embeddedEntries()));
    }
    /** Metadata is literal text, never JSON chat/URLs/actions. Bound code points and strip controls/formatting. */
    public static String plain(String value, int maxCodePoints) {
        if (value == null) return "";
        StringBuilder result = new StringBuilder();
        int count = 0;
        boolean formatting = false;
        int offset = 0;
        int inputBound = Math.min(value.length(), Math.max(0, maxCodePoints) * 4);
        for (; offset < inputBound && count < maxCodePoints;) {
            int cp = value.codePointAt(offset); offset += Character.charCount(cp);
            if (formatting) { formatting = false; continue; }
            if (cp == 0x00a7) { formatting = true; continue; }
            if (cp == '\r') continue;
            if (cp != '\n' && cp != '\t' && (Character.isISOControl(cp) || Character.getType(cp) == Character.FORMAT)) continue;
            result.appendCodePoint(cp == '\t' ? ' ' : cp); count++;
        }
        if (offset < value.length()) result.append('…');
        return result.toString();
    }
}
