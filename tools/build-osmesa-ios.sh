#!/bin/bash
# Build Mesa's OSMesa (Gallium freedreno + softpipe, OpenGL ES) for iOS arm64 from Linux: the
# OpenGL ES library behind CoreAnimation's GLES render server (docs/gles-route-20H392.md).
#
#   tools/build-osmesa-ios.sh [WORKDIR]       default WORKDIR: ~/osmesa-ios-build
#
# Inputs (environment):
#   IOS_SDK    iPhoneOS 16.5 SDK            default ~/ios-sdk/iPhoneOS16.5.sdk
#   BERGAMOTA  a checkout of ry-diffusion/Bergamota (MIT): gpu/eagl/mesa/bergamota-mesa-25.0.7.patch
#              (freedreno/msm over the libdrm stand-in, the OSMesa GLES profile, the hardware
#              OSMesa screen that renders into IOSurfaces through SweetAdreno630)
#   LIBDRM     the libdrm stand-in built from Bergamota's gpu/freedreno-sweet/sweet_drm.c
#              default ~/ios-userland/libdrm.2.dylib
# Needs: clang, ld64.lld, llvm-ar, meson, ninja, bison, flex, python3-mako, python3-yaml, network.
# The cross-build fixes are the ones tools/mesa-ios/README.md explains.
set -euo pipefail
W=${1:-$HOME/osmesa-ios-build}
SDK=${IOS_SDK:-$HOME/ios-sdk/iPhoneOS16.5.sdk}
BERG=${BERGAMOTA:-$HOME/ref/Bergamota}
LIBDRM=${LIBDRM:-$HOME/ios-userland/libdrm.2.dylib}
MESA_VER=25.0.7
MESA_SHA=592272df3cf01e85e7db300c449df5061092574d099da275d19e97ef0510f8a6
DRM_VER=2.4.124

mkdir -p "$W"
cd "$W"

# --- sources -------------------------------------------------------------------------
[ -f mesa-$MESA_VER.tar.xz ] || curl -4 -sL --fail -o mesa-$MESA_VER.tar.xz https://archive.mesa3d.org/mesa-$MESA_VER.tar.xz
echo "$MESA_SHA  mesa-$MESA_VER.tar.xz" | sha256sum -c --quiet
[ -f libdrm-$DRM_VER.tar.xz ] || curl -4 -sL --fail -o libdrm-$DRM_VER.tar.xz https://dri.freedesktop.org/libdrm/libdrm-$DRM_VER.tar.xz
rm -rf mesa && mkdir mesa && tar xJf mesa-$MESA_VER.tar.xz -C mesa --strip-components=1
[ -d libdrm ] || { mkdir libdrm && tar xJf libdrm-$DRM_VER.tar.xz -C libdrm --strip-components=1; }

cd mesa
patch -s -p1 --no-backup-if-mismatch < "$BERG/gpu/eagl/mesa/bergamota-mesa-25.0.7.patch"

# --- meson edits: "msm over a libdrm stand-in, no KMS" (as tools/build-bgair-ios.sh) ---
python3 - <<'PY'
p='meson.build'; s=open(p).read()
s = s.replace("with_gallium_drisw_kms = false\nif system_has_kms_drm\n  dep_libdrm = dependency(",
              "with_gallium_drisw_kms = false\nif system_has_kms_drm or freedreno_kmds.length() > 0   # msm over the libdrm stand-in, no KMS\n  dep_libdrm = dependency(", 1)
open(p,'w').write(s)
p='src/freedreno/meson.build'; s=open(p).read()
s = s.replace("if system_has_kms_drm\n  subdir('drm')\nendif",
              "if system_has_kms_drm or freedreno_kmds.length() > 0   # msm over the libdrm stand-in, no KMS\n  subdir('drm')\nendif", 1)
open(p,'w').write(s)
p='src/freedreno/drm/meson.build'; s=open(p).read()
s = s.replace("  # TODO\n  link_with : [libvdrm],",
              "  # TODO\n  link_with : freedreno_kmds.contains('virtio') ? [libvdrm] : [],   # libvdrm exists only with virtio", 1)
open(p,'w').write(s)
PY
cd ..

