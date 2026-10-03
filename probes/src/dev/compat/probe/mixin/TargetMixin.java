package dev.compat.probe.mixin;
import dev.compat.probe.ProbeTarget;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
@Mixin(ProbeTarget.class)
public abstract class TargetMixin {
 @Inject(method="value",at=@At("HEAD"),cancellable=true,remap=false)
 private static void inject(CallbackInfoReturnable<Integer> callback) { callback.setReturnValue(42); }
}
