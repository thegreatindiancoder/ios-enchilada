#!/usr/bin/env python3
"""Pack files into the userland archive that travels in the boot image (xnu 0175).

  mkuserland.py OUT FILE...

Format (little-endian):
  header   'SWUL' u32 version=1, u32 count, u32 header_size
  entries  count * { char name[56]; u32 offset; u32 size }   (offset from the start of the archive)
  data     each file, 16-byte aligned
Names are base names; the reader (tools/gles-ca/sweetca_inject.c) writes them into one directory.
"""
import os
import struct
import sys

out, files = sys.argv[1], sys.argv[2:]
header = 16 + 64 * len(files)
blob = bytearray(header)
struct.pack_into('<4sIII', blob, 0, b'SWUL', 1, len(files), header)
for i, path in enumerate(files):
    name = os.path.basename(path).encode()
    if len(name) >= 56:
        sys.exit(f'name too long: {name}')
    blob += b'\0' * (-len(blob) & 15)
    data = open(path, 'rb').read()
    struct.pack_into('<56sII', blob, 16 + 64 * i, name, len(blob), len(data))
    blob += data
open(out, 'wb').write(blob)
print(f'{out}: {len(files)} files, {len(blob)} bytes')
