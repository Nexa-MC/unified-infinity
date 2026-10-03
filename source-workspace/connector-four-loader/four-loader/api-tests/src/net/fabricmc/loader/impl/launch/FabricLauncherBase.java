package net.fabricmc.loader.impl.launch;

import java.lang.reflect.Proxy;

/** Test-only stand-in for the existing host launcher's classloader accessor. */
public final class FabricLauncherBase {
    private static final FabricLauncher LAUNCHER = (FabricLauncher) Proxy.newProxyInstance(FabricLauncher.class.getClassLoader(), new Class[]{FabricLauncher.class}, (p,m,a) -> {
        if (m.getName().equals("getTargetClassLoader")) return Thread.currentThread().getContextClassLoader();
        throw new UnsupportedOperationException(m.getName());
    });
    public static FabricLauncher getLauncher() { return LAUNCHER; }
}
