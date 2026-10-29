#!/bin/bash
# Build the GPU-composited UI pieces for the root image (docs/gles-route-20H392.md):
#
#   libdrm.2.dylib         Bergamota's libdrm stand-in (SweetAdreno630)           /usr/local/lib
#   libOSMesa.8.dylib      Mesa OSMesa, freedreno + softpipe (build-osmesa-ios.sh) /usr/local/lib
#   libsweetca.gl.dylib    hackios' eagl.c + sweetca_gl.c                         /usr/local/lib
#   libsweetca.dylib       sweetca_inject.c, loaded by backboardd                 /usr/local/lib
#   backboardd             the stock one with a weak load of libsweetca.dylib     /usr/libexec
#
#   tools/gles-ca/build.sh OUTDIR STOCK_BACKBOARDD
#
# Inputs (environment): IOS_SDK, HACKIOS (a checkout of oosexgang/hackios-xnu-kernel, MIT userland:
# eagl.c, eagl_slots.txt, mkeagl.py, hakios.gl.h), OSMESA_OUT (build-osmesa-ios.sh's out/),
# LIBDRM (the built stand-in). Nothing of the inputs is copied into this repository.
set -euo pipefail
HERE=${GLESCA_SRC:-$(cd "$(dirname "$0")" && pwd)}
OUT=${1:?OUTDIR}
STOCK=${2:?STOCK_BACKBOARDD}
SDK=${IOS_SDK:-$HOME/ios-sdk/iPhoneOS16.5.sdk}
HK=${HACKIOS:-$HOME/ref/hackios-xnu-kernel}
M=${OSMESA_OUT:-$HOME/osmesa-ios-build/out}
LIBDRM=${LIBDRM:-$HOME/ios-userland/libdrm.2.dylib}
CC="clang --target=arm64-apple-ios16.0 -isysroot $SDK -fuse-ld=lld -O1 -Wall -Wno-unused-function"
LIB=/usr/local/lib
export PATH="$PATH:$(ls -d /usr/lib/llvm-*/bin 2>/dev/null | sort -V | tail -1)"

mkdir -p "$OUT/obj" "$OUT/usr/local/lib" "$OUT/usr/libexec"
cp -f "$LIBDRM" "$OUT/usr/local/lib/libdrm.2.dylib"
cp -f "$M/libOSMesa.8.dylib" "$OUT/usr/local/lib/libOSMesa.8.dylib"
llvm-install-name-tool -id $LIB/libOSMesa.8.dylib "$OUT/usr/local/lib/libOSMesa.8.dylib"
python3 -I "$HERE/../macho-add-dylib.py" --rehash "$OUT/usr/local/lib/libOSMesa.8.dylib"
exports=$(llvm-nm -gU "$OUT/usr/local/lib/libOSMesa.8.dylib")
for s in OSMesaSweetActive OSMesaSweetWrapTexture OSMesaCreateContextAttribs OSMesaMakeCurrent; do
	grep -q " _$s\$" <<<"$exports" || { echo "libOSMesa lacks $s" >&2; exit 1; }
done

python3 -I "$HK/userland/mkeagl.py" "$HK/userland/src/eagl_slots.txt" "$M/gl.xml" "$M/exported-gl.txt" \
	"$HK/userland/src/eagl.c" > "$OUT/obj/eagl_gen.h"

$CC -dynamiclib -install_name $LIB/libsweetca.gl.dylib -I"$OUT/obj" -I"$HK/userland/src" \
	-framework CoreFoundation -framework IOKit -framework IOSurface -lobjc \
	"$OUT/usr/local/lib/libOSMesa.8.dylib" -Wl,-adhoc_codesign \
	-o "$OUT/usr/local/lib/libsweetca.gl.dylib" "$HK/userland/src/eagl.c" "$HERE/sweetca_gl.c"

$CC -dynamiclib -install_name $LIB/libsweetca.dylib -I"$HK/userland/src" \
	-framework CoreFoundation -framework IOKit -Wl,-adhoc_codesign \
	-o "$OUT/usr/local/lib/libsweetca.dylib" "$HERE/sweetca_inject.c"

python3 -I "$HERE/../macho-add-dylib.py" "$STOCK" "$OUT/usr/libexec/backboardd" $LIB/libsweetca.dylib
chmod 0755 "$OUT/usr/libexec/backboardd" "$OUT"/usr/local/lib/*.dylib
python3 -I "$HERE/../macho-add-dylib.py" --check "$OUT"/usr/local/lib/*.dylib "$OUT/usr/libexec/backboardd"

for f in "$OUT"/usr/local/lib/*.dylib "$OUT/usr/libexec/backboardd"; do
	printf '%-60s %9d\n' "${f#$OUT}" "$(stat -c %s "$f")"
	llvm-objdump --macho --dylibs-used "$f" | tail -n +2 | grep -E '@rpath|/usr/local' || true
done
