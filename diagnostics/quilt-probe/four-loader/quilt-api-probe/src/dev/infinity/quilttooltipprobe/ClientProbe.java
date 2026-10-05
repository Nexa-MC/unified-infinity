package dev.infinity.quilttooltipprobe;

import java.util.List;
import net.minecraft.class_1657;
import net.minecraft.class_1792;
import net.minecraft.class_1799;
import net.minecraft.class_1836;
import net.minecraft.class_2561;
import net.minecraft.class_2960;
import net.minecraft.class_310;
import net.minecraft.class_5631;
import net.minecraft.class_5632;
import net.minecraft.class_5682;
import net.minecraft.class_5684;
import net.minecraft.class_9276;
import org.quiltmc.loader.api.ModContainer;
import org.quiltmc.loader.api.QuiltLoader;
import org.quiltmc.loader.api.entrypoint.EntrypointContainer;
import org.quiltmc.loader.api.minecraft.ClientOnly;
import org.quiltmc.qsl.base.api.entrypoint.client.ClientModInitializer;
import org.quiltmc.qsl.base.api.event.Event;
import org.quiltmc.qsl.base.api.event.ListenerPhase;
import org.quiltmc.qsl.base.api.event.client.ClientEventAwareListener;
import org.quiltmc.qsl.lifecycle.api.client.event.ClientLifecycleEvents;
import org.quiltmc.qsl.tooltip.api.ConvertibleTooltipData;
import org.quiltmc.qsl.tooltip.api.client.ItemTooltipCallback;
import org.quiltmc.qsl.tooltip.api.client.TooltipComponentCallback;

/** A field entrypoint shared by client initialization and QSL automatic listeners. */
@ClientOnly
@ListenerPhase(callbackTarget = ItemTooltipCallback.class,
        namespace = CommonProbe.NAMESPACE, path = "automatic_item")
public final class ClientProbe implements ClientModInitializer, ItemTooltipCallback, TooltipComponentCallback {
    public static final ClientProbe INSTANCE = new ClientProbe();
    private static final String MANUAL_MARKER = "QSL manual tooltip marker";
    private static final String AUTOMATIC_MARKER = "QSL automatic tooltip marker";
    private int initialized;
    private int ready;
    private long nextRequest;
    private long hoverRequests;
    private boolean override;
    private class_5684 overrideComponent;
    private ItemRequest itemRequest;
    private ComponentRequest componentRequest;

    private ClientProbe() { }

    @Override
    public void onInitializeClient(ModContainer mod) {
        check(CommonProbe.initialized == 1 && ++initialized == 1, "client_init_once_after_common");
        check(QuiltLoader.getModContainer(CommonProbe.ID).orElseThrow() == mod, "client_init_provider_identity");
        // Event construction may auto-register INSTANCE here. Never manually register this listener.
        ItemTooltipCallback.EVENT.addPhaseOrdering(Event.DEFAULT_PHASE,
                class_2960.method_60655(CommonProbe.NAMESPACE, "automatic_item"));
        ItemTooltipCallback.EVENT.register(this::manualItemTooltip);
        TooltipComponentCallback.EVENT.register(data -> {
            ComponentRequest request = componentRequest;
            if (request != null) {
                check(data == request.data, "manual_component_data_identity");
                check(++request.manual == 1, "manual_component_once_per_request");
            }
            return override && data instanceof CommonTooltipData ? overrideComponent : null;
        });
        TooltipComponentCallback.EVENT.register(data -> {
            if (componentRequest != null) {
                check(data == componentRequest.data, "tail_component_data_identity");
                check(++componentRequest.tail == 1, "tail_component_once_per_request");
            }
            return null;
        });
        // Ordering of DEFAULT before ConvertibleTooltipData.EVENT_PHASE belongs to the original module.
        // Deliberately do not repair/add that edge here: the direct checks must detect a missing edge.
        ClientLifecycleEvents.READY.register(this::readyClient);
        CommonProbe.pass("client_init", "count=1 automatic_listener=INSTANCE manual_listeners_registered=true");
    }

