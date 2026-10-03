package org.sinytra.connector.mod;

import org.sinytra.connector.mod.compat.LateRenderTypesInit;
import org.sinytra.connector.mod.compat.LateSheetsInit;

public class ConnectorModClient {

    private ConnectorModClient() {}

    public static void onClientSetup() {
        LateRenderTypesInit.regenerateRenderTypeIds();
    }

    public static void onLoadComplete() {
        LateSheetsInit.completeSheetsInit();
    }
}
