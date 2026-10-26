// SPDX-License-Identifier: MIT
package dev.infinity.forgeplaydriver;

import java.io.FileDescriptor;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.PrintStream;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.EnumSet;
import java.util.UUID;
import java.util.function.BiConsumer;
import java.util.regex.Pattern;
import net.minecraft.network.Connection;
import net.minecraft.network.ConnectionProtocol;
import net.minecraft.network.chat.Component;
import net.minecraft.network.protocol.PacketFlow;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.common.Mod;
import net.neoforged.fml.loading.FMLPaths;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.server.ServerStartedEvent;
import dev.infinity.forgeplayprobe.PlayProbe;


/** Common entrypoint. No client classes, client method references, or client imports. */
@Mod(ForgePlayDriver.MOD_ID)
public final class ForgePlayDriver {
    public static final String MOD_ID = "forge_play_driver";
    static final UUID PLAYER_UUID = UUID.fromString("dd29b97d-cafa-3d53-94e1-f85f75bcf1f6");
    static final String PLAYER_NAME = "APILocal";
    private static final long PID = ProcessHandle.current().pid();
    private static final long START_TICKS = readStartTicks();
    // Minecraft redirects System.out through logging; keep protocol markers at column zero.
    // Never close this stream: the descriptor belongs to the supervised game process.
    private static final PrintStream OUTPUT = new PrintStream(
            new FileOutputStream(FileDescriptor.out), true, StandardCharsets.US_ASCII);
    private static final EnumSet<Role> FAILED = EnumSet.noneOf(Role.class);
    private static final EnumSet<Role> WRITTEN = EnumSet.noneOf(Role.class);
    private static volatile BiConsumer<PlayProbe.Echo, Connection> clientReply;
    private static final Pattern INPUT = Pattern.compile(
            "\\{\"schema\":1,\"nonce\":([1-9][0-9]{0,18}),\"sequence\":1,\"port\":(25631|25632)\\}\\n");
    private static final Pattern RELEASE = Pattern.compile(
            "\\{\"schema\":1,\"nonce\":([1-9][0-9]{0,18}),\"sequence\":1\\}\\n");
    private MinecraftServer server;
    private int counter;

    enum Role {
        CLIENT("client", "forge-play-client-result.json"),
        SERVER("server", "forge-play-server-result.json");
        final String wire;
        final String output;
        Role(String wire, String output) { this.wire = wire; this.output = output; }
    }
    record Input(long nonce, int port) {}
    static final class ProbeFailure extends RuntimeException {
        final String code;
        ProbeFailure(String code) { super(code); this.code = code; }
    }

    public ForgePlayDriver(IEventBus modBus) {
        PlayProbe.observe(new PlayProbe.Observer() {
            public int serverNonce(PlayProbe.Nonce nonce, Connection connection, ServerPlayer sender) {
                return request(nonce, connection, sender);
            }
            public void clientEcho(PlayProbe.Echo echo, Connection connection) {
                var callback = clientReply;
                require(callback != null, "callback_missing");
                callback.accept(echo, connection);
            }
            public void failed(boolean server, Throwable failure) {
                fail(server ? Role.SERVER : Role.CLIENT, "forge_callback_failure");
            }
        });
        NeoForge.EVENT_BUS.addListener(this::serverStarted);
    }
    static synchronized void installClientReply(BiConsumer<PlayProbe.Echo, Connection> callback) {
        require(clientReply == null, "callback_duplicate");
        clientReply = java.util.Objects.requireNonNull(callback);
    }

    private void serverStarted(ServerStartedEvent event) {
        try {
            require(server == null, "server_duplicate");
            server = event.getServer();
            require(server.isDedicatedServer(), "server_not_dedicated");
            require(server.isSameThread(), "server_wrong_thread");
            requirePort(server.getPort());
            requireFresh();
            require(!Files.exists(profile("forge-play-input.json"), LinkOption.NOFOLLOW_LINKS),
                    "server_has_nonce_input");
            emit("FORGE_PLAY_READY", identity(Role.SERVER)
                    + ",\"port\":" + server.getPort()
                    + ",\"main_thread\":true,\"dedicated_server\":true}");
        } catch (RuntimeException exception) {
            fail(Role.SERVER, code(exception, "server_setup_failure"));
        }
    }