    private void readyClient(class_310 client) {
        check(++ready == 1, "client_ready_once_no_replay");
        verifyEntrypointIdentity();
        overrideComponent = class_5684.method_32662(class_2561.method_43470("QSL default-phase override component").method_30937());
        try {
            directItemRequest(new class_1799(CommonProbe.convertibleItem), "convertible_item_null_player");
            directItemRequest(new class_1799(CommonProbe.plainItem), "plain_item_null_player");
            check(new class_1799(CommonProbe.plainItem).method_32347().isEmpty(), "plain_item_has_no_custom_data");
            CommonTooltipData data = new CommonTooltipData("QSL convertible component", false);
            override = true;
            class_5684 result = directComponentRequest(data, "default_override", 0, false);
            check(result == overrideComponent && data.conversions == 0, "default_first_override_before_convertible");
            override = false;
            result = directComponentRequest(data, "convertible_fallback", 1, false);
            check(result != null && result != overrideComponent && data.conversions == 1, "convertible_called_once_after_null");
            // A second real request proves counters are per invocation, not a frame/global count.
            directComponentRequest(data, "convertible_second_request", 1, false);
            check(data.conversions == 2, "convertible_once_per_each_request");
            result = directComponentRequest(new class_5631(class_9276.field_49289), "vanilla_bundle_fallback", 1, false);
            check(result instanceof class_5682, "vanilla_bundle_result_after_all_null_callbacks");
            CommonTooltipData nullData = new CommonTooltipData("null conversion", true);
            directComponentRequest(nullData, "null_convertible_vanilla_rejection", 1, true);
            check(nullData.conversions == 1, "null_convertible_called_once");
            directComponentRequest(new UnsupportedData(), "unsupported_vanilla_rejection", 1, true);
            CommonProbe.pass("direct_requests", "item_requests=2 component_requests=6 null_player=true mutable_lines=true"
                    + " default_first=true first_non_null=true vanilla_fallback=true runtime_ui_evidence=STILL_REQUIRED");
        } finally {
            itemRequest = null;
            componentRequest = null;
            override = Boolean.getBoolean("unified.quiltTooltipProbe.override");
        }
    }

    private void manualItemTooltip(class_1799 stack, class_1657 player, class_1792.class_9635 context,
            class_1836 config, List<class_2561> lines) {
        if (!isProbeStack(stack)) return;
        check(!lines.isEmpty(), "vanilla_lines_precede_callbacks");
        check(countMarker(lines, MANUAL_MARKER) == 0 && countMarker(lines, AUTOMATIC_MARKER) == 0,
                "manual_marker_not_duplicated");
        ItemRequest request = itemRequest;
        if (request != null) {
            check(stack == request.stack && player == null && context == class_1792.class_9635.field_51353
                    && config == class_1836.field_41070, "manual_item_arguments_and_null_player");
            check(++request.manual == 1, "manual_item_once_per_request");
            request.lines = lines;
            request.vanillaLines = lines.size();
        }
        lines.add(class_2561.method_43470(MANUAL_MARKER));
    }

    @Override
    public void onTooltipRequest(class_1799 stack, class_1657 player, class_1792.class_9635 context,
            class_1836 config, List<class_2561> lines) {
        if (!isProbeStack(stack)) return;
        check(countMarker(lines, MANUAL_MARKER) == 1 && countMarker(lines, AUTOMATIC_MARKER) == 0,
                "automatic_item_annotation_phase_and_no_duplicates");
        ItemRequest request = itemRequest;
        if (request != null) {
            check(stack == request.stack && player == null && request.lines == lines
                    && context == class_1792.class_9635.field_51353 && config == class_1836.field_41070,
                    "automatic_item_same_arguments_same_mutable_list");
            check(++request.automatic == 1 && request.manual == 1, "automatic_item_once_after_manual");
        }
        lines.add(class_2561.method_43470(AUTOMATIC_MARKER));
        if (request == null && ++hoverRequests <= 3) {
            CommonProbe.pass("external_item_request", "request=" + hoverRequests
                    + " manual_markers=1 automatic_markers=1 null_player=" + (player == null));
        }
    }

