package org.sinytra.connector.infinity;

/** One bounded budget for the existing independent JAR-transform stage only. */
public record LoadingPolicy(int workers, int cpuBudget, int heapBudget, int configuredCap) {
    public static final String WORKERS_PROPERTY = "unified.infinity.workers";
    public static final String MAX_WORKERS_PROPERTY = "unified.infinity.maxWorkers";
    private static final long MIB = 1024L * 1024L;

    public static LoadingPolicy current(int inputs) {
        return compute(inputs, Runtime.getRuntime().availableProcessors(), Runtime.getRuntime().maxMemory(),
            positiveProperty(MAX_WORKERS_PROPERTY, 4), positiveProperty(WORKERS_PROPERTY, Integer.MAX_VALUE));
    }

    public static LoadingPolicy compute(int inputs, int cpus, long maxHeap, int maxWorkers, int requestedWorkers) {
        if (inputs < 0 || maxWorkers < 1 || requestedWorkers < 1) {
            throw new IllegalArgumentException("Invalid transform worker budget");
        }
        int cpuBudget = Math.max(1, cpus - 1);
        // Conservative admission heuristic, not a reservation or an RSS guarantee.
        int heapBudget = (int) Math.min(Integer.MAX_VALUE, Math.max(1L, (maxHeap - 512L * MIB) / (256L * MIB)));
        int cap = Math.min(maxWorkers, requestedWorkers);
        int workers = inputs == 0 ? 0 : Math.max(1, Math.min(inputs, Math.min(cap, Math.min(cpuBudget, heapBudget))));
        return new LoadingPolicy(workers, cpuBudget, heapBudget, cap);
    }

    private static int positiveProperty(String name, int fallback) {
        String value = System.getProperty(name);
        if (value == null) return fallback;
        try {
            int parsed = Integer.parseInt(value);
            if (parsed > 0) return parsed;
        } catch (NumberFormatException ignored) {
        }
        throw new IllegalArgumentException(name + " must be a positive integer");
    }
}
