/*
 * Copyright (c) Forge Development LLC and contributors
 * SPDX-License-Identifier: LGPL-2.1-only
 */

package net.minecraftforge.fart.internal;

import net.minecraftforge.fart.api.ClassProvider;
import org.jetbrains.annotations.Nullable;

import java.io.IOException;
import java.io.InputStream;
import java.util.Optional;

public class ClassLoaderClassProvider implements ClassProvider {
    private final ClassLoader classLoader;

    public ClassLoaderClassProvider(@Nullable ClassLoader classLoader) {
        this.classLoader = classLoader == null ? this.getClass().getClassLoader() : classLoader;
    }

    @Override
    public Optional<? extends IClassInfo> getClass(String name) {
        try {
            Class<?> cls = Class.forName(name.replace('/', '.'), false, this.classLoader);
            return Optional.of(new ClassProviderImpl.ClassInfo(cls));
        } catch (ClassNotFoundException | NoClassDefFoundError ex) {
            return Optional.empty();
        }
    }

    @Override
    public Optional<byte[]> getClassBytes(String cls) {
        String resource = cls + ".class";
        try(InputStream is = this.classLoader.getResourceAsStream(resource)) {
            if (is != null) {
                return Optional.of(Util.toByteArray(is));
            }
        } catch (IOException e) {
            throw new RuntimeException("Could not get data to compute class info in file: " + resource, e);
        }
        return Optional.empty();
    }

    @Override
    public void close() throws IOException {}
}
