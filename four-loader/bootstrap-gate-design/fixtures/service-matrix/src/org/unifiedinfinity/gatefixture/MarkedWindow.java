package org.unifiedinfinity.gatefixture;
import net.neoforged.neoforgespi.earlywindow.ImmediateWindowProvider;
import java.util.*;
import java.util.function.*;
public final class MarkedWindow implements ImmediateWindowProvider {
    static { Markers.mark("window-static"); }
    public MarkedWindow() { Markers.mark("window-constructor"); }
    public String name() { return "unified-admission-fixture"; }
    public Runnable initialize(String[] arguments) { Markers.mark("window-initialize"); return () -> {}; }
    public void updateFramebufferSize(IntConsumer width, IntConsumer height) {}
    public long setupMinecraftWindow(IntSupplier width, IntSupplier height, Supplier<String> title, LongSupplier monitor) { return 0; }
    public boolean positionWindow(Optional<Object> monitor, IntConsumer width, IntConsumer height, IntConsumer x, IntConsumer y) { return false; }
    public <T> Supplier<T> loadingOverlay(Supplier<?> mc, Supplier<?> ri, Consumer<Optional<Throwable>> error, boolean fade) { return () -> null; }
    public void updateModuleReads(ModuleLayer layer) {}
    public void periodicTick() {}
    public String getGLVersion() { return "fixture"; }
    public void crash(String message) { throw new IllegalStateException(message); }
}
