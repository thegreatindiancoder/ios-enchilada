#!/usr/bin/env python3
"""Add a weak dylib load to a thin arm64 Mach-O and keep its ad-hoc signature valid.

  macho-add-dylib.py IN OUT DYLIB_PATH
  macho-add-dylib.py --rehash FILE...     recompute the page hashes after any other header edit
  macho-add-dylib.py --check FILE...      verify every page hash (exit 1 on a mismatch)

The new LC_LOAD_WEAK_DYLIB goes into the padding between the load commands and the first
section, so no data moves. Weak: if DYLIB_PATH is missing, dyld carries on and the program runs
as before. The embedded signature is updated in place: every CodeDirectory (SHA-1 and SHA-256
alike) gets the new hash of each code page that changed -- the load commands live in page 0.
That is all an ad-hoc signature (no CMS blob, as on iOS system binaries) needs; the cdhash
changes, which this port's AMFI stand-in does not check against a trust cache.

Refuses fat files, binaries without slack, and signatures with a CMS signer.
"""
import hashlib
import struct
import sys

LC_SEGMENT_64, LC_LOAD_WEAK_DYLIB, LC_CODE_SIGNATURE = 0x19, 0x80000018, 0x1d
CSMAGIC_EMBEDDED, CSMAGIC_CD, CSMAGIC_BLOBWRAPPER = 0xfade0cc0, 0xfade0c02, 0xfade0b01
HASHES = {1: hashlib.sha1, 2: hashlib.sha256, 3: hashlib.sha256, 4: hashlib.sha384}


def rehash(path, check_only=False):
    """Recompute (or with check_only, verify) every code-page hash of every CodeDirectory."""
    data = bytearray(open(path, 'rb').read())
    ncmds = struct.unpack_from('<I', data, 16)[0]
    off, sig = 32, None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', data, off)
        if cmd == LC_CODE_SIGNATURE:
            sig = struct.unpack_from('<II', data, off + 8)
        off += size
    if sig is None:
        print(f'{path}: not signed')
        return False
    dataoff = sig[0]
    _, _, count = struct.unpack_from('>III', data, dataoff)
    bad_total = 0
    for i in range(count):
        typ, boff = struct.unpack_from('>II', data, dataoff + 12 + i * 8)
        cd = dataoff + boff
        if struct.unpack_from('>I', data, cd)[0] != CSMAGIC_CD:
            continue
        f = struct.unpack_from('>IIIIIIIIIBBBB', data, cd)
        hash_off, ncode, limit, hsize, htype, pshift = f[4], f[7], f[8], f[9], f[10], f[12]
        bad = 0
        for s in range(ncode):
            digest = HASHES[htype](bytes(data[s << pshift:min((s + 1) << pshift, limit)])).digest()[:hsize]
            at = cd + hash_off + s * hsize
            if data[at:at + hsize] != digest:
                bad += 1
                data[at:at + hsize] = digest
        bad_total += bad
        print(f'{path}: CodeDirectory hash type {htype}, {ncode} pages: {bad} '
              f'{"wrong" if check_only else "rewritten"}')
    if not check_only and bad_total:
        open(path, 'wb').write(data)
    return bad_total == 0


def main():
    if sys.argv[1] in ('--rehash', '--check'):
        ok = all([rehash(p, sys.argv[1] == '--check') for p in sys.argv[2:]])
        sys.exit(0 if ok or sys.argv[1] == '--rehash' else 1)
    src, dst, dylib = sys.argv[1:4]
    data = bytearray(open(src, 'rb').read())
    magic, _, _, _, ncmds, sizeofcmds, _, _ = struct.unpack_from('<IIIIIIII', data, 0)
    if magic != 0xfeedfacf:
        sys.exit(f'not a thin 64-bit Mach-O ({magic:#x})')
    off, first_section, sig = 32, len(data), None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', data, off)
        if cmd == LC_SEGMENT_64:
            for s in range(struct.unpack_from('<I', data, off + 64)[0]):
                ssize, soff = struct.unpack_from('<QI', data, off + 72 + s * 80 + 40)
                if soff and ssize:
                    first_section = min(first_section, soff)
        elif cmd == LC_CODE_SIGNATURE:
            sig = struct.unpack_from('<II', data, off + 8)
        elif cmd in (0xc, LC_LOAD_WEAK_DYLIB):
            name_off = struct.unpack_from('<I', data, off + 8)[0]
            name = data[off + name_off:off + size].split(b'\0')[0].decode()
            if name == dylib:
                sys.exit(f'{src} already loads {dylib}')
        off += size
    name = dylib.encode() + b'\0'
    cmdsize = (24 + len(name) + 7) & ~7
    slack = first_section - off
    print(f'load commands end {off:#x}, first section {first_section:#x}, slack {slack}, need {cmdsize}')
    if slack < cmdsize or any(data[off:off + cmdsize]):
        sys.exit('not enough zero padding after the load commands')
    lc = struct.pack('<IIIIII', LC_LOAD_WEAK_DYLIB, cmdsize, 24, 2, 0x10000, 0x10000) + name
    data[off:off + cmdsize] = lc + b'\0' * (cmdsize - len(lc))
    struct.pack_into('<II', data, 16, ncmds + 1, sizeofcmds + cmdsize)

    if sig is None:
        print('no code signature: done')
    else:
        dataoff, datasize = sig
        sb_magic, _, count = struct.unpack_from('>III', data, dataoff)
        if sb_magic != CSMAGIC_EMBEDDED:
            sys.exit(f'unexpected signature magic {sb_magic:#x}')
        cds = []
        for i in range(count):
            typ, boff = struct.unpack_from('>II', data, dataoff + 12 + i * 8)
            bmagic, blen = struct.unpack_from('>II', data, dataoff + boff)
            if bmagic == CSMAGIC_BLOBWRAPPER and blen > 8:
                sys.exit('signature has a CMS signer: not an ad-hoc signature, refusing')
            if bmagic == CSMAGIC_CD:
                cds.append(dataoff + boff)
        for cd in cds:
            (_, _, version, flags, hash_off, ident_off, nspecial, ncode, code_limit,
             hash_size, hash_type, platform, page_shift) = struct.unpack_from('>IIIIIIIIIBBBB', data, cd)
            h = HASHES[hash_type]
            page = 1 << page_shift
            changed = 0
            for slot in range(ncode):
                start = slot * page
                if start >= off + cmdsize:                     # only pages that hold the load commands
                    break
                end = min(start + page, code_limit)
                digest = h(bytes(data[start:end])).digest()[:hash_size]
                at = cd + hash_off + slot * hash_size
                if data[at:at + hash_size] != digest:
                    data[at:at + hash_size] = digest
                    changed += 1
            print(f'CodeDirectory v{version:#x} hash type {hash_type}, {ncode} pages of {page}: {changed} slot(s) updated')
    open(dst, 'wb').write(data)


if __name__ == '__main__':
    main()
