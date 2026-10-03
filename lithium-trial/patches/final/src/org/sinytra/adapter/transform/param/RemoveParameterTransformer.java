package org.sinytra.adapter.transform.param;

import org.objectweb.asm.Type;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.LocalVariableNode;
import org.objectweb.asm.tree.MethodNode;
import org.sinytra.adapter.env.ctx.MixinContext;
import org.sinytra.adapter.analysis.locals.LVTSnapshot;
import org.sinytra.adapter.env.ctx.PatchResult;
import org.sinytra.adapter.util.AdapterUtil;

import java.util.List;

public record RemoveParameterTransformer(int index, boolean invalidateUsage) implements ParameterTransformer {
    public RemoveParameterTransformer(int index) {
        this(index, true);
    }

    @Override
    public PatchResult apply(ClassNode classNode, MethodNode methodNode, MixinContext context, List<Type> parameters, int offset) {
        final int target = this.index() + offset;
        validateParameterAnnotations(methodNode, parameters.size());
        final int lvtIndex = ParamTransformationUtil.calculateLVTIndex(parameters, !context.isStatic(), target);

        LVTSnapshot.with(methodNode, () -> {
            LocalVariableNode lvn = methodNode.localVariables.stream()
                .filter(v -> v.index == lvtIndex)
                .findFirst()
                .orElse(null);
            if (lvn != null) {
                methodNode.localVariables.remove(lvn);
                if (this.invalidateUsage) {
                    AdapterUtil.replaceLVT(methodNode, idx -> idx == lvtIndex ? -1 : idx);
                }
            }
        });

        methodNode.parameters.remove(target);
        removeParameterAnnotations(methodNode, target);
        parameters.remove(target);

        return PatchResult.COMPUTE_FRAMES;
    }

    // ASM stores attribute counts independently from arrays. Keep the existing
    // descriptor-coordinate annotation placement, removing only this parameter.
    // Reduced-count attributes can use non-descriptor indices (synthetic params);
    // refuse those ambiguous layouts rather than guessing and moving annotations.
    static void validateParameterAnnotations(MethodNode method, int parameterCount) {
        validateAnnotationLayout(method.visibleParameterAnnotations, method.visibleAnnotableParameterCount, parameterCount);
        validateAnnotationLayout(method.invisibleParameterAnnotations, method.invisibleAnnotableParameterCount, parameterCount);
    }

    private static void validateAnnotationLayout(List<?>[] annotations, int count, int parameters) {
        if (annotations != null && (annotations.length != parameters || (count != 0 && count != parameters))) {
            throw new IllegalArgumentException("Cannot remove parameter from non-descriptor-coordinate annotation layout");
        }
    }

    static void removeParameterAnnotations(MethodNode method, int target) {
        method.visibleParameterAnnotations = AdapterUtil.removeArrayElement(method.visibleParameterAnnotations, target, List[]::new);
        method.invisibleParameterAnnotations = AdapterUtil.removeArrayElement(method.invisibleParameterAnnotations, target, List[]::new);
        if (method.visibleAnnotableParameterCount > 0) method.visibleAnnotableParameterCount--;
        if (method.invisibleAnnotableParameterCount > 0) method.invisibleAnnotableParameterCount--;
    }
}
