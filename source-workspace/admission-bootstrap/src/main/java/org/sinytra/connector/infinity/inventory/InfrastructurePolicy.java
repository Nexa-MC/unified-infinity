package org.sinytra.connector.infinity.inventory;

import java.nio.file.Path;
import java.util.*;
import static org.sinytra.connector.infinity.inventory.AdmissionInventory.*;

/** Audited primary-declaration rules only. Does not provide dependencies or execute candidate code. */
public final class InfrastructurePolicy {
    public enum Action { ADMIT, EXCLUDE, BLOCK_MIXED_FILE, REQUIRE_PRE_SERVICE_GATE }
    public record Rule(String id, Set<Ecosystem> ecosystems, Set<String> primaryIds, String reason, List<String> replacementIds) {
        public Rule { ecosystems = Set.copyOf(ecosystems); primaryIds = Set.copyOf(primaryIds); replacementIds = List.copyOf(replacementIds); }
    }
    public record Candidate(Path path, SourceChain source, Ecosystem ecosystem, List<String> primaryIds, boolean earlyServiceProvider) {
        public Candidate { primaryIds = List.copyOf(primaryIds); }
    }
    public record Decision(Action action, List<Exclusion> exclusions, List<String> unrelatedIds) {
        public Decision { exclusions = List.copyOf(exclusions); unrelatedIds = List.copyOf(unrelatedIds); }
        public boolean mayExecute() { return action == Action.ADMIT; }
    }
    private static final Set<Ecosystem> FABRIC = Set.of(Ecosystem.FABRIC);
    private static final Set<Ecosystem> QUILT = Set.of(Ecosystem.QUILT);
    private static final Set<Ecosystem> HOST = Set.of(Ecosystem.NEOFORGE, Ecosystem.FORGE);
    private static final List<Rule> RULES = buildRules();
    private static List<Rule> buildRules() {
        List<Rule> result = new ArrayList<>(List.of(
        new Rule("fabric-api-aggregate", FABRIC, Set.of("fabric-api"), "External Fabric API conflicts with the managed FFAPI profile", List.of("fabric_api")),
        new Rule("ffapi-aggregate", HOST, Set.of("fabric_api", "forgified_fabric_api"), "External FFAPI duplicates the managed API profile", List.of("fabric_api", "forgified_fabric_api")),
        new Rule("qfapi-aggregate", QUILT, Set.of("quilted_fabric_api"), "External QFAPI introduces another API runtime; full QFAPI compatibility is not supplied", List.of()),
        new Rule("qsl-base", QUILT, Set.of("quilt_base"), "External QSL base conflicts with the pinned managed base", List.of("quilt_base")),
        new Rule("qsl-lifecycle", QUILT, Set.of("quilt_lifecycle_events"), "External QSL lifecycle conflicts with the pinned managed lifecycle module", List.of("quilt_lifecycle_events")),
        new Rule("qsl-unsupported-modules", QUILT, AuditedInfrastructureIds.UNSUPPORTED_QSL, "External QSL module is excluded by the bounded profile; this API has no internal replacement", List.of()),
        new Rule("modmenu", FABRIC, Set.of("modmenu"), "Unified uses the host mod list; ModMenu configuration APIs are not replaced", List.of()),
        new Rule("connector", HOST, Set.of("connector", "connectormod"), "A second external loader bridge cannot own the Unified loading pipeline", List.of()),
        new Rule("connector-extras", HOST, Set.of("connectorextras", "connectorextras_modmenu_bridge", "modmenu"), "External Connector integrations are excluded; their integration APIs are not supplied by the built-in list", List.of())
    ));
        for (String id : new TreeSet<>(AuditedInfrastructureIds.FFAPI_MODULES))
            result.add(new Rule("ffapi-module:" + id, HOST, Set.of(id), "External FFAPI module conflicts with the managed profile", List.of(id)));
        return List.copyOf(result);
    }
    private InfrastructurePolicy() {}
    public static List<Rule> rules() { return RULES; }
    public static Decision evaluate(Candidate candidate) {
        if (TrustedPayloads.find(candidate.path(), candidate.primaryIds()).isPresent())
            return new Decision(Action.ADMIT, List.of(), List.of());
        List<Exclusion> hits = new ArrayList<>(); List<String> unrelated = new ArrayList<>();
        for (String id : candidate.primaryIds()) {
            Rule match = RULES.stream().filter(r -> r.ecosystems().contains(candidate.ecosystem()) && r.primaryIds().contains(id)).findFirst().orElse(null);
            if (match == null) unrelated.add(id);
            else hits.add(new Exclusion(candidate.source(), id, match.id(), match.reason(),
                match.replacementIds().isEmpty() ? Replacement.NO_API_REPLACEMENT : Replacement.NOT_VERIFIED,
                List.of(), candidate.earlyServiceProvider()));
        }
        if (hits.isEmpty()) return new Decision(Action.ADMIT, List.of(), List.of());
        // A late scanner must never advertise that an already admitted SERVICE provider was prevented from executing.
        Action action = candidate.earlyServiceProvider() ? Action.REQUIRE_PRE_SERVICE_GATE
            : unrelated.isEmpty() ? Action.EXCLUDE : Action.BLOCK_MIXED_FILE;
        return new Decision(action, hits, unrelated);
    }
    /** Notification enrichment only. Version ranges and API contracts remain the real host resolver's responsibility. */
    public static List<Exclusion> reconcileNotices(List<Exclusion> notices, Collection<String> selectedIds) {
        return notices.stream().map(n -> {
            Rule rule = RULES.stream().filter(r -> r.id().equals(n.ruleId())).findFirst().orElseThrow();
            List<String> present = rule.replacementIds().stream().filter(selectedIds::contains).toList();
            return new Exclusion(n.source(), n.originalId(), n.ruleId(), n.reason(),
                present.isEmpty() ? n.replacement() : Replacement.SELECTED_PROVIDER_PRESENT, present, n.earlyServiceProvider());
        }).toList();
    }
}