# --- pkg-config for the iOS target --------------------------------------------------
mkdir -p pc drm-link
cp -f "$LIBDRM" drm-link/libdrm.2.dylib
ln -sf libdrm.2.dylib drm-link/libdrm.dylib
cat > pc/libdrm.pc <<EOP
Name: libdrm
Description: libdrm stand-in (SweetAdreno630)
Version: $DRM_VER
Cflags: -I$W/libdrm/include/drm -I$W/libdrm
Libs: -L$W/drm-link -ldrm
EOP
cat > pc/zlib.pc <<EOP
Name: zlib
Description: iOS SDK zlib (resolved through -isysroot)
Version: 1.3.1
Libs: -lz
Cflags:
EOP

cat > ios.cross <<EOC
[binaries]
c = 'clang'
cpp = 'clang++'
objc = 'clang'
objcpp = 'clang++'
ar = 'llvm-ar'
strip = 'llvm-strip'
pkg-config = 'pkg-config'

[host_machine]
system = 'darwin'
subsystem = 'ios'
cpu_family = 'aarch64'
cpu = 'arm64'
endian = 'little'

[properties]
needs_exe_wrapper = true

[built-in options]
c_args = ['--target=arm64-apple-ios16.0', '-isysroot', '$SDK', '-DHAVE_STRUCT_TIMESPEC', '-DHAVE_DLADDR', '-DHAVE_DLFCN_H', '-DHAVE_FUNC_ATTRIBUTE_PACKED']
c_link_args = ['--target=arm64-apple-ios16.0', '-isysroot', '$SDK', '-fuse-ld=lld']
cpp_args = ['--target=arm64-apple-ios16.0', '-isysroot', '$SDK', '-DHAVE_STRUCT_TIMESPEC', '-DHAVE_DLADDR', '-DHAVE_DLFCN_H', '-DHAVE_FUNC_ATTRIBUTE_PACKED', '-Wno-c++11-narrowing', '-Wno-narrowing']
cpp_link_args = ['--target=arm64-apple-ios16.0', '-isysroot', '$SDK', '-fuse-ld=lld']
objc_args = ['--target=arm64-apple-ios16.0', '-isysroot', '$SDK']
objc_link_args = ['--target=arm64-apple-ios16.0', '-isysroot', '$SDK', '-fuse-ld=lld']
EOC

export PKG_CONFIG_PATH="$W/pc" PKG_CONFIG_LIBDIR="$W/pc"
rm -rf build
# --wrap-mode=nofallback: freedreno's decode tools ask for libxml2 with a fallback subproject,
# which would download it and try to build xmllint for iOS.
meson setup build mesa --cross-file ios.cross --wrap-mode=nofallback --buildtype=release -Db_ndebug=true \
  -Dprefix=/usr/local -Dlibdir=lib \
  -Dplatforms= -Dgallium-drivers=softpipe,freedreno -Dfreedreno-kmds=msm -Dvulkan-drivers= \
  -Dglx=disabled -Degl=disabled -Dgbm=disabled -Dosmesa=true -Dllvm=disabled -Dshared-glapi=enabled \
  -Dgles1=enabled -Dgles2=enabled -Dopengl=true -Dzstd=disabled -Dxmlconfig=disabled -Dexpat=disabled \
  -Dshader-cache=disabled -Dvalgrind=disabled -Dlibunwind=disabled -Dglvnd=disabled -Dvideo-codecs= \
  -Dtools= -Dgallium-vdpau=disabled -Dgallium-va=disabled -Dgallium-xa=disabled -Dlmsensors=disabled \
  -Dgallium-opencl=disabled -Dgallium-rusticl=false -Dbuild-tests=false > setup.log 2>&1 \
  || { tail -30 setup.log; exit 1; }
ninja -C build -j"$(nproc)" > ninja.log 2>&1 || { grep -E 'error|FAILED' ninja.log | head -30; exit 1; }

mkdir -p out
OUT=$(find build -name 'libOSMesa*.dylib' -type f | head -1)
llvm-strip -x -o out/libOSMesa.8.dylib "$OUT"
llvm-nm -gU out/libOSMesa.8.dylib | awk '$3 ~ /^_gl/ { print substr($3, 2) }' > out/exported-gl.txt
cp mesa/src/mapi/glapi/registry/gl.xml out/gl.xml
echo "libOSMesa.8.dylib: $(stat -c %s out/libOSMesa.8.dylib) bytes, $(wc -l < out/exported-gl.txt) gl* exports"
llvm-objdump --macho --dylibs-used out/libOSMesa.8.dylib
