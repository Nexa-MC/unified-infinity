"""Minimal local-game process environment; unlisted keys are never read/copied.

This is environment hygiene, not a filesystem/network sandbox. Official loader
arguments still define the private game directory. No proxy is needed for these
pre-cached, local-only development tests, so no proxy variables are inherited.
"""
from collections.abc import Mapping
from pathlib import Path

POLICY_VERSION = 'minimal-local-game-v1'
# Required local display endpoints, locale, and optional standard Mesa selectors.
# XAUTHORITY is a local display-context path; its contents are never read here.
INHERITED_KEYS = (
    'DISPLAY', 'XAUTHORITY', 'WAYLAND_DISPLAY', 'XDG_RUNTIME_DIR',
    'LANG', 'LANGUAGE', 'LC_ALL', 'LC_CTYPE', 'LC_COLLATE', 'LC_MESSAGES',
    'LC_MONETARY', 'LC_NUMERIC', 'LC_TIME', 'TZ',
    'LIBGL_ALWAYS_SOFTWARE', 'MESA_LOADER_DRIVER_OVERRIDE', 'GALLIUM_DRIVER',
    '__GLX_VENDOR_LIBRARY_NAME',
)
OFFICIAL_KEYS = frozenset({'MOD_CLASSES'})
PRIVATE_DIRECTORIES = {
    'HOME': '.launch-home',
    'XDG_CACHE_HOME': '.launch-cache',
    'XDG_CONFIG_HOME': '.launch-config',
    'XDG_DATA_HOME': '.launch-data',
    'TMPDIR': '.launch-tmp',
}

def build_game_environment(source: Mapping[str, str], game_directory: Path,
                           java_home: Path, official_fields: Mapping[str, str]):
    """Read values only for allowlisted keys. Never enumerate/copy source values."""
    if set(official_fields) - OFFICIAL_KEYS:
        raise ValueError('Unexpected official-run environment field; review before launch')
    game_directory=game_directory.resolve()
    java_home=java_home.resolve()
    result={key:source[key] for key in INHERITED_KEYS if key in source}
    result.setdefault('LANG','C.UTF-8')
    result['JAVA_HOME']=str(java_home)
    result['PATH']=str(java_home/'bin')+':/usr/local/bin:/usr/bin:/bin'
    for key,name in PRIVATE_DIRECTORIES.items():result[key]=str(game_directory/name)
    for key,value in official_fields.items():
        if not isinstance(value,str) or '\x00' in value:
            raise ValueError('Invalid official-run environment field value')
        result[key]=value
    return result

def create_private_environment_directories(game_directory: Path):
    game_directory=game_directory.resolve()
    for name in PRIVATE_DIRECTORIES.values():
        path=game_directory/name
        if path.is_symlink() or path.resolve().parent!=game_directory:
            raise ValueError('Refusing a redirected private environment directory')
        path.mkdir(parents=True,exist_ok=True)

def public_policy_descriptor():
    """No ambient key names or values are exposed in this policy descriptor."""
    return {'version':POLICY_VERSION,'inheritedAllowlist':list(INHERITED_KEYS),
            'officialRunAllowlist':sorted(OFFICIAL_KEYS),
            'fixedPrivateDirectoryKeys':list(PRIVATE_DIRECTORIES),
            'fixedPath':True,'proxyVariablesInherited':False,
            'unlistedKeysInherited':False,'jvmOptionInjectionInherited':False,
            'filesystemOrNetworkSandboxClaim':False}
