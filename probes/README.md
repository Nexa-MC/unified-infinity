# Project-owned binary parity probe
This is our own fixture mod, not evidence of third-party mod compatibility.
One unchanged JAR is to be run under native Fabric and NeoForge+Connector.
It verifies Fabric entrypoint invocation, actual Fabric API EventFactory dispatch,
and upstream Mixin injection into a project-owned target before class definition.
It does not exercise Minecraft target mappings, registries, rendering or networking.

Version0.2 adds a real MinecraftServer tick method injection in the intermediary
namespace (method_3748, mapped from official tickServer(BooleanSupplier)). It records
200 idle ticks after100warmup ticks. This exercises Minecraft-target Mixin remapping;
its latency distribution is an idle-server baseline, not a loaded-modpack SLA.