    @Override
    public class_5684 getComponent(class_5632 data) {
        if (componentRequest != null) {
            check(data == componentRequest.data, "automatic_component_data_identity");
            check(++componentRequest.automatic == 1, "automatic_component_once_per_request");
        }
        return null;
    }

    private void directItemRequest(class_1799 stack, String label) {
        check(itemRequest == null, "no_nested_item_request");
        ItemRequest request = new ItemRequest(++nextRequest, stack);
        itemRequest = request;
        try {
            // Actual vanilla target, never Event.invoker() as a substitute for injection evidence.
            List<class_2561> lines = stack.method_7950(class_1792.class_9635.field_51353, null, class_1836.field_41070);
            check(request.manual == 1 && request.automatic == 1, "both_item_callbacks_once");
            check(lines == request.lines && lines.size() == request.vanillaLines + 2, "returned_same_mutable_list");
            check(lines.get(lines.size() - 2).getString().equals(MANUAL_MARKER)
                    && lines.get(lines.size() - 1).getString().equals(AUTOMATIC_MARKER), "ordered_appended_markers");
            lines.add(class_2561.method_43470("request-local mutability check"));
            lines.remove(lines.size() - 1);
            CommonProbe.pass("item_request", "request=" + request.id + " label=" + label
                    + " manual=1 automatic=1 vanilla_lines=" + request.vanillaLines + " null_player=true same_list=true");
        } finally {
            itemRequest = null;
        }
    }

    private class_5684 directComponentRequest(class_5632 data, String label, int expectedTail, boolean vanillaRejects) {
        check(componentRequest == null, "no_nested_component_request");
        ComponentRequest request = new ComponentRequest(++nextRequest, data);
        componentRequest = request;
        int conversionsBefore = data instanceof CommonTooltipData convertible ? convertible.conversions : 0;
        class_5684 result = null;
        boolean rejected = false;
        try {
            try {
                // Exact original TooltipComponent.of(TooltipData) target.
                result = class_5684.method_32663(data);
            } catch (IllegalArgumentException exception) {
                if (!vanillaRejects) throw exception;
                rejected = true;
            }
            check(rejected == vanillaRejects, "vanilla_rejection_contract_" + label);
            check(request.automatic == 1 && request.manual == 1 && request.tail == expectedTail,
                    "component_callbacks_once_and_first_non_null_" + label);
            int conversions = data instanceof CommonTooltipData convertible ? convertible.conversions - conversionsBefore : 0;
            CommonProbe.pass("component_request", "request=" + request.id + " label=" + label
                    + " automatic=" + request.automatic + " manual=" + request.manual + " tail=" + request.tail
                    + " convertible=" + conversions + " vanilla_rejected=" + rejected
                    + " result=" + (result == null ? "null" : result.getClass().getName()));
            return result;
        } finally {
            componentRequest = null;
        }
    }

