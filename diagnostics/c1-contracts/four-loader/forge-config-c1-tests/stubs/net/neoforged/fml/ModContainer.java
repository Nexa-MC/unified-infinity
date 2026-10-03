package net.neoforged.fml;
public class ModContainer {
 private final String id; public final java.util.List<net.neoforged.bus.api.Event> events=new java.util.concurrent.CopyOnWriteArrayList<>();
 public java.util.function.Consumer<net.neoforged.bus.api.Event> listener=e->{};
 public ModContainer(String id){this.id=id;} public String getModId(){return id;}
 public net.neoforged.bus.api.IEventBus getEventBus(){return null;}
 public final <T extends net.neoforged.bus.api.Event & net.neoforged.fml.event.IModBusEvent> void acceptEvent(T event){events.add(event);listener.accept(event);}
}
