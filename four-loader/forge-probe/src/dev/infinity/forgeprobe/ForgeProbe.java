package dev.infinity.forgeprobe;

import java.util.concurrent.atomic.AtomicInteger;
import net.minecraft.core.BlockPos;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.entity.ChestBlockEntity;
import net.minecraft.world.level.saveddata.SavedData;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.event.server.ServerStartedEvent;
import net.minecraftforge.eventbus.api.IEventBus;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.event.lifecycle.FMLCommonSetupEvent;
import net.minecraftforge.fml.javafmlmod.FMLJavaModLoadingContext;
import net.minecraftforge.registries.DeferredRegister;
import net.minecraftforge.registries.RegistryObject;

/** Original project-owned fixture. Compiled once against official Forge 52.1.0. */
@Mod(ForgeProbe.MOD_ID)
public final class ForgeProbe {
    public static final String MOD_ID = "unified_forge_probe";
    private static final ResourceLocation ID = ResourceLocation.fromNamespaceAndPath(MOD_ID, "anchor");
    private static final AtomicInteger CONSTRUCTIONS = new AtomicInteger();
    private static final AtomicInteger SUPPLIERS = new AtomicInteger();
    private static final DeferredRegister<Item> ITEMS = DeferredRegister.create(Registries.ITEM, MOD_ID);
    private static final RegistryObject<Item> ANCHOR = ITEMS.register("anchor", () -> {
        require(SUPPLIERS.incrementAndGet() == 1, "duplicate_item_supplier");
        return new Item(new Item.Properties());
    });
    private static final BlockPos CHEST = new BlockPos(0, 100, 0);
    private static final String MARKER = "forge_52_1_0_probe_v1";
    private final AtomicInteger setups = new AtomicInteger();
    private final AtomicInteger queued = new AtomicInteger();
    private MinecraftServer startedServer;
    private int postTicks;

    public ForgeProbe(FMLJavaModLoadingContext context) {
        require(CONSTRUCTIONS.incrementAndGet() == 1, "duplicate_constructor");
        require(!ANCHOR.isPresent(), "premature_registry_presence");
        boolean prematureGetRejected = false;
        try {
            ANCHOR.get();
        } catch (NullPointerException expected) {
            prematureGetRejected = true;
        }
        require(prematureGetRejected, "premature_get_must_throw_NullPointerException");
        require(ANCHOR.getId().equals(ID), "early_registry_id");
        require(ANCHOR.getKey().location().equals(ID), "early_registry_key");
        IEventBus modBus = context.getModEventBus();
        ITEMS.register(modBus);
        modBus.addListener(this::commonSetup);
        MinecraftForge.EVENT_BUS.addListener(this::serverStarted);
        MinecraftForge.EVENT_BUS.addListener(this::serverTick);
        pass("constructor", "count=1 context=" + context.getClass().getName() + " premature_get=NullPointerException");
    }

    private void commonSetup(FMLCommonSetupEvent event) {
        require(setups.incrementAndGet() == 1, "duplicate_common_setup");
        verifyRegistry();
        pass("common_setup", "count=1");
        event.enqueueWork(() -> {
            require(queued.incrementAndGet() == 1, "duplicate_enqueued_work");
            verifyRegistry();
            pass("enqueued_work", "count=1 thread=" + Thread.currentThread().getName());
        });
    }

    private void serverStarted(ServerStartedEvent event) {
        require(startedServer == null, "duplicate_server_started");
        startedServer = event.getServer();
        require(startedServer.isSameThread(), "server_started_wrong_thread");
        require(setups.get() == 1 && queued.get() == 1, "setup_queue_incomplete");
        verifyRegistry();
        ServerLevel level = startedServer.overworld();
        ProbeData data = level.getDataStorage().computeIfAbsent(ProbeData.FACTORY, MOD_ID);
        String phase = System.getProperty("unified.forgeProbe.phase", "unset");
        if (phase.equals("create")) {
            require(data.marker.isEmpty(), "create_requires_new_world");
            level.setBlock(CHEST.below(), Blocks.STONE.defaultBlockState(), 3);
            require(level.setBlock(CHEST, Blocks.CHEST.defaultBlockState(), 3), "place_chest");
            require(level.getBlockEntity(CHEST) instanceof ChestBlockEntity, "created_chest_missing");
            ChestBlockEntity chest = (ChestBlockEntity) level.getBlockEntity(CHEST);
            chest.setItem(0, new ItemStack(ANCHOR.get(), 7));
            chest.setChanged();
            data.marker = MARKER;
            data.setDirty();
            verifyWorld(level, data);
            pass("world_create", "item=" + ID + " count=7 pos=0,100,0 saved_data=" + MARKER);
        } else if (phase.equals("reopen")) {
            // Read every assertion before any mod write; missing data must fail, never repair itself.
            verifyWorld(level, data);
            pass("world_reopen", "read_before_write=true item=" + ID + " count=7 saved_data=" + data.marker);
        } else {
            throw new IllegalStateException("Set -Dunified.forgeProbe.phase=create or reopen, got " + phase);
        }
        pass("server_started", "phase=" + phase + " registry_id=" + ANCHOR.getId() + " supplier_count=" + SUPPLIERS.get());
    }

    private void serverTick(TickEvent.ServerTickEvent.Post event) {
        require(event.getServer() == startedServer, "post_tick_server_identity");
        require(event.getServer().isSameThread(), "post_tick_wrong_thread");
        boolean haveTime = event.haveTime();
        if (++postTicks == 5) {
            verifyRegistry();
            pass("post_tick", "count=5 haveTime=" + haveTime + " thread=" + Thread.currentThread().getName());
            pass("ready_to_save", "phase=" + System.getProperty("unified.forgeProbe.phase"));
        }
    }

    private static void verifyRegistry() {
        require(ANCHOR.isPresent(), "registry_object_absent");
        require(ANCHOR.getId().equals(ID), "registry_id");
        require(ANCHOR.getKey().location().equals(ID), "registry_key");
        require(ANCHOR.get() == BuiltInRegistries.ITEM.get(ID), "registry_identity");
        require(SUPPLIERS.get() == 1, "supplier_count");
    }

    private static void verifyWorld(ServerLevel level, ProbeData data) {
        require(MARKER.equals(data.marker), "saved_data_marker");
        require(level.getBlockState(CHEST).is(Blocks.CHEST), "persisted_chest_block");
        require(level.getBlockEntity(CHEST) instanceof ChestBlockEntity, "persisted_chest_entity");
        ItemStack stack = ((ChestBlockEntity) level.getBlockEntity(CHEST)).getItem(0);
        require(stack.getItem() == ANCHOR.get() && stack.getCount() == 7, "persisted_custom_item");
    }

    private static void require(boolean value, String assertion) {
        if (!value) throw new IllegalStateException("UNIFIED_FORGE_PROBE FAIL assertion=" + assertion);
    }

    private static void pass(String stage, String detail) {
        System.out.println("UNIFIED_FORGE_PROBE PASS stage=" + stage + " " + detail);
    }

    private static final class ProbeData extends SavedData {
        private static final SavedData.Factory<ProbeData> FACTORY =
                new SavedData.Factory<>(ProbeData::new, ProbeData::load, null);
        private String marker = "";

        private static ProbeData load(CompoundTag tag, HolderLookup.Provider registries) {
            ProbeData data = new ProbeData();
            data.marker = tag.getString("marker");
            return data;
        }

        @Override
        public CompoundTag save(CompoundTag tag, HolderLookup.Provider registries) {
            tag.putString("marker", marker);
            return tag;
        }
    }
}