    private void verifyEntrypointIdentity() {
        EntrypointContainer<ClientEventAwareListener> ownEvents = eventProvider(CommonProbe.ID);
        EntrypointContainer<ClientModInitializer> ownInit = initProvider(CommonProbe.ID);
        check(ownEvents.getEntrypoint() == INSTANCE && ownInit.getEntrypoint() == INSTANCE,
                "own_client_events_client_init_same_INSTANCE");
        check(ownEvents.getProvider() == ownInit.getProvider()
                && ownEvents.getProvider() == QuiltLoader.getModContainer(CommonProbe.ID).orElseThrow(),
                "own_native_entrypoint_provider_identity");
        EntrypointContainer<ClientEventAwareListener> moduleEvents = eventProvider("quilt_tooltip");
        EntrypointContainer<ClientModInitializer> moduleInit = initProvider("quilt_tooltip");
        Object listener = moduleEvents.getEntrypoint();
        check(listener == moduleInit.getEntrypoint(), "original_tooltip_same_INSTANCE_both_keys");
        check(listener instanceof TooltipComponentCallback, "original_tooltip_listener_type");
        check(listener.getClass().getName().equals("org.quiltmc.qsl.tooltip.impl.client.QuiltClientTooltipMod"),
                "original_tooltip_implementation_class");
        check(moduleEvents.getProvider() == moduleInit.getProvider()
                && moduleEvents.getProvider() == QuiltLoader.getModContainer("quilt_tooltip").orElseThrow(),
                "original_tooltip_native_provider_identity");
        check(moduleEvents.getProvider().getClassLoader() == listener.getClass().getClassLoader()
                && listener.getClass().getClassLoader() == ItemTooltipCallback.class.getClassLoader()
                && listener.getClass().getClassLoader() == getClass().getClassLoader(), "one_game_classloader");
        try {
            check(listener.getClass().getField("INSTANCE").get(null) == listener, "original_static_field_identity");
        } catch (ReflectiveOperationException exception) {
            throw new IllegalStateException("NATIVE_QUILT_TOOLTIP_PROBE original_INSTANCE", exception);
        }
        ListenerPhase phase = listener.getClass().getAnnotation(ListenerPhase.class);
        check(phase != null && phase.callbackTarget() == TooltipComponentCallback.class
                && class_2960.method_60655(phase.namespace(), phase.path()).equals(ConvertibleTooltipData.EVENT_PHASE),
                "original_convertible_listener_annotation");
        CommonProbe.pass("native_identity", "own_singleton=true module_singleton=true native_provider=true"
                + " same_classloader=true callback_phase=" + ConvertibleTooltipData.EVENT_PHASE
                + " module_sources=" + moduleEvents.getProvider().getSourcePaths()
                + " implementation_source=" + listener.getClass().getProtectionDomain().getCodeSource());
    }

    private static EntrypointContainer<ClientEventAwareListener> eventProvider(String id) {
        var entries = QuiltLoader.getEntrypointContainers("client_events", ClientEventAwareListener.class).stream()
                .filter(entry -> entry.getProvider().metadata().id().equals(id)).toList();
        check(entries.size() == 1, "exactly_one_client_events_entry_" + id);
        return entries.get(0);
    }

    private static EntrypointContainer<ClientModInitializer> initProvider(String id) {
        var entries = QuiltLoader.getEntrypointContainers("client_init", ClientModInitializer.class).stream()
                .filter(entry -> entry.getProvider().metadata().id().equals(id)).toList();
        check(entries.size() == 1, "exactly_one_client_init_entry_" + id);
        return entries.get(0);
    }

    private static boolean isProbeStack(class_1799 stack) {
        return stack.method_7909() == CommonProbe.convertibleItem || stack.method_7909() == CommonProbe.plainItem;
    }

    private static long countMarker(List<class_2561> lines, String marker) {
        return lines.stream().filter(text -> text.getString().equals(marker)).count();
    }

    private static void check(boolean condition, String name) { CommonProbe.require(condition, name); }

    @ClientOnly
    private static final class ItemRequest {
        final long id;
        final class_1799 stack;
        List<class_2561> lines;
        int vanillaLines;
        int manual;
        int automatic;
        ItemRequest(long id, class_1799 stack) { this.id = id; this.stack = stack; }
    }

    @ClientOnly
    private static final class ComponentRequest {
        final long id;
        final class_5632 data;
        int automatic;
        int manual;
        int tail;
        ComponentRequest(long id, class_5632 data) { this.id = id; this.data = data; }
    }

    @ClientOnly
    private static final class UnsupportedData implements class_5632 { }
}
