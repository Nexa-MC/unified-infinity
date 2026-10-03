/*
 * Adapted for the native-quilt-v1 host compatibility profile (2026).
 * Loader-engine references are replaced by isolated host-backed/value implementations.
 * Copyright 2016 FabricMC
 * Copyright 2022-2023 QuiltMC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package org.quiltmc.loader.api.minecraft;

import net.fabricmc.api.EnvType;
import net.fabricmc.loader.api.FabricLoader;

/** Minecraft environment is owned by the existing host. */
public final class MinecraftQuiltLoader {
    private MinecraftQuiltLoader() {}
    public static EnvType getEnvironmentType() { return FabricLoader.getInstance().getEnvironmentType(); }
}
