package org.sinytra.connector.forge.loader;

import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;
import net.neoforged.bus.EventBusErrorMessage;
import net.neoforged.bus.api.BusBuilder;
import net.neoforged.bus.api.Event;
import net.neoforged.bus.api.EventListener;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.ModContainer;
import net.neoforged.fml.ModLoadingContext;
import net.neoforged.fml.ModLoadingException;
import net.neoforged.fml.ModLoadingIssue;
import net.neoforged.fml.event.IModBusEvent;
import net.neoforged.neoforgespi.language.IModInfo;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

/** One host-managed container, construction attempt, and mod event bus per Forge mod. */
public final class ForgeModContainer extends ModContainer {
    private static final Logger LOGGER = LogManager.getLogger();

    private final IEventBus eventBus;
    private final ForgeModLoadingContext context;
    private final Class<?> modClass;
    private final AtomicBoolean constructionAttempted = new AtomicBoolean();
    private Object modInstance;

    public ForgeModContainer(IModInfo info, String entrypoint, ModuleLayer gameLayer) {
        super(info);
        this.eventBus = BusBuilder.builder()
            .setExceptionHandler(ForgeModContainer::onEventFailed)
            .markerType(IModBusEvent.class)
            .allowPerPhasePost()
            .build();
        this.context = new ForgeModLoadingContext(this);

        // Match the host language loader's class-loading scope. Class.forName(Module,
        // String) does not initialize the class; initialization happens at construction.
        var hostContext = ModLoadingContext.get();
        try {
            hostContext.setActiveContainer(this);
            String moduleName = info.getOwningFile().moduleName();
            Module module = gameLayer.findModule(moduleName)
                .orElseThrow(() -> new IllegalStateException("Forge entrypoint module not found: " + moduleName));
            this.modClass = Objects.requireNonNull(Class.forName(module, entrypoint),
                "Forge entrypoint class not found in its owning module: " + entrypoint);
        } catch (Throwable failure) {
            throw loadingFailure("fml.modloadingissue.failedtoloadmodclass", failure);
        } finally {
            hostContext.setActiveContainer(null);
        }
    }

    @Override
    protected void constructMod() {
        if (!this.constructionAttempted.compareAndSet(false, true)) {
            throw loadingFailure("fml.modloadingissue.failedtoloadmod",
                new IllegalStateException("Forge mod construction was already attempted: " + getModId()));
        }
        try {
            // ModLoader owns this scope, including the following FMLConstructModEvent.
            // Do not clear it or replace the host's final lifecycle event dispatch.
            if (ModLoadingContext.get().getActiveContainer() != this) {
                throw new IllegalStateException("Forge mod construction requires its active host container: " + getModId());
            }
            Constructor<?> constructor;
            try {
                constructor = this.modClass.getDeclaredConstructor(ForgeModLoadingContext.class);
            } catch (NoSuchMethodException | SecurityException noContextConstructor) {
                constructor = this.modClass.getDeclaredConstructor();
            }
            this.modInstance = constructor.getParameterCount() == 0
                ? constructor.newInstance()
                : constructor.newInstance(this.context);
            LOGGER.debug("Constructed Forge adapter mod {} using {}", getModId(), constructor);
        } catch (Throwable failure) {
            if (failure instanceof InvocationTargetException wrapped && wrapped.getCause() != null) {
                failure = wrapped.getCause();
            }
            throw loadingFailure("fml.modloadingissue.failedtoloadmod", failure);
        }
    }

    @Override
    public IEventBus getEventBus() {
        return this.eventBus;
    }

    ForgeModLoadingContext context() {
        return this.context;
    }

    private ModLoadingException loadingFailure(String message, Throwable cause) {
        return new ModLoadingException(ModLoadingIssue.error(message).withAffectedMod(this.modInfo).withCause(cause));
    }

    private static void onEventFailed(IEventBus bus, Event event, EventListener[] listeners, int index, Throwable failure) {
        LOGGER.error(new EventBusErrorMessage(event, index, listeners, failure));
    }
}
