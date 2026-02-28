"""
L0 Data — C library to distro package name mapping.

Used by dynamic_dep_resolver to resolve native library dependencies
to the correct distro-specific package name.
Pure data, no logic.
"""

from __future__ import annotations


LIB_TO_PACKAGE_MAP: dict[str, dict[str, str]] = {
    "ssl": {
        "debian": "libssl-dev",
        "rhel": "openssl-devel",
        "alpine": "openssl-dev",
        "arch": "openssl",
        "suse": "libopenssl-devel",
        "macos": "openssl@3",
    },
    "crypto": {
        "debian": "libssl-dev",
        "rhel": "openssl-devel",
        "alpine": "openssl-dev",
        "arch": "openssl",
        "suse": "libopenssl-devel",
        "macos": "openssl@3",
    },
    "curl": {
        "debian": "libcurl4-openssl-dev",
        "rhel": "libcurl-devel",
        "alpine": "curl-dev",
        "arch": "curl",
        "suse": "libcurl-devel",
        "macos": "curl",
    },
    "z": {
        "debian": "zlib1g-dev",
        "rhel": "zlib-devel",
        "alpine": "zlib-dev",
        "arch": "zlib",
        "suse": "zlib-devel",
    },
    "ffi": {
        "debian": "libffi-dev",
        "rhel": "libffi-devel",
        "alpine": "libffi-dev",
        "arch": "libffi",
        "suse": "libffi-devel",
    },
    "sqlite3": {
        "debian": "libsqlite3-dev",
        "rhel": "sqlite-devel",
        "alpine": "sqlite-dev",
        "arch": "sqlite",
        "suse": "sqlite3-devel",
    },
    "xml2": {
        "debian": "libxml2-dev",
        "rhel": "libxml2-devel",
        "alpine": "libxml2-dev",
        "arch": "libxml2",
        "suse": "libxml2-devel",
    },
    "yaml": {
        "debian": "libyaml-dev",
        "rhel": "libyaml-devel",
        "alpine": "yaml-dev",
        "arch": "libyaml",
        "suse": "libyaml-devel",
    },
    "readline": {
        "debian": "libreadline-dev",
        "rhel": "readline-devel",
        "alpine": "readline-dev",
        "arch": "readline",
        "suse": "readline-devel",
    },
    "bz2": {
        "debian": "libbz2-dev",
        "rhel": "bzip2-devel",
        "alpine": "bzip2-dev",
        "arch": "bzip2",
        "suse": "libbz2-devel",
    },
    "lzma": {
        "debian": "liblzma-dev",
        "rhel": "xz-devel",
        "alpine": "xz-dev",
        "arch": "xz",
        "suse": "xz-devel",
    },
    "gdbm": {
        "debian": "libgdbm-dev",
        "rhel": "gdbm-devel",
        "alpine": "gdbm-dev",
        "arch": "gdbm",
        "suse": "gdbm-devel",
    },
    "ncurses": {
        "debian": "libncurses-dev",
        "rhel": "ncurses-devel",
        "alpine": "ncurses-dev",
        "arch": "ncurses",
        "suse": "ncurses-devel",
    },
    "png": {
        "debian": "libpng-dev",
        "rhel": "libpng-devel",
        "alpine": "libpng-dev",
        "arch": "libpng",
        "suse": "libpng16-devel",
    },
    "jpeg": {
        "debian": "libjpeg-dev",
        "rhel": "libjpeg-turbo-devel",
        "alpine": "libjpeg-turbo-dev",
        "arch": "libjpeg-turbo",
        "suse": "libjpeg-turbo-devel",
    },
    "pcre2-8": {
        "debian": "libpcre2-dev",
        "rhel": "pcre2-devel",
        "alpine": "pcre2-dev",
        "arch": "pcre2",
        "suse": "pcre2-devel",
    },
}

