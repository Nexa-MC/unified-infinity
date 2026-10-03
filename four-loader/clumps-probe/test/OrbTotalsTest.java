package dev.infinity.clumpsprobe;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** Pure-Java arithmetic controls. Does not load Minecraft or establish mixin behavior. */
public final class OrbTotalsTest {
    private static final Map<Integer, Integer> EXPECTED = Map.of(1, 1, 3, 1, 7, 2, 17, 1, 37, 1);
    private static int assertions;

    public static void main(String[] args) {
        OrbTotals initial = OrbTotals.from(List.of(Map.of(1, 1), Map.of(3, 1), Map.of(7, 1),
                Map.of(7, 1), Map.of(17, 1), Map.of(37, 1)));
        check(initial.entities() == 6 && initial.units() == 6 && initial.xp() == 72, "initial counts");
        check(initial.histogram().equals(EXPECTED), "initial histogram");
        OrbTotals merged = OrbTotals.from(List.of(EXPECTED));
        check(merged.entities() == 1 && merged.units() == 6 && merged.xp() == 72, "merged weighted counts");
        check(merged.histogram().equals(initial.histogram()), "merge conservation");
        check(OrbTotals.from(List.of(Map.of(1, 1), Map.of(3, 1), Map.of(7, 2),
                Map.of(17, 1), Map.of(37, 1))).entities() == 5, "partial merge remains five entities");
        OrbTotals wrongDistribution = OrbTotals.from(List.of(Map.of(12, 6)));
        check(wrongDistribution.xp() == 72 && wrongDistribution.units() == 6
                && !wrongDistribution.histogram().equals(EXPECTED), "same XP and count cannot conceal wrong values");
        check(OrbTotals.from(List.of(Map.of(7, 1))).xp() != 72, "lost XP rejected by expected total");
        check(OrbTotals.from(List.of(EXPECTED, EXPECTED)).xp() == 144, "duplicated XP detected");
        check(OrbTotals.from(List.of()).entities() == 0, "lost entities visible to caller");
        bad(() -> OrbTotals.from(List.of(Map.of())), IllegalArgumentException.class);
        bad(() -> OrbTotals.from(List.of(Map.of(0, 1))), IllegalArgumentException.class);
        bad(() -> OrbTotals.from(List.of(Map.of(7, 0))), IllegalArgumentException.class);
        bad(() -> OrbTotals.from(List.of(Map.of(7, -1))), IllegalArgumentException.class);
        Map<Integer, Integer> nullValue = new HashMap<>();
        nullValue.put(7, null);
        bad(() -> OrbTotals.from(List.of(nullValue)), IllegalArgumentException.class);
        Map<Integer, Integer> nullKey = new HashMap<>();
        nullKey.put(null, 1);
        bad(() -> OrbTotals.from(List.of(nullKey)), IllegalArgumentException.class);
        int max = Integer.MAX_VALUE;
        check(OrbTotals.from(List.of(Map.of(max, max))).xp() == (long) max * max, "long multiplication");
        bad(() -> OrbTotals.from(List.of(Map.of(1, max), Map.of(1, 1))), ArithmeticException.class);
        bad(() -> OrbTotals.from(List.of(Map.of(max, max, max - 1, max, max - 2, max))), ArithmeticException.class);
        Map<Integer, Integer> mutable = new HashMap<>(EXPECTED);
        OrbTotals copied = OrbTotals.from(List.of(mutable));
        mutable.put(7, 99);
        check(copied.histogram().equals(EXPECTED), "snapshot detached from source");
        bad(() -> copied.histogram().put(7, 99), UnsupportedOperationException.class);
        System.out.println("ORB_TOTALS_UNIT_TEST PASS assertions=" + assertions + " minecraft_loaded=false");
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
        assertions++;
    }

    private static void bad(Runnable action, Class<? extends RuntimeException> expected) {
        try {
            action.run();
        } catch (RuntimeException exception) {
            check(expected.isInstance(exception), "unexpected exception: " + exception);
            return;
        }
        throw new AssertionError("Expected " + expected.getName());
    }
}