    private int request(PlayProbe.Nonce payload, Connection connection, ServerPlayer player) {
        try {
            require(!hasFailed(Role.SERVER), "server_already_failed");
            require(server != null && server.isDedicatedServer(), "server_not_dedicated");
            require(server.isSameThread(), "server_wrong_thread");
            require(connection.getPacketListener().protocol() == ConnectionProtocol.PLAY
                    && connection.getReceiving() == PacketFlow.SERVERBOUND, "server_wrong_direction");
            require(player != null && player.getServer() == server, "server_wrong_instance");
            require(player.connection.getConnection() == connection, "server_wrong_connection");
            require(PLAYER_UUID.equals(player.getUUID()) && PLAYER_NAME.equals(player.getGameProfile().getName()),
                    "server_wrong_identity");
            requireRemote(connection, server.getPort(), false);
            require(payload.value() > 0 && payload.sequence() == 1, "server_payload");
            require(counter == 0, "server_duplicate_request");
            int before = counter;
            counter = Math.addExact(counter, 1);
            require(before == 0 && counter == 1, "server_counter");
            pass(Role.SERVER, payload.value(), server.getPort(), connection.getPacketListener().protocol(), connection.getReceiving());
            return counter;
        } catch (RuntimeException exception) {
            fail(Role.SERVER, code(exception, "server_handler_failure"));
            connection.disconnect(Component.literal("forge_play_driver:server_failure"));
            throw exception;
        }
    }

    static void requireRemote(Connection connection, int port, boolean client) {
        requirePort(port);
        require(connection != null && connection.isConnected(), "connection_closed");
        require(!connection.isMemoryConnection(), "memory_connection");
        requireLoopback(connection.getRemoteAddress());
        requireLoopback(connection.channel().localAddress());
        var address = (InetSocketAddress) (client ? connection.getRemoteAddress() : connection.channel().localAddress());
        require(address.getPort() == port, "wrong_port");
    }

    private static void requireLoopback(SocketAddress address) {
        require(address instanceof InetSocketAddress, "not_tcp_address");
        var inet = (InetSocketAddress) address;
        require(!inet.isUnresolved() && inet.getAddress().isLoopbackAddress()
                && "127.0.0.1".equals(inet.getAddress().getHostAddress()), "not_ipv4_loopback");
    }

    static void require(boolean condition, String code) {
        if (!condition) throw new ProbeFailure(code);
    }
    static void requirePort(int port) { require(port == 25631 || port == 25632, "wrong_port"); }
    static String code(RuntimeException exception, String fallback) {
        return exception instanceof ProbeFailure known ? known.code : fallback;
    }
    private static Path profile(String fixedName) { return FMLPaths.GAMEDIR.get().resolve(fixedName); }

