#!/usr/bin/env python3
"""Find C++ vtables and the functions in their slots inside an iOS dyld shared cache.

  dsc-vtables.py CACHE_DIR [PATTERN ...]

CACHE_DIR holds dyld_shared_cache_arm64, its numbered sub-caches and the .symbols file
(an iOS 16 split cache, e.g. /System/Library/Caches/com.apple.dyld of a mounted root).
Every local symbol whose mangled name contains one of the PATTERNs is collected
(default: CoreAnimation's window server and GLES classes). For each vtable symbol
(__ZTV...) found, the slots are read from the cache and printed as
"offset-from-vtable+0x10  target  symbol", the layout the render-server hooks use
(slot address = vtable + 0x10 + offset). Pointers in the cache's data mappings carry
slide-info bits in the high bits; the low 36 bits plus the cache base are the target.

Read-only: nothing is written anywhere.
"""
import mmap
import os
import struct
import sys

DEFAULT = [b'2CA12WindowServer', b'2CA3OGL', b'2CA6Render']


def open_map(path):
    f = open(path, 'rb')
    return mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)


def mappings(m):
    off, cnt = struct.unpack_from('<II', m, 0x10)
    out = []
    for i in range(cnt):
        addr, size, foff, maxp, initp = struct.unpack_from('<QQQII', m, off + i * 32)
        out.append((addr, size, foff))
    return out


def main():
    d = sys.argv[1]
    pats = [p.encode() for p in sys.argv[2:]] or DEFAULT
    files = sorted(f for f in os.listdir(d) if f.startswith('dyld_shared_cache_arm64') and not f.endswith('.symbols'))
    space = []                                   # (addr, size, map, fileoff)
    for f in files:
        m = open_map(os.path.join(d, f))
        if m[:7] != b'dyld_v1':
            continue
        for addr, size, foff in mappings(m):
            space.append((addr, size, m, foff))
    space.sort(key=lambda t: t[0])
    base = space[0][0]
    print(f'# {len(files)} cache files, {len(space)} mappings, base {base:#x}')

    def read(addr, n):
        for a, s, m, fo in space:
            if a <= addr < a + s:
                return m[fo + addr - a: fo + addr - a + n]
        return None

    sym = open_map(os.path.join(d, 'dyld_shared_cache_arm64.symbols'))
    lso, lss = struct.unpack_from('<QQ', sym, 0x48)
    nlo, nlc, sto, sts, eno, enc = struct.unpack_from('<IIIIII', sym, lso)
    strings = lso + sto
    wanted = set()
    for p in pats:
        i = sym.find(p, strings, strings + sts)
        while i != -1:
            s = sym.rfind(b'\0', strings, i) + 1
            wanted.add(s - strings)
            i = sym.find(p, i + 1, strings + sts)
    print(f'# {nlc} local symbols, {len(wanted)} names match {pats}')

    names = {}                                   # address -> name (all matching symbols)
    vtables = {}
    nl = lso + nlo
    for strx, ntype, nsect, ndesc, value in struct.iter_unpack('<IBBHQ', sym[nl:nl + nlc * 16]):
        if strx in wanted and value:
            e = sym.find(b'\0', strings + strx)
            name = sym[strings + strx:e].decode('ascii', 'replace')
            names[value] = name
            if name.startswith('__ZTV'):
                vtables[name] = value

    for vt in sorted(vtables):
        addr = vtables[vt]
        print(f'\n{vt}  {addr:#x}')
        blob = read(addr, 0x10 + 8 * 160) or b''
        for k in range(160):
            raw = struct.unpack_from('<Q', blob, 0x10 + 8 * k)[0] if len(blob) >= 0x18 + 8 * k else 0
            tgt = raw & 0xFFFFFFFFF
            if tgt and tgt < base:
                tgt += base
            if raw == 0:
                if k > 4:
                    break
                continue
            print(f'  {8 * k:#06x}  {tgt:#x}  {names.get(tgt, "?")}')


if __name__ == '__main__':
    main()
