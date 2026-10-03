package dev.infinity.quiltprobe.mixin;
import dev.infinity.quiltprobe.QuiltProbe;
import java.util.function.BooleanSupplier;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
@Mixin(targets="net.minecraft.server.MinecraftServer")
public abstract class TickMixin {
    @Inject(method="method_3748(Ljava/util/function/BooleanSupplier;)V", at=@At("HEAD"))
    private void infinity$nativeQuiltTick(BooleanSupplier budget, CallbackInfo info) { QuiltProbe.mixinTicks++; }
}
