package dev.modcompat.preload;

/** A source-stage observation; deliberately contains no global-percent field. */
public record ProgressSnapshot(String stage, String status, Long completed, Long total,
                               long elapsedMs, long sequence, String error) {
    public static final ProgressSnapshot WAITING = new ProgressSnapshot("waiting", "running", null, null, 0, -1, null);
    public ProgressSnapshot {
        if (stage == null || status == null || elapsedMs < 0 || sequence < -1)
            throw new IllegalArgumentException("Invalid progress envelope");
        if (!java.util.Set.of("waiting", "discover", "resolve", "transform", "commit").contains(stage)
                || !java.util.Set.of("running", "complete", "failed").contains(status))
            throw new IllegalArgumentException("Unknown stage or status");
        if ((completed != null && completed < 0) || (total != null && total < 0)
                || (completed != null && total != null && completed > total))
            throw new IllegalArgumentException("Invalid progress counts");
    }
    public boolean determinate() { return completed != null && total != null && total > 0; }
    public double fraction() { return determinate() ? (double) completed / total : 0; }
    public String heading() {
        return switch (stage) {
            case "discover" -> "Discovering mod archives";
            case "resolve" -> "Resolving dependencies";
            case "transform" -> "Preparing compatible bytecode";
            case "commit" -> "Registering prepared mods";
            default -> "Waiting for loader events";
        };
    }
    public String detail() {
        if (status.equals("failed")) return "Stage failed" + (error == null ? "" : " · " + error);
        if (stage.equals("commit") && status.equals("complete")) return "Compatibility stages complete · waiting for Minecraft";
        if (determinate()) return completed + " / " + total + " · current stage only";
        if (completed != null) return completed + " observed · total unknown";
        return "Total unknown · observing actual loader work";
    }
}
