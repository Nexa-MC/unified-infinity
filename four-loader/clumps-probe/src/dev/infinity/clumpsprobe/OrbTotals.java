package dev.infinity.clumpsprobe;

import java.util.Collection;
import java.util.Map;
import java.util.TreeMap;

/** Pure arithmetic used by the real entity probe; never manufactures entity state. */
record OrbTotals(int entities, long units, long xp, Map<Integer, Integer> histogram) {
    static OrbTotals from(Collection<? extends Map<Integer, Integer>> maps) {
        long units = 0;
        long xp = 0;
        Map<Integer, Integer> histogram = new TreeMap<>();
        for (Map<Integer, Integer> map : maps) {
            if (map == null || map.isEmpty()) throw new IllegalArgumentException("empty_clumped_map");
            for (Map.Entry<Integer, Integer> entry : map.entrySet()) {
                Integer value = entry.getKey();
                Integer count = entry.getValue();
                if (value == null || count == null || value <= 0 || count <= 0) {
                    throw new IllegalArgumentException("nonpositive_clumped_entry");
                }
                units = Math.addExact(units, count.longValue());
                xp = Math.addExact(xp, Math.multiplyExact(value.longValue(), count.longValue()));
                histogram.merge(value, count, Math::addExact);
            }
        }
        return new OrbTotals(maps.size(), units, xp, Map.copyOf(histogram));
    }
}
