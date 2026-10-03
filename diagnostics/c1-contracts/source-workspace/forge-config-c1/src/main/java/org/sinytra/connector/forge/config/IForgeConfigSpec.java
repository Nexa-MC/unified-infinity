/*
 * Copyright (c) Forge Development LLC and contributors
 * SPDX-License-Identifier: LGPL-2.1-only
 */

package org.sinytra.connector.forge.config;

import com.electronwill.nightconfig.core.CommentedConfig;
import com.electronwill.nightconfig.core.UnmodifiableConfig;

public interface IForgeConfigSpec<T extends IForgeConfigSpec<T>> extends UnmodifiableConfig {
    @SuppressWarnings("unchecked")
    default T self() {
        return (T) this;
    }

    void acceptConfig(CommentedConfig data);

    boolean isCorrecting();

    boolean isCorrect(CommentedConfig commentedFileConfig);

    int correct(CommentedConfig commentedFileConfig);

    void afterReload();
}
