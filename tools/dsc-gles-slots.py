#!/usr/bin/env python3
"""Read the EAGL macro-context offsets off OpenGLES.framework in an iOS dyld shared cache.

  dsc-gles-slots.py CACHE_DIR [SLOTS.txt]

Every exported gl* function of OpenGLES loads the current context's function table from
thread-local storage and jumps through one fixed offset of it. This prints "offset name" for
each exported gl* function (the format of hackios' userland/src/eagl_slots.txt, without the
QuartzCore column), and with SLOTS.txt compares against such a list: same, moved, missing.

Only the instruction shapes seen in the stubs are decoded: LDR Xt, [Xn, #imm] (unsigned
offset) and BR/BRAA. Read-only.
"""
import mmap
import os
import struct
import sys

LC_SEGMENT_64, LC_SYMTAB = 0x19, 0x2
OPENGLES = b'/System/Library/Frameworks/OpenGLES.framework/OpenGLES'


def main():
    d = sys.argv[1]
    files = sorted(f for f in os.listdir(d) if f.startswith('dyld_shared_cache_arm64') and not f.endswith('.symbols'))
    space, main_map = [], None
    for f in files:
        fh = open(os.path.join(d, f), 'rb')
        m = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        if m[:7] != b'dyld_v1':
            continue
        if f == 'dyld_shared_cache_arm64':
            main_map = m
        off, cnt = struct.unpack_from('<II', m, 0x10)
        for i in range(cnt):
            a, s, fo, _, _ = struct.unpack_from('<QQQII', m, off + i * 32)
            space.append((a, s, m, fo))

    def read(addr, n):
        for a, s, m, fo in space:
            if a <= addr < a + s:
                return m[fo + addr - a: fo + addr - a + n]
        raise KeyError(hex(addr))

    m = main_map
    mapping_off = struct.unpack_from('<I', m, 0x10)[0]
    if mapping_off >= 0x1c8:
        img_off, img_cnt = struct.unpack_from('<II', m, 0x1c0)
    else:
        img_off, img_cnt = struct.unpack_from('<II', m, 0x18)
    base = None
    for i in range(img_cnt):
        addr, _, _, path_off, _ = struct.unpack_from('<QQQII', m, img_off + i * 32)
        path = m[path_off:m.find(b'\0', path_off)]
        if path == OPENGLES:
            base = addr
    if base is None:
        sys.exit('OpenGLES not found in the cache image list')

    ncmds = struct.unpack_from('<I', read(base, 32), 16)[0]
    p = base + 32
    linkedit = symtab = None
    for _ in range(ncmds):
        cmd, size = struct.unpack('<II', read(p, 8))
        body = read(p, size)
        if cmd == LC_SEGMENT_64 and body[8:24].rstrip(b'\0') == b'__LINKEDIT':
            linkedit = struct.unpack_from('<QQQQ', body, 24)        # vmaddr, vmsize, fileoff, filesize
        elif cmd == LC_SYMTAB:
            symtab = struct.unpack_from('<IIII', body, 8)           # symoff, nsyms, stroff, strsize
        p += size
    le_vm, _, le_fo, _ = linkedit
    symoff, nsyms, stroff, strsize = symtab
    syms = read(le_vm + symoff - le_fo, nsyms * 16)
    strs = read(le_vm + stroff - le_fo, strsize)

    found = {}
    for strx, ntype, nsect, ndesc, value in struct.iter_unpack('<IBBHQ', syms):
        if not (ntype & 0x01) or not value:                         # external, defined
            continue
        name = strs[strx:strs.find(b'\0', strx)].decode()
        if not name.startswith('_gl'):
            continue
        code = read(value, 128)
        if os.environ.get('DUMP') == name[1:]:
            print('# bytes', ' '.join(f'0x{b:02x}' for b in code))
        # mrs x8, tpidrro_el0; ldr x8, [x8, #240] (the context); ...; ldr xF, [x8, #N]; ldr x0, [x8, #32]; br xF
        # The table entry is the field the branch register was loaded from, counted from the
        # context's +0x20 (what the entry receives as its first argument, hackios' table[0]).
        loads, entry = {}, None
        for k in range(0, 128, 4):
            ins = struct.unpack_from('<I', code, k)[0]
            if ins & 0xFFC00000 == 0xF9400000:                      # LDR Xt, [Xn, #imm12*8]
                loads[ins & 0x1F] = ((ins >> 10) & 0xFFF) * 8
            elif ins & 0xFFDFFC1F == 0xD61F0000:                    # BR Xn / BLR Xn
                entry = loads.get((ins >> 5) & 0x1F)
                break
        if entry is not None and entry >= 0x20:
            found[name[1:]] = entry - 0x20

    by_off = {}
    for n, o in found.items():
        by_off.setdefault(o, []).append(n)
    if len(sys.argv) > 2:
        ref = {}
        for line in open(sys.argv[2]):
            f = line.split('#')[0].split()
            if f:
                for n in f[2:]:
                    ref[n] = int(f[0], 16)
        same = sum(1 for n, o in ref.items() if found.get(n) == o)
        moved = [(n, ref[n], found[n]) for n in ref if n in found and found[n] != ref[n]]
        missing = [n for n in ref if n not in found]
        print(f'# reference {len(ref)} names: {same} same offset, {len(moved)} moved, {len(missing)} not found')
        for n, a, b in moved:
            print(f'# moved   {n}: {a:#06x} -> {b:#06x}')
        for n in missing[:40]:
            print(f'# missing {n}')
    for o in sorted(by_off):
        print(f'{o:#06x} {" ".join(sorted(by_off[o]))}')


if __name__ == '__main__':
    main()
