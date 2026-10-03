# Bounded Forge 52 own-probe slice

This is an implementation proposal, not implemented support. All API comparisons
below use exact Forge 52.1.0 and NeoForge 21.1.219 / FML 4.0.42 source or binaries.
`inspection/*javap.txt` records erased JVM descriptors where relevant.

## 1. Own probe contract

Compile one genuine Forge-only mod against the pinned official 52.1.0 reference.
The resulting JAR contains `META-INF/mods.toml`, `@net.minecraftforge.fml.common.Mod`
and Forge API references, no NeoForge references or dual-loader descriptor.

The mod should have:

1. A public constructor taking `FMLJavaModLoadingContext`, with a per-run
   construction counter asserted to equal one. Add a separate zero-argument
   constructor fixture only after the primary path works; do not put both in one
   probe and accidentally test host-specific constructor selection
2. `context.getModEventBus().addListener(this::commonSetup)` and exactly one
   `FMLCommonSetupEvent`. `enqueueWork(Runnable)` verifies its task runs once,
   after registration, on the actual host main-thread work queue
3. `DeferredRegister<Block>.create(Registries.BLOCK, MODID)` and
   `DeferredRegister<Item>.create(Registries.ITEM, MODID)` in the first stage;
   both are genuine Forge overloads. Register one `Block` and its `BlockItem`
   using `RegistryObject`. Assert `isPresent`, `getId`, `getKey`, `get` at legal
   phases and a defined failure for premature `get`
4. Once stage 3 passes, switch/add a fixture using the common MDK pattern
   `DeferredRegister.create(ForgeRegistries.BLOCKS, MODID)` and `ITEMS`. This
   exercises the distinct `IForgeRegistry` facade rather than silently claiming
   it from the vanilla registry-key overload
5. `MinecraftForge.EVENT_BUS.addListener` for the explicit
   `TickEvent.ServerTickEvent.Post` subtype. Use `getServer()` and `haveTime()`;
   record tick count and thread identity. Do not claim compatibility for the
   base `TickEvent`/`phase`/`side` fields from this narrower test
6. A `ServerStartedEvent` callback or known parent-owned command harness checks
   `unified_forge_probe:anchor` in the actual host block/item registries. Place
   this block at a fixed location, put its item in a chest, and store a small
   marker in vanilla `SavedData` (or the existing proven persistence harness)
7. On the first run, place and save once; on the second, **read and assert before
   any write**. Assert registry IDs, block state, saved-data marker and chest
   item survived shutdown/reopen. A scoreboard-only check is insufficient to
   establish custom registry persistence

No third-party mods are needed for the initial vertical slice. Do not execute
the native Forge control or probe until the parent coordinates its launch.

## 2. Constructor and context ABI

Forge `FMLModContainer.constructMod()` selects
`modClass.getDeclaredConstructor(FMLJavaModLoadingContext.class)`, falling back
to `getDeclaredConstructor()`. It supplies its own per-mod context. Neo's
container instead requires exactly one public constructor and injects only:
`net.neoforged.bus.api.IEventBus`, `net.neoforged.fml.ModContainer`, Neo
`FMLModContainer`, and `net.neoforged.api.distmarker.Dist`.

Forge context has these descriptors:

```
FMLJavaModLoadingContext.getModEventBus()
  ()Lnet/minecraftforge/eventbus/api/IEventBus;
FMLJavaModLoadingContext.get()
  ()Lnet/minecraftforge/fml/javafmlmod/FMLJavaModLoadingContext;
FMLJavaModLoadingContext.getContainer()
  ()Lnet/minecraftforge/fml/javafmlmod/FMLModContainer;
```

It extends Forge `ModLoadingContext`, with a covariant bridge returning Forge
`ModContainer`. These types do not become equivalent by replacing a prefix.

**Preferred integration option:** a small integrated Forge-language adapter
implementing the host `IModLanguageLoader` contract, returning a host
`ModContainer` subclass. The host still controls construction and final event
delivery; the adapter recognizes Forge annotation data, obeys the exact Forge
constructor choice, and supplies a scoped context facade. Use a distinct
effective provider name/declared adapter ABI rather than registering another
`javafml` provider competing with native mods. Preserve original metadata/ranges
and validate them separately against the bounded Forge capability.

