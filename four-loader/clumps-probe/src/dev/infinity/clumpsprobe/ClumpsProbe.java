package dev.infinity.clumpsprobe;

import com.blamejared.clumps.helper.IClumpedOrb;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;
import net.minecraft.core.BlockPos;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.ExperienceOrb;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.saveddata.SavedData;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.event.server.ServerStartedEvent;
import net.minecraftforge.fml.common.Mod;

/** Original Forge-only fixture; observes real Clumps mixins on normal server ticks. */
@Mod(ClumpsProbe.MOD_ID)
public final class ClumpsProbe {
    public static final String MOD_ID = "unified_clumps_probe";
    private static final String MARKER = "clumps_forge_19_0_0_1_probe_v1";
    private static final AtomicInteger CONSTRUCTIONS = new AtomicInteger();
    private static final BlockPos ORIGIN = new BlockPos(8, 100, 8);
    private static final AABB ARENA = new AABB(5, 100, 5, 12, 104, 12);
    private static final int[] VALUES = {1, 3, 7, 7, 17, 37};
    private static final Map<Integer, Integer> EXPECTED = Map.of(1, 1, 3, 1, 7, 2, 17, 1, 37, 1);
    private static final int MAX_TICKS = 200;
    private MinecraftServer server;
    private ServerLevel level;
    private ProbeData data;
    private String phase;
    private int postTicks;
    private int settledTicks;
    private boolean seeded;
    private boolean finished;

    public ClumpsProbe() {
        require(CONSTRUCTIONS.incrementAndGet() == 1, "duplicate_constructor");
        MinecraftForge.EVENT_BUS.addListener(this::serverStarted);
        MinecraftForge.EVENT_BUS.addListener(this::serverTick);
        pass("constructor", "count=1");
    }

    private void serverStarted(ServerStartedEvent event) {
        require(server == null, "duplicate_server_started");
        server = event.getServer();
        require(server.isSameThread(), "server_started_wrong_thread");
        level = server.overworld();
        require(level.players().isEmpty(), "requires_no_players");
        phase = System.getProperty("unified.clumpsProbe.phase", "unset");
        require(phase.equals("create") || phase.equals("reopen"), "phase_must_be_create_or_reopen");
        data = level.getDataStorage().computeIfAbsent(ProbeData.FACTORY, MOD_ID);
        if (phase.equals("create")) {
            require(data.marker.isEmpty(), "create_requires_new_probe_world");
            level.setChunkForced(0, 0, true);
            level.getChunk(0, 0);
        } else {
            // Do not repair missing world evidence or respawn/reseed an absent entity.
            require(MARKER.equals(data.marker), "saved_data_marker_missing");
            require(data.survivor != null, "saved_survivor_uuid_missing");
            require(level.getForcedChunks().contains(ChunkPos.asLong(0, 0)), "persisted_forced_chunk_missing");
        }
        pass("server_started", "phase=" + phase + " players=0 max_post_ticks=" + MAX_TICKS);
    }

    private void serverTick(TickEvent.ServerTickEvent.Post event) {
        require(event.getServer() == server, "post_tick_server_identity");
        require(event.getServer().isSameThread(), "post_tick_wrong_thread");
        boolean haveTime = event.haveTime();
        if (finished) return;
        require(level.players().isEmpty(), "unexpected_player");
        if (++postTicks == 1) pass("post_tick", "count=1 haveTime=" + haveTime);
        require(postTicks <= MAX_TICKS, "behavior_timeout_phase_" + phase);
        if (!level.isPositionEntityTicking(ORIGIN) || !level.areEntitiesLoaded(ChunkPos.asLong(0, 0))) return;
        if (phase.equals("create")) runCreate();
        else runReopen();
    }

    private void runCreate() {
        if (!seeded) {
            require(orbs().isEmpty(), "arena_has_preexisting_orbs");
            for (int x = 5; x <= 11; x++) {
                for (int z = 5; z <= 11; z++) {
                    level.setBlock(new BlockPos(x, 99, z), Blocks.STONE.defaultBlockState(), 3);
                    for (int y = 100; y <= 103; y++) {
                        level.setBlock(new BlockPos(x, y, z), Blocks.AIR.defaultBlockState(), 3);
                    }
                }
            }
            for (int i = 0; i < VALUES.length; i++) {
                ExperienceOrb orb = new ExperienceOrb(level, 8.35 + i * 0.05, 100.1, 8.5, VALUES[i]);
                require(orb instanceof IClumpedOrb, "clumps_interface_not_injected");
                require(map(orb).equals(Map.of(VALUES[i], 1)), "initial_orb_value_" + i);
                orb.setNoGravity(true);
                orb.setDeltaMovement(Vec3.ZERO);
                require(orb.addTag(MOD_ID), "orb_tag");
                require(level.addFreshEntity(orb), "spawn_orb_" + i);
            }
            List<ExperienceOrb> initial = orbs();
            require(initial.size() == VALUES.length, "initial_entity_count");
            verifyTotals(initial);
            seeded = true;
            pass("seeded", "entities=6 units=6 xp=72 map=1:1,3:1,7:2,17:1,37:1");
            return;
        }
        List<ExperienceOrb> current = orbs();
        verifyTotals(current); // Every observed merge transition must preserve the entire histogram.
        require(current.size() <= VALUES.length, "entity_count_increased");
        if (current.size() != 1) {
            settledTicks = 0;
            return;
        }
        ExperienceOrb survivor = current.getFirst();
        require(survivor.tickCount > 0, "survivor_never_ticked");
        if (++settledTicks < 5) return;
        pass("merge", "initial_entities=6 final_entities=1 units=6 xp=72 stable_observations=5 post_ticks=" + postTicks);
        verifyNbtRoundTrip(survivor);
        data.marker = MARKER;
        data.survivor = survivor.getUUID();
        data.setDirty();
        pass("world_create", "survivor=" + data.survivor + " saved_data=" + MARKER);
        finish();
    }

