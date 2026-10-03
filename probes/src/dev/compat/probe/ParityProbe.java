package dev.compat.probe;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.event.Event;
import net.fabricmc.fabric.api.event.EventFactory;
public final class ParityProbe implements ModInitializer {
 public void onInitialize() {
  int[] calls={0};
  Event<Runnable> event=EventFactory.createArrayBacked(Runnable.class, listeners -> () -> { for(Runnable listener:listeners)listener.run(); });
  event.register(()->calls[0]++); event.register(()->calls[0]+=2); event.invoker().run();
  int transformed=ProbeTarget.value();
  if(calls[0]!=3||transformed!=42)throw new IllegalStateException("Parity probe failed event="+calls[0]+" mixin="+transformed);
  System.out.println("COMPAT_PARITY_PROBE_OK event=3 mixin=42 entrypoint=1");
 }
}