Host interface is `name()`, `version()`,
`loadMod(IModInfo, ModFileScanData, ModuleLayer): ModContainer`, plus `validate`.
Host `ModContainer` exposes a constructor `(IModInfo)`, a protected
`constructMod()`, abstract `getEventBus()`, and **final** event-acceptance methods.
Its event bus must support `allowPerPhasePost()` for host phase dispatch. The
adapter must not copy Forge's container wholesale: that would import Forge's
different lifecycle state machine, context extension and bus implementation.

A generated host entrypoint/constructor adapter is an alternative, but then
prove scan ownership, original annotation handling, one visible host
constructor, exactly-once invocation and exception attribution. A simple
`@Mod` remap alone will reject the real Forge context constructor.

## 3. Event bus and lifecycle: safe subset versus non-equivalence

| Surface | Forge | Neo | Bounded treatment |
|---|---|---|---|
| `IEventBus.addListener(Consumer)` | `(Consumer)V` | same | Can share host bus after explicit type/descriptor mapping and lambda method-type mapping |
| priority listener overloads | `(EventPriority,[boolean,Class,]Consumer)V` | corresponding overloads exist | Only admit exact audited descriptors; test ordering and receive-cancelled before claiming |
| `IEventBus.post(Event)` | `(ForgeEvent)Z` | `(NeoEvent)NeoEvent` | Cannot package-remap; rewrite call through a semantic adapter or reject |
| `addGenericListener` | multiple overloads | absent | Separate implementation, not admitted by the first slice |
| bus `shutdown()` | present | absent | Reject until specifically implemented |
| `Event` cancellation/result methods | Forge base-event semantics | split Neo contracts | No blanket equivalence |
| `FMLCommonSetupEvent` callback and `enqueueWork` | `enqueueWork(Runnable): CompletableFuture` | same callable descriptor after type adaptation | Can map callback type if actual host event/queue is used; no re-posting an imitation event |
| setup event constructor | `(ForgeModContainer,ModLoadingStage)` | `(NeoModContainer,DeferredWorkQueue)` | Not remappable for mods that construct/subclass it |
| `MinecraftForge.EVENT_BUS` | Forge global field | `NeoForge.EVENT_BUS` | Exact static field owner + descriptor remap for tested listeners; do not create another global bus |

For the own slice, an allowlisted relocation can map listener event types and
`IEventBus` to the existing host bus while non-isomorphic Forge context and
registry types map to explicitly owned facade classes. It must be a **symbol
map with exceptions**, not a blanket `net/minecraftforge` substitution. The
transform audit should list every Forge symbol in the input and whether it is
mapped, handled by a facade, or rejected. This also catches missing descriptors
inside lambda bootstrap handles, annotations and generic signatures.

## 4. Registry ABI: a real facade is needed

Forge and Neo have these erased descriptors:

```
Forge DeferredRegister.create(ResourceKey,String): Forge DeferredRegister
Forge DeferredRegister.create(IForgeRegistry,String): Forge DeferredRegister
Forge DeferredRegister.register(String,Supplier): Forge RegistryObject
Forge DeferredRegister.register(Forge IEventBus): void

Neo DeferredRegister.create(ResourceKey,String): Neo DeferredRegister
Neo DeferredRegister.create(Registry,String): Neo DeferredRegister
Neo DeferredRegister.register(String,Supplier): Neo DeferredHolder
Neo DeferredRegister.register(Neo IEventBus): void
```

The return descriptor is part of JVM linkage. Remapping `DeferredRegister` while
leaving `RegistryObject` unchanged fails. Blindly replacing `RegistryObject`
with `DeferredHolder` is also insufficient: Forge is a final `Supplier` wrapper,
Neo is a holder implementation, and optional/missing-entry methods differ.

Implement an owned minimal Forge `DeferredRegister` facade delegating once to
the Neo register for a vanilla registry key. Return a stable owned
`RegistryObject` facade wrapping the host holder. Its tested contract includes
`get(): Object`, `getId(): ResourceLocation`, `getKey(): ResourceKey`,
`isPresent(): boolean`, registration timing, and supplier/lambda identity.
Add other methods only with descriptor and behavior tests. Check Forge's
specified premature-get exception and optional behavior rather than inheriting
whatever exception a Neo holder happens to throw.

