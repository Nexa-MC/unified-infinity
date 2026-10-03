/*
 * Copyright 2022-2023 QuiltMC
 * SPDX-License-Identifier: Apache-2.0
 * Adapted for native-quilt-v1: bounded SPDX data copied from the pinned
 * Quilt Loader 0.30.1 quilt_loader/licenses.json, not a network lookup.
 */
package org.sinytra.connector.quilt.metadata.qmj;

import org.quiltmc.loader.api.ModLicense;
import java.util.Map;

/** License details for the pinned/probe profile. Unknown identifiers retain the public null/default contract. */
public record ModLicenseImpl(String name, String id, String url, String description) implements ModLicense {
    private static final Map<String, ModLicense> KNOWN = Map.ofEntries(
        Map.entry("Apache-2.0", new ModLicenseImpl("Apache License 2.0","Apache-2.0","https://spdx.org/licenses/Apache-2.0.html","")),
        Map.entry("MIT", new ModLicenseImpl("MIT License","MIT","https://spdx.org/licenses/MIT.html","")),
        Map.entry("LGPL-3.0-only", new ModLicenseImpl("GNU Lesser General Public License v3.0 only","LGPL-3.0-only","https://spdx.org/licenses/LGPL-3.0-only.html","")),
        Map.entry("LGPL-3.0-or-later", new ModLicenseImpl("GNU Lesser General Public License v3.0 or later","LGPL-3.0-or-later","https://spdx.org/licenses/LGPL-3.0-or-later.html","")),
        Map.entry("CC0-1.0", new ModLicenseImpl("Creative Commons Zero v1.0 Universal","CC0-1.0","https://spdx.org/licenses/CC0-1.0.html",""))
    );
    public static ModLicense fromIdentifier(String identifier) { return KNOWN.get(identifier); }
    public static ModLicense fromIdentifierOrDefault(String identifier) {
        ModLicense license = fromIdentifier(identifier);
        return license == null ? new ModLicenseImpl(identifier, identifier, "", "") : license;
    }
}