    private void runReopen() {
        // Entity loading is asynchronous; wait for the saved UUID, but never synthesize it.
        if (level.getEntity(data.survivor) == null) return;
        List<ExperienceOrb> current = orbs();
        require(current.size() == 1, "reopen_entity_count");
        ExperienceOrb survivor = current.getFirst();
        require(survivor.getUUID().equals(data.survivor), "reopen_survivor_identity");
        require(survivor.getTags().contains(MOD_ID), "reopen_probe_tag");
        require(survivor.isNoGravity(), "reopen_no_gravity");
        require(level.getBlockState(ORIGIN.below()).is(Blocks.STONE), "reopen_platform_missing");
        verifyTotals(current);
        pass("world_reopen", "read_before_write=true entities=1 units=6 xp=72 survivor=" + data.survivor);
        verifyNbtRoundTrip(survivor);
        finish();
    }

    private List<ExperienceOrb> orbs() {
        return level.getEntitiesOfClass(ExperienceOrb.class, ARENA, ExperienceOrb::isAlive);
    }

    private static Map<Integer, Integer> map(ExperienceOrb orb) {
        require(orb instanceof IClumpedOrb, "clumps_interface_not_injected");
        return ((IClumpedOrb) orb).clumps$getClumpedMap();
    }

    private static void verifyTotals(List<ExperienceOrb> orbs) {
        require(!orbs.isEmpty(), "all_orbs_lost");
        List<Map<Integer, Integer>> maps = new ArrayList<>();
        for (ExperienceOrb orb : orbs) {
            require(orb.getTags().contains(MOD_ID), "foreign_orb_in_arena");
            maps.add(map(orb));
        }
        OrbTotals totals;
        try {
            totals = OrbTotals.from(maps);
        } catch (RuntimeException malformedMap) {
            throw fail("invalid_clumped_map_" + malformedMap.getMessage());
        }
        require(totals.histogram().equals(EXPECTED), "histogram_not_conserved_" + new TreeMap<>(totals.histogram()));
        require(totals.units() == 6, "orb_units_not_conserved");
        require(totals.xp() == 72, "weighted_xp_not_conserved");
    }

    private void verifyNbtRoundTrip(ExperienceOrb survivor) {
        CompoundTag tag = survivor.saveWithoutId(new CompoundTag());
        require(tag.contains("clumpedMap", 10), "clumped_map_not_saved");
        CompoundTag saved = tag.getCompound("clumpedMap");
        Map<Integer, Integer> savedMap = new TreeMap<>();
        for (String key : saved.getAllKeys()) savedMap.put(Integer.parseInt(key), saved.getInt(key));
        require(savedMap.equals(EXPECTED), "saved_clumped_map_wrong");
        ExperienceOrb restored = new ExperienceOrb(EntityType.EXPERIENCE_ORB, level);
        restored.load(tag);
        require(map(restored).equals(EXPECTED), "nbt_roundtrip_clumped_map_wrong");
        verifyTotals(List.of(restored));
        // The restored comparison object is deliberately never added to the world.
        pass("nbt_roundtrip", "entities=1 units=6 xp=72 clumped_map=true in_memory=true");
    }

    private void finish() {
        finished = true;
        pass("ready_to_save", "phase=" + phase + " post_ticks=" + postTicks + " xp=72");
    }

    private static void require(boolean condition, String assertion) {
        if (!condition) throw fail(assertion);
    }

    private static IllegalStateException fail(String assertion) {
        String message = "UNIFIED_CLUMPS_PROBE FAIL assertion=" + assertion;
        System.err.println(message);
        return new IllegalStateException(message);
    }

    private static void pass(String stage, String detail) {
        System.out.println("UNIFIED_CLUMPS_PROBE PASS stage=" + stage + " " + detail);
    }

    private static final class ProbeData extends SavedData {
        private static final SavedData.Factory<ProbeData> FACTORY =
                new SavedData.Factory<>(ProbeData::new, ProbeData::load, null);
        private String marker = "";
        private UUID survivor;

        private static ProbeData load(CompoundTag tag, HolderLookup.Provider registries) {
            ProbeData data = new ProbeData();
            data.marker = tag.getString("marker");
            if (tag.hasUUID("survivor")) data.survivor = tag.getUUID("survivor");
            return data;
        }

        @Override
        public CompoundTag save(CompoundTag tag, HolderLookup.Provider registries) {
            tag.putString("marker", marker);
            if (survivor != null) tag.putUUID("survivor", survivor);
            return tag;
        }
    }
}