    static Input readInput() {
        return parseInput(readBounded(profile("forge-play-input.json"), 128));
    }
    static Input parseInput(String text) {
        var match = INPUT.matcher(text);
        require(match.matches(), "input_schema");
        try { return new Input(Long.parseLong(match.group(1)), Integer.parseInt(match.group(2))); }
        catch (NumberFormatException exception) { throw new ProbeFailure("input_nonce_range"); }
    }
    static boolean releasePresent() {
        return Files.exists(profile("forge-play-release.json"), LinkOption.NOFOLLOW_LINKS);
    }
    static void requireRelease(long nonce) {
        var match = RELEASE.matcher(readBounded(profile("forge-play-release.json"), 96));
        require(match.matches(), "release_schema");
        try { require(Long.parseLong(match.group(1)) == nonce, "release_nonce"); }
        catch (NumberFormatException exception) { throw new ProbeFailure("release_nonce_range"); }
    }
    private static String readBounded(Path path, int limit) {
        try {
            require(Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS), "input_not_regular");
            try (var stream = Files.newInputStream(path, LinkOption.NOFOLLOW_LINKS)) {
                byte[] bytes = stream.readNBytes(limit + 1);
                require(bytes.length <= limit, "input_too_large");
                for (byte value : bytes) require(value >= 0, "input_not_ascii");
                return new String(bytes, StandardCharsets.US_ASCII);
            }
        } catch (IOException exception) { throw new ProbeFailure("input_io"); }
    }
    static void requireFresh() {
        for (Role outputRole : Role.values()) {
            require(!Files.exists(profile(outputRole.output), LinkOption.NOFOLLOW_LINKS)
                    && !Files.exists(profile(outputRole.output + ".tmp"), LinkOption.NOFOLLOW_LINKS), "stale_result");
        }
        require(!releasePresent(), "stale_release");
    }
    private static long readStartTicks() {
        String stat = readBounded(Path.of("/proc/self/stat"), 4096);
        int end = stat.lastIndexOf(')');
        require(end > 0, "process_identity");
        String[] fields = stat.substring(end + 2).strip().split("\\s+");
        require(fields.length > 19, "process_identity");
        long ticks = Long.parseLong(fields[19]);
        require(ticks > 0, "process_identity");
        return ticks;
    }
    static synchronized boolean hasFailed(Role role) { return FAILED.contains(role); }
    private static String identity(Role role) {
        return "{\"schema\":1,\"role\":\"" + role.wire + "\",\"pid\":" + PID + ",\"start_ticks\":" + START_TICKS;
    }
    static synchronized void pass(Role role, long nonce, int port, ConnectionProtocol phase, PacketFlow flow) {
        require(!FAILED.contains(role), "already_failed");
        require(!WRITTEN.contains(role), "duplicate_result");
        String direction = directionFields(role, phase, flow);
        String json = identity(role) + ",\"status\":\"PASS\",\"nonce\":" + nonce + direction
                + ",\"sequence\":1,\"counter_before\":0,\"counter_after\":1,\"player_uuid\":\"" + PLAYER_UUID
                + "\",\"player_name\":\"APILocal\",\"port\":" + port
                + ",\"main_thread\":true,\"loopback\":true,\"memory_connection\":false,\"dedicated_server\":"
                + (role == Role.SERVER) + ",\"remote_join\":" + (role == Role.CLIENT) + ",\"code\":\"ok\"}";
        writeResult(role, json);
        emit("FORGE_PLAY_JSON", json);
    }
    static String directionFields(Role role, ConnectionProtocol phase, PacketFlow flow) {
        require(phase == ConnectionProtocol.PLAY
                && flow == (role == Role.SERVER ? PacketFlow.SERVERBOUND : PacketFlow.CLIENTBOUND), "result_direction");
        return ",\"phase\":\"" + phase.name() + "\",\"flow\":\"" + flow.name() + "\"";
    }
    static synchronized void fail(Role role, String code) {
        if (!FAILED.add(role)) return;
        String json = identity(role) + ",\"status\":\"FAIL\",\"code\":\"" + code + "\"}";
        emit("FORGE_PLAY_JSON", json);
        try { writeResult(role, json); }
        catch (RuntimeException exception) { System.err.println("FORGE_PLAY_FILE_ERROR"); }
    }
    static void disconnected(long nonce) {
        emit("FORGE_PLAY_DISCONNECTED", identity(Role.CLIENT) + ",\"nonce\":" + nonce
                + ",\"sequence\":1,\"player_uuid\":\"" + PLAYER_UUID + "\",\"code\":\"ok\"}");
    }
    private static void writeResult(Role role, String json) {
        byte[] bytes = (json + "\n").getBytes(StandardCharsets.US_ASCII);
        require(bytes.length <= 2048, "result_too_large");
        Path target = profile(role.output);
        Path temporary = profile(role.output + ".tmp");
        require(!Files.isSymbolicLink(target), "result_symlink");
        require(WRITTEN.contains(role) || !Files.exists(target, LinkOption.NOFOLLOW_LINKS), "stale_result");
        try {
            Files.write(temporary, bytes, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS);
            Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            WRITTEN.add(role);
        } catch (IOException exception) { throw new ProbeFailure("result_io"); }
    }
    private static void emit(String marker, String json) {
        require(json.length() <= 2048, "result_too_large");
        OUTPUT.println(marker + " " + json);
    }
}
