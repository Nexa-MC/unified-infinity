package org.sinytra.connector.locator;

import org.sinytra.connector.infinity.inventory.*;
import java.io.IOException;
import java.nio.file.Path;
import java.util.*;
import static org.sinytra.connector.infinity.inventory.AdmissionInventory.*;

/** Consumes the single BOOT admission transaction; never starts another scan or trust registry. */
public final class OrdinaryAdmissionGate {
    private OrdinaryAdmissionGate() {}
    public static InfrastructurePolicy.Decision inspect(Path path, SourceChain ignoredSource) throws IOException {
        AdmissionSession session = AdmissionSession.current();
        session.requireKnown(path);
        InfrastructurePolicy.Decision decision = session.decision(path).orElseThrow();
        if (decision.action() == InfrastructurePolicy.Action.EXCLUDE) AdmittedModCatalog.recordExclusions(decision.exclusions());
        return decision;
    }
    public static boolean allow(Path path, SourceChain ignoredSource) throws IOException {
        AdmissionSession session = AdmissionSession.current();
        boolean admitted = session.permits(List.of(path));
        inspect(path, ignoredSource);
        return admitted;
    }
    public static SourceChain root(Path path) { return new SourceChain(path.toAbsolutePath().normalize().toString(), List.of()); }
}
