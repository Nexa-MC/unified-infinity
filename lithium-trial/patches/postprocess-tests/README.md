# Redirect and callback postprocessor regression checks

Run `bash lithium-trial/patches/postprocess-tests/run.sh` after building the experimental patch.
The classpath prioritizes the runtime's ASM 9.8 and Guava 32.1.2 over installer-only transitive JARs.

79 assertions cover real NeoForge LevelReader interface inheritance, BlockState superclass lookup,
symbolic receiver identity, rejection of inherited static/private and missing methods, and 16
static/instance × callback-used/unused × cancellable/noncancellable × void/nonvoid combinations.
The callback annotation list and original clean configuration must remain intact.
These are postprocessor tests; real handler Mixin application is covered by the server trials.
