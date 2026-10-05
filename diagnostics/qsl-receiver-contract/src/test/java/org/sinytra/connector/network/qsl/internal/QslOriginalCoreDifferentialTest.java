/* Self-authored MIT harness; see LICENSES/Project-MIT.txt. */
package org.sinytra.connector.network.qsl.internal;

import java.util.*;
import java.util.function.Function;
import net.minecraft.class_2539;
import net.minecraft.class_2598;
import net.minecraft.class_8710;
import org.quiltmc.qsl.networking.impl.*;

/** Executes unchanged original alpha.5 core, with external types explicitly doubled. */
public final class QslOriginalCoreDifferentialTest {
    enum H implements QslPlayReceivers.Receiver {
        FIRST, SECOND, LOCAL;
        public void receive(QslPlayConnection connection, Object payload) {}
    }
    interface Engine {
        boolean global(String id, H h);
        H unglobal(String id);
        boolean local(int n, String id, H h);
        H unlocal(int n, String id);
        Map<String,H> globals();
        Set<String> globalChannels();
        Map<String,H> locals(int n);
        Set<String> localChannels(int n);
        void stop(int n);
        void available(boolean value);
        int validations();
    }
    static final class Original implements Engine {
        final PayloadTypeRegistryImpl<Object> payloads = new PayloadTypeRegistryImpl<>();
        final GlobalReceiverRegistry<H> registry = new GlobalReceiverRegistry<>(class_2598.SERVERBOUND, class_2539.PLAY, payloads);
        final List<Addon> addons = List.of(new Addon(registry), new Addon(registry));
        Original() { addons.forEach(registry::startSession); }
        static class_8710.class_9154<?> id(String s) { return s == null ? null : new class_8710.class_9154<>(s); }
        public boolean global(String s,H h) { return registry.registerGlobalReceiver(id(s),h); }
        public H unglobal(String s) { return registry.unregisterGlobalReceiver(id(s)); }
        public boolean local(int n,String s,H h) { return addons.get(n).registerChannel(id(s),h); }
        public H unlocal(int n,String s) { return addons.get(n).unregisterChannel(id(s)); }
        public Map<String,H> globals() {
            var result = new TreeMap<String,H>(); registry.getReceivers().forEach((k,v)->result.put(k.toString(),v)); return result;
        }
        public Set<String> globalChannels() {
            var result = new TreeSet<String>(); registry.getChannels().forEach(k->result.add(k.toString())); return result;
        }
        public Map<String,H> locals(int n) {
            var result = new TreeMap<String,H>(); var a=addons.get(n);
            a.getReceivableChannels().forEach(k->result.put(k.toString(),a.getHandler(k))); return result;
        }
        public Set<String> localChannels(int n) {
            var result = new TreeSet<String>(); addons.get(n).getReceivableChannels().forEach(k->result.add(k.toString())); return result;
        }
        public void stop(int n) { registry.endSession(addons.get(n)); }
        public void available(boolean v) { payloads.available=v; }
        public int validations() { return payloads.lookups; }
        static final class Addon extends AbstractNetworkAddon<H> {
            Addon(GlobalReceiverRegistry<H> r) { super(r,"qsl-original-core-contract"); }
            protected void handleRegistration(class_8710.class_9154<?> id) {}
            protected void handleUnregistration(class_8710.class_9154<?> id) {}
            protected void invokeDisconnectEvent() {}
            protected boolean isReservedChannel(class_8710.class_9154<?> id) { return NetworkingImpl.isReservedCommonChannel(id); }
        }
    }
    static final class Candidate implements Engine {
        int checks;
        boolean hasType=true;
        final QslPlayReceivers registry = new QslPlayReceivers(QslPlayReceivers.ReceiveSide.SERVER_C2S, id->{
            checks++;
            if (!hasType) throw new IllegalArgumentException("Fixture payload type absent");
        });
        final List<QslPlayConnection> sessions = List.of(connect(),connect());
        QslPlayConnection connect() { return new QslPlayConnection(registry,new NoOpHost(),new ArrayList<>()); }
        static PlayChannelId id(String s) { return s==null ? null : new PlayChannelId(s); }
        public boolean global(String s,H h) { return registry.registerGlobal(id(s),h); }
        public H unglobal(String s) { return (H)registry.unregisterGlobal(id(s)); }
        public boolean local(int n,String s,H h) { return sessions.get(n).registerLocal(id(s),h); }
        public H unlocal(int n,String s) { return (H)sessions.get(n).unregisterLocal(id(s)); }
        public Map<String,H> globals() {
            var result=new TreeMap<String,H>(); registry.globalReceiversSnapshot().forEach((k,v)->result.put(k.value(),(H)v)); return result;
        }
        public Set<String> globalChannels() {
            var result=new TreeSet<String>();registry.globalChannelsSnapshot().forEach(k->result.add(k.value()));return result;
        }
        public Map<String,H> locals(int n) {
            var result=new TreeMap<String,H>();var a=sessions.get(n);
            a.receivableChannelsSnapshot().forEach(k->result.put(k.value(),(H)a.receiver(k)));return result;
        }
        public Set<String> localChannels(int n) {
            var result=new TreeSet<String>();sessions.get(n).receivableChannelsSnapshot().forEach(k->result.add(k.value()));return result;
        }
        public void stop(int n) { registry.endSession(sessions.get(n)); }
        public void available(boolean v) { hasType=v; }
        public int validations() { return checks; }
    }
    static final class NoOpHost implements QslPlayConnection.HostHooks {
        public boolean isReceivingEventLoop(){return true;}
        public void executeOnGameThread(Runnable r){throw new AssertionError("Outside core scope");}
        public void onInit(QslPlayConnection c){}
        public void onJoin(QslPlayConnection c){}
        public void onDisconnect(QslPlayConnection c){}
        public void onPeerChannels(QslPlayConnection c,List<PlayChannelId> ids,boolean register){throw new AssertionError("Outside core scope");}
        public void advertiseReceivers(QslPlayConnection c,List<PlayChannelId> ids,boolean register){throw new AssertionError("Outside core scope");}
    }
    record Failure(String type) {}
    static Object result(Engine e,Function<Engine,Object> action) {
        try{return action.apply(e);}catch(RuntimeException x){return new Failure(x.getClass().getName());}
    }
    static final class Pair {
        final Engine original=new Original(),candidate=new Candidate();
        final String name;
        Pair(String name){this.name=name;}
        void step(String label,Function<Engine,Object> op,Object expected) {
            Object a=result(original,op),b=result(candidate,op);
            equal(a,b,name+": "+label+" differential return");equal(a,expected,name+": "+label+" upstream expectation");
            equal(state(original),state(candidate),name+": "+label+" differential state");
        }
        List<Object> state(Engine e){return List.of(e.globals(),e.globalChannels(),e.locals(0),e.locals(1),e.localChannels(0),e.localChannels(1),e.validations());}
    }
    static void equal(Object a,Object b,String message){if(!Objects.equals(a,b))throw new AssertionError(message+" original="+a+" other="+b);}
    public static void main(String[] ignored) {
        Pair p=new Pair("global putIfAbsent and two-session propagation");
        p.step("insert",e->e.global("probe:a",H.FIRST),true);
        p.step("duplicate",e->e.global("probe:a",H.SECOND),false);
        p.step("both propagated",e->List.of(e.locals(0).get("probe:a"),e.locals(1).get("probe:a")),List.of(H.FIRST,H.FIRST));
        p=new Pair("local putIfAbsent and late global");
        p.step("local",e->e.local(0,"probe:a",H.LOCAL),true);
        p.step("local duplicate",e->e.local(0,"probe:a",H.SECOND),false);
        p.step("late global",e->e.global("probe:a",H.FIRST),true);
        p.step("local preserved",e->List.of(e.locals(0).get("probe:a"),e.locals(1).get("probe:a")),List.of(H.LOCAL,H.FIRST));
        p.step("global removal",e->e.unglobal("probe:a"),H.FIRST);
        p.step("local also removed",e->e.locals(0).isEmpty()&&e.locals(1).isEmpty(),true);
        p=new Pair("local removal has no global fallback or duplicate recopy");
        p.step("global",e->e.global("probe:a",H.FIRST),true);
        p.step("remove local",e->e.unlocal(0,"probe:a"),H.FIRST);
        p.step("duplicate global",e->e.global("probe:a",H.SECOND),false);
        p.step("no fallback",e->e.locals(0).get("probe:a"),null);
        p.step("other retained",e->e.locals(1).get("probe:a"),H.FIRST);
        p=new Pair("absent global still validates without local removal");
        p.step("local",e->e.local(0,"probe:a",H.LOCAL),true);
        p.step("absent global",e->e.unglobal("probe:a"),null);
        p.step("validator called",Engine::validations,1);
        p.step("local retained",e->e.locals(0).get("probe:a"),H.LOCAL);
        p=new Pair("validation failure precedes mutation");
        p.step("global",e->e.global("probe:a",H.FIRST),true);
        p.step("disable type",e->{e.available(false);return null;},null);
        p.step("unregister fails",e->e.unglobal("probe:a"),new Failure(IllegalArgumentException.class.getName()));
        p.step("global retained",e->e.globals().get("probe:a"),H.FIRST);
        p.step("registration does not validate",e->e.global("probe:b",H.SECOND),true);
        p=new Pair("ended session is no longer updated");
        p.step("existing global",e->e.global("probe:a",H.FIRST),true);
        p.step("end",e->{e.stop(0);return null;},null);
        p.step("remove global",e->e.unglobal("probe:a"),H.FIRST);
        p.step("ended retains existing",e->e.locals(0).get("probe:a"),H.FIRST);
        p.step("new global",e->e.global("probe:b",H.SECOND),true);
        p.step("ended ignores new",e->e.locals(0).get("probe:b"),null);
        p=new Pair("absent local removal");
        p.step("missing",e->e.unlocal(0,"probe:a"),null);
        p.step("no payload validation",Engine::validations,0);
        for(String reserved:List.of("minecraft:register","minecraft:unregister")) {
            p=new Pair("reserved "+reserved);
            Failure failure=new Failure(IllegalArgumentException.class.getName());
            p.step("global register",e->e.global(reserved,H.FIRST),failure);
            p.step("global unregister",e->e.unglobal(reserved),failure);
            p.step("local register",e->e.local(0,reserved,H.FIRST),failure);
            p.step("local unregister",e->e.unlocal(0,reserved),failure);
            p.step("no validation",Engine::validations,0);
        }
        p=new Pair("null arguments");
        Failure npe=new Failure(NullPointerException.class.getName());
        p.step("global ID",e->e.global(null,H.FIRST),npe);
        p.step("global handler",e->e.global("probe:a",null),npe);
        p.step("global remove ID",e->e.unglobal(null),npe);
        p.step("local ID",e->e.local(0,null,H.FIRST),npe);
        p.step("local handler",e->e.local(0,"probe:a",null),npe);
        p.step("local remove ID",e->e.unlocal(0,null),npe);
        System.out.println("10 original-core differential scenarios passed against unchanged QSL alpha.5; no native runtime acceptance claim");
    }
}
