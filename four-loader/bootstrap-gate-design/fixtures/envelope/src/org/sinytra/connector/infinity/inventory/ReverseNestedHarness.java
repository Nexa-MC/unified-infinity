package org.sinytra.connector.infinity.inventory;
import java.nio.file.*;
import java.util.*;
/** Fail closed when excluding an API envelope would hide unrelated content below it. */
public final class ReverseNestedHarness {
    public static void main(String[] args)throws Exception {
        Path root=Path.of(args[0]).toRealPath(),parent=root.resolve("game/mods/parent.jar");String mode=args[1];String before=BootstrapInstallation.sha256(parent);
        var policy=new BootstrapInstallation.Policy(1,true,root.resolve("game").toString(),root.toString(),"neoforgeclient","test-only",Map.of(),Map.of(),List.of(new BootstrapInstallation.Artifact("owner.jar","SELF",List.of(),"BOOT_OWNER")),List.of(),List.of(),"reverse-nested-test");
        var session=AdmissionSession.initialize(policy);var decision=session.decision(parent).orElseThrow();
        if(mode.equals("support-library")) {
            check(decision.action()==InfrastructurePolicy.Action.EXCLUDE,"API with only private support library should still skip");
            check(session.admittedFolder(root.resolve("game/mods")).isEmpty(),"excluded API unexpectedly exposed");
        } else {
            check(decision.action()==InfrastructurePolicy.Action.BLOCK_MIXED_FILE,"unrelated nested content must not be silently hidden");
            check(decision.unrelatedIds().contains("fixture_content"),"actual unrelated ID must remain observable");
            try{session.admittedFolder(root.resolve("game/mods"));throw new AssertionError("mixed parent was exposed");}catch(IllegalStateException expected){check(expected.getMessage().contains("Unsupported mixed"),"wrong failure");}
        }
        check(BootstrapInstallation.sha256(parent).equals(before),"original container changed");
        System.out.println("PASS reverse="+mode+" action="+decision.action()+" originalUnchanged=true");
    }
    private static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
}
