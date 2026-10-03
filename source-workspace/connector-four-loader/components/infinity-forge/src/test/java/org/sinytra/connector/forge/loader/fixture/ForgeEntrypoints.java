package org.sinytra.connector.forge.loader.fixture;

import net.neoforged.fml.ModLoadingContext;
import net.neoforged.fml.event.lifecycle.FMLCommonSetupEvent;
import org.sinytra.connector.forge.loader.ForgeModLoadingContext;

public final class ForgeEntrypoints {
    public static class ContextOnly {
        static { System.setProperty("unified.forge.facade.test.initialized", "yes"); }
        public static int constructions, setup, work;
        public static boolean sameContext, activeContainer, workSameContext;
        public static Thread workThread;
        private final ForgeModLoadingContext context;
        public ContextOnly(ForgeModLoadingContext context) {
            this.context = context;
            constructions++;
            sameContext = context == ForgeModLoadingContext.get();
            activeContainer = ModLoadingContext.get().getActiveContainer().getEventBus() == context.getModEventBus();
            context.getModEventBus().addListener(this::commonSetup);
        }
        private void commonSetup(FMLCommonSetupEvent event) {
            setup++;
            event.enqueueWork(() -> {
                work++;
                workThread = Thread.currentThread();
                workSameContext = ForgeModLoadingContext.get() == this.context;
            });
        }
    }
    public static class ContextFirst {
        public static int context, zero;
        public ContextFirst(ForgeModLoadingContext ignored) { context++; }
        public ContextFirst() { zero++; }
    }
    public static class ZeroArg {
        public static int constructions;
        public static boolean sameContext;
        public ZeroArg() { constructions++; sameContext = ForgeModLoadingContext.get().getModEventBus() != null; }
    }
    public static class PrivateContext {
        public static int zero;
        private PrivateContext(ForgeModLoadingContext ignored) { }
        public PrivateContext() { zero++; }
    }
    public static class Throwing {
        public static int attempts;
        public Throwing(ForgeModLoadingContext ignored) { attempts++; throw new IllegalStateException("own-constructor-cause"); }
    }
    public static class Unsupported {
        public Unsupported(String ignored) { }
    }
}
