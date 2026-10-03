package dev.compat.probe.mixin;
import java.util.function.BooleanSupplier;
import dev.compat.probe.TickMetrics;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
@Mixin(targets="net.minecraft.server.MinecraftServer")
public abstract class MinecraftTickMixin {
 @Unique private long infinity$tickStart;
 @Inject(method="method_3748(Ljava/util/function/BooleanSupplier;)V",at=@At("HEAD"))
 private void infinity$beforeTick(BooleanSupplier budget, CallbackInfo callback) { infinity$tickStart=System.nanoTime(); }
 @Inject(method="method_3748(Ljava/util/function/BooleanSupplier;)V",at=@At("RETURN"))
 private void infinity$afterTick(BooleanSupplier budget, CallbackInfo callback) { TickMetrics.record(System.nanoTime()-infinity$tickStart); }
}