The `ForgeRegistries.BLOCKS`/`ITEMS` MDK pattern requires exact static field
descriptors `IForgeRegistry`; model them as views of **the actual vanilla/Neo
registry**, not new registry storage. Initially expose only the operations the
MDK probe uses, with deterministic unsupported diagnostics for other methods.
`create(IForgeRegistry,String)` resolves that view to its host registry key.
Custom `RegistryBuilder`, snapshots, aliases, missing mappings, sync, optional
registries, intrusive holders and `ObjectHolder` injection are outside this
first contract.

Forge `RegisterEvent.getForgeRegistry()`/`getVanillaRegistry()` are not Neo's
`getRegistry()` overloads. The default probe can let the native deferred-register
delegate own actual host RegisterEvent subscription. Do not assert user-written
Forge RegisterEvent listeners work until an explicit event-view adaptation is
implemented and tested.

## 5. Tick signature boundary

Forge class:
`net.minecraftforge.event.TickEvent$ServerTickEvent$Post`

Neo class:
`net.neoforged.neoforge.event.tick.ServerTickEvent$Post`

Both inherit `getServer(): MinecraftServer`; Forge has `haveTime(): boolean`,
Neo has `hasTime(): boolean`. Both Post constructors take
`(BooleanSupplier,MinecraftServer)`, but Forge's base `TickEvent` also carries
public `type`, `side`, `phase` fields and enums. Neo's hierarchy does not.

For the deliberately narrow Post callback, exact class and method rules can
target the native Neo event without an extra event copy. A probe that reads
`phase == END`, registers a base `TickEvent` listener, expects a Forge custom
event superclass, or relies on cancellation needs a richer view/dispatcher
contract; reject rather than silently change its semantics.

## 6. Bounded implementation and acceptance sequence

1. **Freeze and classify.** Preserve accepted c892/380221 pins. Add a read-only
   Forge-symbol/metadata inventory and its negative fixtures. Capture immutable
   original input hash, source namespace, API ABI, side and unsupported symbols
2. **Metadata through host discovery.** Add the Forge reader/projection to the
   one transaction before FML's incompatible-mod fallback. Cover mandatory vs
   optional dependencies, wrong MC/Forge range, wrong Java, duplicate mod IDs,
   dual descriptors and side filtering. Retain host uniqueness and sorting
3. **Constructor/context gate.** Integrate the language adapter or explicit
   generated entrypoint mechanism. Build the genuine own Forge JAR once. Before
   a world, prove `@Mod` scan, context constructor, one construction, host mod
   list identity and exception propagation. Merely being listed is not a pass
4. **Setup + vanilla-key deferred registry.** Add tested bus listener mappings,
   context, `DeferredRegister` and `RegistryObject` facades. Prove setup once,
   `enqueueWork` once, block/item registration once, supplier timing and no
   second registry freeze schedule
5. **Common MDK registry field gate.** Add only the required `IForgeRegistry`
   views and `ForgeRegistries.BLOCKS`/`ITEMS` fields. Run the MDK-style variant
6. **Tick + persistence.** Add explicit Post tick mapping/member adaptation and
   actual world/registry assertions. Parent coordinates isolated native Forge
   52.1.0 and Unified runs: clean world, save/stop, reopen. Keep full event traces,
   input/output hashes, logs and world evidence. Compare semantic assertions,
   not wall-clock tick counts
7. **Regression and attribution.** Repeat the accepted native-Neo and Fabric
   probes on the new exact core/host profile, then the previously approved
   Lithium/Chunky/Farmer's Delight acceptance as coordinated. One at a time
   first; pair tests only after individual controls work
8. **Next feature only from evidence.** Own-Mixin/refmap fixture, config or an
   approved real Forge artifact comes next. No broad Forge/4-loader support
   claim, and no performance work, until these gates produce actual evidence

Transform caching must hash the original JAR, exact target/host/adapter ABI,
symbol rules and source namespace. No game-load side effects should occur in
static admission. A failed/unsupported candidate must remain a diagnosed failed
candidate, not become a successful empty transform or silently skipped mod.
