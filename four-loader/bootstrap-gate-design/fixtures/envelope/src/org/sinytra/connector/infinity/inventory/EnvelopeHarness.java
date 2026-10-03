package org.sinytra.connector.infinity.inventory;
import java.nio.file.*;
import java.util.*;
import net.neoforged.fml.loading.ModDirTransformerDiscoverer;

/** Only canonical metadata scanning/discovery. Never initializes any official Connector provider. */
public final class EnvelopeHarness {
    public static void main(String[] args) throws Exception {
        Path root=Path.of(args[0]).toRealPath(); String mode=args[1];
        Path outer=root.resolve("game/mods/connector.jar"); String before=BootstrapInstallation.sha256(outer);
        var artifacts=new ArrayList<BootstrapInstallation.Artifact>();
        artifacts.add(new BootstrapInstallation.Artifact("owner.jar","SELF",List.of(),"BOOT_OWNER"));
        var embedded=new ArrayList<BootstrapInstallation.Embedded>();
        if(mode.equals("trusted")) {
            artifacts.add(new BootstrapInstallation.Artifact("game/mods/connector.jar",before,List.of(),"MANAGED_ROOT"));
            embedded.add(new BootstrapInstallation.Embedded("game/mods/connector.jar",List.of("META-INF/jarjar/runtime-1.0.0+1.21.1.jar"),"36de91a417138f01a1801b7e2ae59bb1052c8ddb23b1352d3fe952b3d33a5e06",List.of(),"PLATFORM",null));
            embedded.add(new BootstrapInstallation.Embedded("game/mods/connector.jar",List.of("META-INF/jarjar/org.sinytra.connector-2.0.0-beta.17+1.21.1-mod.jar"),"0bd1b42d10a78152287935b02b06554478e4f38fad3e5fce334a9e7efc920266",List.of("connector"),"PLATFORM",null));
        }
        var policy=new BootstrapInstallation.Policy(1,true,root.resolve("game").toString(),root.toString(),"neoforgeclient","test-only",Map.of(),Map.of(),artifacts,embedded,List.of(),"envelope-test");
        AdmissionSession session=AdmissionSession.initialize(policy);
        var action=session.decision(outer).orElseThrow().action();
        if(mode.equals("official")) {
            check(action==InfrastructurePolicy.Action.EXCLUDE,"exact release must exclude whole envelope");
            check(new ModDirTransformerDiscoverer().candidates(root.resolve("game")).isEmpty(),"official provider must not enter SERVICE");
            check(session.decision(outer).orElseThrow().exclusions().stream().anyMatch(e->e.originalId().equals("connector")&&!e.source().embeddedEntries().isEmpty()),"original nested descriptor attribution lost");
        } else if(mode.equals("trusted")) {
            check(action==InfrastructurePolicy.Action.ADMIT,"exact installed pinned origin must bypass external envelope rule");
            check(new ModDirTransformerDiscoverer().candidates(root.resolve("game")).size()==1,"trusted root missing");
        } else {
            check(action==InfrastructurePolicy.Action.BLOCK_MIXED_FILE,"different/mixed envelope must remain explicitly unsupported");
            try {session.permits(List.of(outer));throw new AssertionError("unsupported envelope was silently allowed");}
            catch(IllegalStateException expected) {check(expected.getMessage().contains("Unsupported mixed"),"wrong failure");}
        }
        check(BootstrapInstallation.sha256(outer).equals(before),"original test archive changed");
        System.out.println("PASS envelope="+mode+" action="+action+" unchanged=true officialProvidersExecuted=false");
    }
    private static void check(boolean condition,String message) {if(!condition)throw new AssertionError(message);}
}
