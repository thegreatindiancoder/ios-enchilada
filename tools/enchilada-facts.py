#!/usr/bin/env python3
"""Read-only hardware facts from a OnePlus 6 (enchilada), for the port.

    python3 tools/enchilada-facts.py                  # phone in OrangeFox/TWRP (adb root) or Android
    python3 tools/enchilada-facts.py --su             # rooted Android: read root-only files through su
    python3 tools/enchilada-facts.py --fastboot       # phone in fastboot mode: bootloader variables
    python3 tools/enchilada-facts.py --summarize DIR  # rebuild DIR/summary.txt from DIR/raw
    python3 tools/enchilada-facts.py --selftest       # offline check of the parsers and the guards

Nothing is written to the phone. Every phone-side command only reads (cat, ls, readlink,
getprop, grep, dmesg, tar to stdout) and its output streams to the PC through
'adb exec-out': no file is created on the phone, nothing is mounted, no property is set.
The only raw partitions read are boot_a/b, dtbo_a/b and vbmeta_a/b (skip them with
--no-partitions); persist, modem*, fsg, fsc and the bootloaders are never opened. In
fastboot mode only 'devices', 'getvar all' and 'oem device-info' are sent.

Everything lands in facts/<date>-<time>/ (ignored by git):
  raw/         exact dumps - they hold the serial number and MAC addresses, keep them private
  summary.txt  what the port needs, with serials, IMEI-like numbers and MACs redacted

ADB / FASTBOOT environment variables override the tool paths (Windows: platform-tools).
"""
import argparse
import datetime
import os
import re
import shlex
import struct
import subprocess
import sys
import tarfile
import zlib

PARTITIONS = ('boot_a', 'boot_b', 'dtbo_a', 'dtbo_b', 'vbmeta_a', 'vbmeta_b')

# Anything that could change the phone. The commands in this file are fixed strings; the
# check runs before every adb call as a second line of defence against later edits.
WRITEISH = re.compile(r"""(
    \bdd\b | \bof= | > | \btee\b | \bu?mount\b | \b(?:re)?setprop\b | \brm\b | \bmv\b
  | \bcp\b | \bln\b | \bchmod\b | \bchown\b | \bchcon\b | \bmkdir\b | \bmkfs
  | \bmke2fs\b | \bmkswap\b | \bflash | \berase\b | \bwipe\b | \breboot\b
  | \bfastboot\b | \btruncate\b | \bblockdev\b | \bsgdisk\b | \bs?fdisk\b | \bparted\b
  | \binsmod\b | \brmmod\b | \bmodprobe\b | \bmagisk | \bsetenforce\b
)""", re.X)
# Words that only matter as a command (they also occur inside sysfs paths, e.g. .../start).
COMMAND_WORDS = re.compile(r"""(?:^|[;&|(`]|\$\(|\bdo\b|\bthen\b|\belse\b)\s*
    (?:busybox\s+|toybox\s+)?(start|stop|input|format|touch|sync|kill\w*|settings|svc|sendevent|am|pm|cmd)\b""",
                           re.X)
FASTBOOT_ALLOWED = (('devices',), ('getvar', 'all'), ('oem', 'device-info'))
NEVER_READ = re.compile(r'persist|modem|fsg|fsc|xbl|abl|tz|hyp|keymaster|cmnlib|devcfg|aop|'
                        r'storsec|qupfw|frp|misc|param|oem|reserve|bluetooth|dsp')

BY_NAME_DIRS = '/dev/block/by-name /dev/block/bootdevice/by-name'

# (file under raw/, phone command, needs root). Every command only reads.
TEXT_COMMANDS = [
    ('id.txt', 'id', False),
    ('getprop.txt', 'getprop', False),
    ('uname.txt', 'uname -a', False),
    ('cmdline.txt', 'cat /proc/cmdline', False),
    ('meminfo.txt', 'cat /proc/meminfo', False),
    ('cpuinfo.txt', 'cat /proc/cpuinfo', False),
    ('iomem.txt', 'cat /proc/iomem', True),
    ('partitions.txt', 'cat /proc/partitions', False),
    ('mounts.txt', 'cat /proc/mounts', False),
    ('by-name.txt', f'for d in {BY_NAME_DIRS}; do [ -d $d ] && echo == $d && ls -l $d/; done 2>/dev/null', False),
    ('partition-table.txt',
     f'for d in {BY_NAME_DIRS}; do if [ -d $d ]; then for l in $d/*; do t=$(readlink -f $l); '
     'b=${t##*/}; echo ${l##*/} $t $(cat /sys/class/block/$b/start 2>/dev/null) '
     '$(cat /sys/class/block/$b/size 2>/dev/null); done; break; fi; done', False),
    ('block-devices.txt',
     'for b in /sys/block/sd*; do echo ${b##*/} size=$(cat $b/size 2>/dev/null) '
     'vendor=$(cat $b/device/vendor 2>/dev/null) model=$(cat $b/device/model 2>/dev/null) '
     'rev=$(cat $b/device/rev 2>/dev/null); done', False),
    ('soc0.txt',
     'for f in family machine soc_id revision raw_id raw_version hw_platform platform_subtype '
     'platform_version foundry_id pmic_model pmic_die_revision vendor build_id; do '
     'echo $f=$(cat /sys/devices/soc0/$f 2>/dev/null); done', False),
    ('devinfo.txt', '[ -d /proc/devinfo ] && for f in /proc/devinfo/*; do echo == ${f##*/}; cat $f 2>/dev/null; done', False),
    ('input-devices.txt', 'cat /proc/bus/input/devices', False),
    ('i2c-devices.txt',
     'for d in /sys/bus/i2c/devices/*; do echo ${d##*/} name=$(cat $d/name 2>/dev/null) '
     'of_node=$(readlink -f $d/of_node 2>/dev/null); done', False),
    ('spmi-devices.txt', 'ls /sys/bus/spmi/devices/ 2>/dev/null', False),
    ('drm.txt',
     'for c in /sys/class/drm/*; do echo == ${c##*/}; cat $c/status $c/enabled $c/modes 2>/dev/null; done',
     False),
    ('fb0.txt',
     'for f in name modes virtual_size stride bits_per_pixel; do '
     'echo $f=$(cat /sys/class/graphics/fb0/$f 2>/dev/null); done', False),
    ('backlight.txt',
     'for b in /sys/class/backlight/*; do echo ${b##*/} max=$(cat $b/max_brightness 2>/dev/null) '
     'now=$(cat $b/brightness 2>/dev/null); done', False),
    ('power-supply.txt', 'for p in /sys/class/power_supply/*; do echo == ${p##*/}; cat $p/uevent 2>/dev/null; done',
     False),
    ('build-props.txt',
     'for f in /system/build.prop /system_root/system/build.prop /system/system/build.prop '
     '/vendor/build.prop /odm/etc/build.prop; do [ -f $f ] && echo == $f && '
     'grep -E -e ro.build.display.id -e ro.build.fingerprint -e ro.build.version -e ro.vendor.build '
     '-e ro.product -e ro.rom.version $f; done 2>/dev/null', False),
    ('firmware-files.txt',
     'ls -la /vendor/firmware /vendor/firmware_mnt/image /firmware/image /odm/firmware 2>/dev/null', False),
    ('dmesg.txt', 'dmesg', True),
]
BINARY_COMMANDS = [
    ('live-fdt.dtb', 'cat /sys/firmware/fdt', True),
    ('device-tree.tar', 'tar -cf - -C /sys/firmware/devicetree base', True),
]


def ensure_readonly(cmd):
    stripped = cmd.replace('2>/dev/null', '')
    m = WRITEISH.search(stripped) or COMMAND_WORDS.search(stripped)
    if m:
        raise SystemExit(f'refusing phone command, not read-only ({m.group(0).strip()!r}): {cmd}')
    if "'" in cmd:
        raise SystemExit(f'refusing phone command with a single quote (su quoting): {cmd}')


def tool(env, default):
    value = os.environ.get(env)
    if not value:
        return [default]
    if os.path.exists(value):
        return [value]
    return shlex.split(value, posix=(os.name != 'nt'))


class Phone:
    def __init__(self, use_su):
        self.adb = tool('ADB', 'adb')
        self.use_su = use_su
        self.root = False
        self.wrap_su = False

    def run(self, args, timeout=900):
        try:
            p = subprocess.run(self.adb + list(args), capture_output=True, timeout=timeout)
        except FileNotFoundError:
            raise SystemExit(f'adb not found ({self.adb[0]}); install platform-tools or set ADB=')
        return p.returncode, p.stdout, p.stderr

    def sh(self, cmd, timeout=900):
        ensure_readonly(cmd)
        if self.wrap_su:
            cmd = f"su -c '{cmd}'"
        rc, out, err = self.run(['exec-out', cmd], timeout)
        return out

    def connect(self):
        rc, out, err = self.run(['devices'])
        lines = [l.split('\t') for l in out.decode(errors='replace').splitlines()[1:] if '\t' in l]
        if not lines:
            raise SystemExit('no adb device: boot the phone into OrangeFox/TWRP or Android with USB debugging')
        if len(lines) > 1 and not os.environ.get('ANDROID_SERIAL'):
            raise SystemExit('several adb devices: set ANDROID_SERIAL to the phone')
        states = {s for _, s in lines}
        if 'unauthorized' in states:
            raise SystemExit('adb unauthorized: accept the RSA prompt on the phone')
        state = self.run(['get-state'])[1].decode(errors='replace').strip()
        uid = self.sh('id -u').decode(errors='replace').strip()
        self.root = uid == '0'
        if not self.root and self.use_su:
            self.wrap_su = True
            uid = self.sh('id -u').decode(errors='replace').strip()
            self.root = uid == '0'
            if not self.root:
                self.wrap_su = False
                print('su refused root for the adb shell: on Magisk open Superuser and allow "Shell", '
                      'or accept the prompt on the phone, then run again; collecting the non-root subset now')
        return state


# ---------------------------------------------------------------- FDT / boot image parsing

class Node:
    def __init__(self, name, parent):
        self.name, self.parent, self.props, self.children = name, parent, {}, []

    def path(self):
        if self.parent is None:
            return '/'
        p = self.parent.path()
        return (p if p.endswith('/') else p + '/') + self.name

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def child(self, name):
        for c in self.children:
            if c.name == name or c.name.split('@')[0] == name:
                return c
        return None


def fdt_parse(blob):
    if len(blob) < 40:
        raise ValueError('too short for an FDT')
    (magic, total, off_struct, off_strings, _rsv, version, _comp, _cpu,
     size_strings) = struct.unpack_from('>9I', blob, 0)
    if magic != 0xd00dfeed:
        raise ValueError('not an FDT')
    size_struct = struct.unpack_from('>I', blob, 36)[0] if version >= 17 else total - off_struct
    strings = blob[off_strings:off_strings + size_strings]

    def name_at(off):
        return strings[off:strings.index(b'\0', off)].decode('ascii', 'replace')

    root = cur = None
    p, end = off_struct, off_struct + size_struct
    while p < end:
        tok = struct.unpack_from('>I', blob, p)[0]
        p += 4
        if tok == 1:
            e = blob.index(b'\0', p)
            node = Node(blob[p:e].decode('ascii', 'replace'), cur)
            p = (e + 4) & ~3
            if cur is None:
                root = node
            else:
                cur.children.append(node)
            cur = node
        elif tok == 2:
            cur = cur.parent
        elif tok == 3:
            ln, nameoff = struct.unpack_from('>II', blob, p)
            p += 8
            cur.props[name_at(nameoff)] = blob[p:p + ln]
            p = (p + ln + 3) & ~3
        elif tok == 4:
            continue
        elif tok == 9:
            break
        else:
            raise ValueError(f'bad FDT token {tok} at 0x{p - 4:x}')
    if root is None:
        raise ValueError('empty FDT')
    return root


def u32s(v):
    return list(struct.unpack('>%dI' % (len(v) // 4), v[:len(v) // 4 * 4]))


def strs(v):
    return [s.decode('ascii', 'replace') for s in v.split(b'\0') if s]


def is_text(v):
    return len(v) > 0 and v.endswith(b'\0') and all(32 <= c < 127 or c == 0 for c in v)


def fmt_prop(v, limit=24):
    if not v:
        return '<empty>'
    if is_text(v):
        return ', '.join(repr(s) for s in strs(v))
    if len(v) % 4 == 0:
        words = u32s(v)
        if len(words) == 1:
            return f'<0x{words[0]:x}> = {words[0]}'
        s = ' '.join(f'0x{w:x}' for w in words[:limit])
        return f'<{s}{" ..." if len(words) > limit else ""}> ({len(v)} bytes)'
    return f'{v[:32].hex()}{"..." if len(v) > 32 else ""} ({len(v)} bytes)'


def cells(node, name, default):
    v = node.props.get(name) if node is not None else None
    return u32s(v)[0] if v else default


def reg_ranges(node):
    parent = node.parent
    ac, sc = cells(parent, '#address-cells', 2), cells(parent, '#size-cells', 1 if parent is None else 1)
    if parent is not None and '#size-cells' not in parent.props:
        sc = 1
    words = u32s(node.props.get('reg', b''))
    out, step = [], ac + sc
    for i in range(0, len(words) - step + 1, step):
        a = 0
        for w in words[i:i + ac]:
            a = (a << 32) | w
        s = 0
        for w in words[i + ac:i + step]:
            s = (s << 32) | w
        out.append((a, s))
    return out


def phandles(root):
    m = {}
    for n in root.walk():
        for k in ('phandle', 'linux,phandle'):
            if k in n.props and len(n.props[k]) == 4:
                m[u32s(n.props[k])[0]] = n
    return m


def dtb_identity(root):
    p = root.props
    out = {'model': ', '.join(strs(p['model'])) if 'model' in p else '?',
           'compatible': ', '.join(strs(p['compatible'])) if 'compatible' in p else '?'}
    for k in ('qcom,msm-id', 'qcom,board-id', 'qcom,pmic-id'):
        if k in p:
            words = u32s(p[k])
            out[k] = ' '.join(f'0x{w:x}' for w in words) + ' (' + ' '.join(str(w) for w in words) + ')'
    for k, v in p.items():
        if k.startswith(('oem,', 'oneplus,', 'qcom,oem')) and k not in out:
            out[k] = fmt_prop(v)
    return out


def split_dtbs(data):
    out, pos = [], 0
    while True:
        pos = data.find(b'\xd0\x0d\xfe\xed', pos)
        if pos < 0 or pos + 8 > len(data):
            return out
        size = struct.unpack_from('>I', data, pos + 4)[0]
        if 64 <= size <= len(data) - pos:
            out.append((pos, data[pos:pos + size]))
            pos += size
        else:
            pos += 4


def os_version_str(v):
    if not v:
        return '0'
    ver, lvl = v >> 11, v & 0x7ff
    return f'{ver >> 14}.{(ver >> 7) & 0x7f}.{ver & 0x7f}, patch {2000 + (lvl >> 4)}-{lvl & 0xf:02d}'


def bootimg_parse(b):
    if b[:8] != b'ANDROID!':
        return {'error': 'no ANDROID! magic (empty or non-Android boot partition)'}
    ks, ka, rs, ra, ss, sa, ta, ps, ver, osv = struct.unpack_from('<10I', b, 8)
    info = {'header_version': ver}
    if ver >= 3:
        info['note'] = 'header v3+ layout; only the version is decoded'
        return info
    cmd = b[64:64 + 512].split(b'\0')[0] + b[608:608 + 1024].split(b'\0')[0]
    info.update(kernel_size=ks, kernel_addr=hex(ka), ramdisk_size=rs, ramdisk_addr=hex(ra),
                second_size=ss, tags_addr=hex(ta), page_size=ps, os_version=os_version_str(osv),
                name=b[48:64].split(b'\0')[0].decode('ascii', 'replace'),
                cmdline=cmd.decode('ascii', 'replace'))
    rnd = lambda n: (n + ps - 1) // ps * ps
    kernel = b[ps:ps + ks]
    off = ps + rnd(ks) + rnd(rs) + rnd(ss)
    if ver >= 1:
        rds, _rdo, hs = struct.unpack_from('<IQI', b, 1632)
        info.update(recovery_dtbo_size=rds, header_size=hs)
        off += rnd(rds)
    dtb_section = b''
    if ver >= 2:
        ds, da = struct.unpack_from('<IQ', b, 1648)
        info.update(dtb_size=ds, dtb_addr=hex(da))
        dtb_section = b[off:off + ds]
    info['kernel_format'] = 'gzip (Image.gz)' if kernel[:2] == b'\x1f\x8b' else (
        'raw arm64 Image' if kernel[56:60] == b'ARM\x64' else 'unknown')
    tail = kernel
    if kernel[:2] == b'\x1f\x8b':
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            img = d.decompress(kernel)
            tail = d.unused_data
            info['kernel_uncompressed'] = len(img)
        except zlib.error as e:
            info['gzip_error'] = str(e)
    elif info['kernel_format'] == 'raw arm64 Image':
        image_size = struct.unpack_from('<Q', kernel, 16)[0]
        tail = kernel[image_size:] if 0 < image_size < len(kernel) else kernel
    dtbs = []
    for where, blob in [('appended', x[1]) for x in split_dtbs(tail)] + [('dtb section', x[1]) for x in split_dtbs(dtb_section)]:
        try:
            ident = dtb_identity(fdt_parse(blob))
        except ValueError as e:
            ident = {'error': str(e)}
        dtbs.append((where, len(blob), ident))
    info['dtbs'] = dtbs
    return info


def dtbo_parse(b):
    if len(b) < 32 or struct.unpack_from('>I', b, 0)[0] != 0xd7b7ab1e:
        return {'error': 'no DT table magic (0xd7b7ab1e)'}
    magic, total, hdr, esz, count, eoff, page, ver = struct.unpack_from('>8I', b, 0)
    info = {'total_size': total, 'entry_count': count, 'page_size': page, 'version': ver, 'entries': []}
    for i in range(count):
        dsz, doff, ident, rev, c0, c1, c2, c3 = struct.unpack_from('>8I', b, eoff + i * esz)
        e = {'index': i, 'size': dsz, 'id': hex(ident), 'rev': hex(rev),
             'custom': ' '.join(hex(c) for c in (c0, c1, c2, c3))}
        try:
            e.update(dtb_identity(fdt_parse(b[doff:doff + dsz])))
        except (ValueError, struct.error) as err:
            e['error'] = str(err)
        info['entries'].append(e)
    return info


def vbmeta_parse(b):
    if b[:4] != b'AVB0':
        return {'error': 'no AVB0 magic'}
    flags = struct.unpack_from('>I', b, 120)[0]
    return {'flags': flags, 'hashtree_disabled': bool(flags & 1), 'verification_disabled': bool(flags & 2)}


# ---------------------------------------------------------------- redaction and summary

SENSITIVE_KEY = re.compile(r'serial|imei|meid|mac|cpuid|android_?id|iccid|imsi|msisdn|phone|'
                           r'account|ssid|wifi.*addr|bt.*addr|bdaddr|uuid|fingerprint_id', re.I)
REDACTIONS = [
    (re.compile(r'(androidboot\.[\w.]*(?:serial|mac|imei|meid|cpuid|uid|bdaddr)[\w.]*=)\S+', re.I), r'\1<redacted>'),
    (re.compile(r'((?:^|[\s(])(?:\(bootloader\)\s*)?serial(?:no|_number)?\s*[:=]\s*)\S+', re.I | re.M), r'\1<redacted>'),
    (re.compile(r'\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b'), '<mac>'),
    (re.compile(r'\b\d{14,17}\b'), '<long-number>'),
]


def redact(text):
    out = []
    for line in text.splitlines():
        m = re.match(r'\[([^\]]*)\]: \[(.*)\]$', line)
        if m and SENSITIVE_KEY.search(m.group(1)):
            line = f'[{m.group(1)}]: [<redacted>]'
        for rx, rep in REDACTIONS:
            line = rx.sub(rep, line)
        out.append(line)
    return '\n'.join(out)


def read(raw, name, binary=False):
    p = os.path.join(raw, name)
    if not os.path.exists(p):
        return None
    with open(p, 'rb') as f:
        data = f.read()
    return data if binary else data.decode('utf-8', 'replace')


def parse_getprop(text):
    props = {}
    for line in (text or '').splitlines():
        m = re.match(r'\[([^\]]*)\]: \[(.*)\]$', line)
        if m:
            props[m.group(1)] = m.group(2)
    return props


def human(n):
    for unit, size in (('GiB', 1 << 30), ('MiB', 1 << 20), ('KiB', 1 << 10)):
        if n >= size:
            return f'{n / size:.2f} {unit}'
    return f'{n} B'


PANEL_KEYS = re.compile(r'panel-name|panel-type|compression|dsc|width|height|framerate|te-|-te|bpp|'
                        r'lane|physical|reset|bl-|brightness|porch|pulse|clockrate|traffic|'
                        r'mode-switch|refresh|partial|roi|cmd-mode|video|esd|gpio', re.I)
TOUCH_COMPAT = re.compile(r'synaptics|rmi|goodix|touch|s3706|s3320|tcm|fts|himax|novatek', re.I)


def describe_refs(node, ph, key, v):
    words = u32s(v)
    if key.endswith('-supply') and len(words) == 1 and words[0] in ph:
        r = ph[words[0]]
        rn = ', '.join(strs(r.props['regulator-name'])) if 'regulator-name' in r.props else ''
        return f'-> {r.path()} {rn}'.rstrip()
    if (key.endswith('-gpio') or key.endswith('-gpios') or key == 'gpios') and words and words[0] in ph:
        parts, i = [], 0
        while i < len(words):
            ctl = ph.get(words[i])
            if ctl is None:
                break
            n = cells(ctl, '#gpio-cells', 2)
            args = words[i + 1:i + 1 + n]
            parts.append(f'{ctl.path()} pin {args[0] if args else "?"} flags {args[1:] if len(args) > 1 else []}')
            i += 1 + n
        if parts:
            return '-> ' + '; '.join(parts)
    if key in ('interrupts-extended',) and words and words[0] in ph:
        return f'-> {ph[words[0]].path()} {words[1:]}'
    return ''


def fdt_report(root, cmdline, lines):
    ph = phandles(root)
    ident = dtb_identity(root)
    lines.append('identity:')
    for k, v in ident.items():
        lines.append(f'  {k}: {v}')
    total = 0
    lines.append('memory nodes (as passed by ABL):')
    for n in root.walk():
        if n.parent is root and (n.name == 'memory' or n.name.startswith('memory@')):
            for a, s in reg_ranges(n):
                total += s
                lines.append(f'  {n.path()}: 0x{a:x} + 0x{s:x} -> 0x{a + s:x}  ({human(s)})')
    lines.append(f'  total: 0x{total:x} ({human(total)})')
    rsv = root.child('reserved-memory')
    if rsv is not None:
        lines.append('reserved-memory:')
        items = []
        for c in rsv.children:
            rr = reg_ranges(c) if 'reg' in c.props else []
            flags = ' no-map' if 'no-map' in c.props else ''
            if rr:
                for a, s in rr:
                    items.append((a, f'  0x{a:09x}-0x{a + s:09x} {human(s):>10}  {c.name}{flags}'))
            else:
                sz = u32s(c.props.get('size', b''))
                items.append((1 << 64, f'  (dynamic) size {[hex(w) for w in sz]}  {c.name}{flags}'))
        lines.extend(t for _, t in sorted(items))
    chosen = root.child('chosen')
    if chosen is not None and 'bootargs' in chosen.props:
        lines.append('chosen/bootargs: ' + redact(', '.join(strs(chosen.props['bootargs']))))
    # display
    m = re.search(r'msm_drm\.dsi_display0=([^:\s]+)', cmdline or '')
    want = m.group(1) if m else None
    lines.append(f'display selected by ABL (cmdline msm_drm.dsi_display0): {want or "not in cmdline"}')
    panels = [n for n in root.walk() if 'qcom,mdss-dsi-panel-name' in n.props]
    chosen_panel = None
    if want:
        # Downstream trees name the display nodes qcom,dsi-display@N and carry the
        # name ABL puts into the cmdline in their 'label' property.
        for n in root.walk():
            label = strs(n.props.get('label', b''))
            if n.name == want or n.name.startswith(want) or (label and label[0] == want):
                if 'qcom,dsi-panel' in n.props and u32s(n.props['qcom,dsi-panel'])[0] in ph:
                    chosen_panel = ph[u32s(n.props['qcom,dsi-panel'])[0]]
                    lines.append(f'display node {n.path()}: ' + ' '.join(
                        f'{k}={fmt_prop(v)}' for k, v in n.props.items() if k in ('label', 'qcom,display-type', 'qcom,dsi-display-active')))
                elif 'qcom,mdss-dsi-panel-name' in n.props:
                    chosen_panel = n
    lines.append(f'panel nodes in DT: {len(panels)}')
    for n in panels:
        mark = '  <== selected' if n is chosen_panel else ''
        lines.append(f'  {n.path()}: {fmt_prop(n.props["qcom,mdss-dsi-panel-name"])}{mark}')
    if chosen_panel is not None:
        lines.append(f'selected panel {chosen_panel.path()}:')
        for sub in chosen_panel.walk():
            for k, v in sub.props.items():
                if PANEL_KEYS.search(k) and 'command' not in k:
                    rel = sub.path()[len(chosen_panel.path()):] or '.'
                    lines.append(f'  {rel}  {k} = {fmt_prop(v)} {describe_refs(sub, ph, k, v)}'.rstrip())
    # touch
    lines.append('touch candidates (all statuses):')
    for n in root.walk():
        compat = ', '.join(strs(n.props.get('compatible', b'')))
        if compat and TOUCH_COMPAT.search(compat):
            bus = n.parent
            bus_reg = reg_ranges(bus) if bus is not None and 'reg' in bus.props else []
            lines.append(f'  {n.path()}  compatible={compat}  status={", ".join(strs(n.props.get("status", b"(none)\0")))}')
            if bus_reg:
                lines.append(f'    bus {bus.path()} reg 0x{bus_reg[0][0]:x}')
            for k, v in n.props.items():
                if k in ('compatible', 'status') or len(v) > 256:
                    continue
                lines.append(f'    {k} = {fmt_prop(v)} {describe_refs(n, ph, k, v)}'.rstrip())
    # keys
    lines.append('keys (PON / gpio-keys):')
    for n in root.walk():
        compat = ', '.join(strs(n.props.get('compatible', b'')))
        if 'linux,code' in n.props or 'pon' in compat or 'gpio-keys' in compat:
            desc = ' '.join(f'{k}={fmt_prop(v)} {describe_refs(n, ph, k, v)}'.strip()
                            for k, v in n.props.items() if k in ('compatible', 'label', 'linux,code', 'gpios', 'reg', 'qcom,pon-type', 'interrupts'))
            lines.append(f'  {n.path()}: {desc}')
    # framebuffer / splash
    lines.append('framebuffer / splash nodes:')
    for n in root.walk():
        compat = ', '.join(strs(n.props.get('compatible', b'')))
        if 'splash' in n.name or 'simple-framebuffer' in compat or n.name.startswith('framebuffer'):
            rr = reg_ranges(n) if 'reg' in n.props else []
            extra = ' '.join(f'{k}={fmt_prop(n.props[k])}' for k in ('width', 'height', 'stride', 'format') if k in n.props)
            lines.append(f'  {n.path()} ' + ' '.join(f'0x{a:x}+0x{s:x}' for a, s in rr) + f' {extra}'.rstrip())


def summarize(outdir):
    raw = os.path.join(outdir, 'raw')
    L = []
    meta = read(raw, 'meta.txt') or ''
    L += ['# OnePlus 6 (enchilada) facts', '', meta.strip(), '']
    props = parse_getprop(read(raw, 'getprop.txt'))
    cmdline = (read(raw, 'cmdline.txt') or '').strip()
    if props:
        L.append('## device / firmware (getprop)')
        for k in ('ro.product.device', 'ro.product.model', 'ro.product.name', 'ro.build.product',
                  'ro.build.display.id', 'ro.build.fingerprint', 'ro.build.version.release',
                  'ro.bootloader', 'ro.boot.hardware', 'ro.boot.slot_suffix', 'ro.boot.verifiedbootstate',
                  'ro.boot.vbmeta.device_state', 'ro.boot.flash.locked', 'ro.boot.prj_version',
                  'ro.boot.hw_version', 'ro.boot.rf_version', 'ro.boot.project_name', 'ro.boot.ddr_size',
                  'ro.boot.ddr_type', 'ro.twrp.boot', 'ro.orangefox.version', 'ro.build.fox_id'):
            if k in props:
                L.append(f'  {k} = {props[k]}')
        for k in sorted(props):
            if k.startswith('ro.boot.') and k not in ' '.join(L) and not SENSITIVE_KEY.search(k):
                L.append(f'  {k} = {props[k]}')
        L.append('')
    bp = read(raw, 'build-props.txt')
    if bp and bp.strip():
        L += ['## installed OS build.prop (if mounted)', redact(bp.strip()), '']
    if cmdline:
        L += ['## kernel cmdline from ABL (redacted)', redact(cmdline), '']
        panel = re.search(r'msm_drm\.dsi_display0=(\S+)', cmdline)
        L += [f'  panel selector (msm_drm.dsi_display0): {panel.group(1) if panel else "(none)"}', '']
    soc = read(raw, 'soc0.txt')
    if soc:
        L += ['## SoC (/sys/devices/soc0, serial not read)', soc.strip(), '']
    dev = read(raw, 'devinfo.txt')
    if dev and dev.strip():
        L += ['## OnePlus /proc/devinfo (lcd, tp, ddr, ufs ...)', redact(dev.strip()), '']
    mem = read(raw, 'meminfo.txt')
    if mem:
        L += ['## RAM', '  ' + ' | '.join(l for l in mem.splitlines() if l.startswith(('MemTotal', 'MemFree')))]
    io = read(raw, 'iomem.txt')
    if io:
        L.append('  /proc/iomem System RAM:')
        L += ['  ' + l.strip() for l in io.splitlines() if 'System RAM' in l and not l.startswith(' ')]
    L.append('')
    fdt = read(raw, 'live-fdt.dtb', binary=True)
    if fdt:
        L.append('## live device tree (/sys/firmware/fdt)')
        try:
            fdt_report(fdt_parse(fdt), cmdline, L)
        except ValueError as e:
            L.append(f'  parse error: {e}')
        L.append('')
    for name, title in (('drm.txt', 'DRM connectors'), ('fb0.txt', 'fbdev'), ('backlight.txt', 'backlight'),
                        ('input-devices.txt', 'input devices'), ('i2c-devices.txt', 'I2C devices'),
                        ('spmi-devices.txt', 'SPMI devices'), ('block-devices.txt', 'UFS LUNs (512-byte sectors)')):
        t = read(raw, name)
        if t and t.strip():
            if name == 'input-devices.txt':
                t = '\n'.join(l for l in t.splitlines() if l.startswith(('N:', 'P:', 'H:')))
            L += [f'## {title}', redact(t.strip()), '']
    ps = read(raw, 'power-supply.txt')
    if ps:
        keep = [l for l in ps.splitlines() if l.startswith('==') or re.search(
            r'_(DESIGN|CHARGE_FULL|TECHNOLOGY|TYPE|MODEL_NAME|CAPACITY)=|CHARGE_FULL_DESIGN', l)]
        L += ['## power supplies', redact('\n'.join(keep)), '']
    pt = read(raw, 'partition-table.txt')
    if pt and pt.strip():
        L += ['## partitions (name, device, start sector, size)']
        for l in pt.splitlines():
            f = l.split()
            if len(f) >= 4 and f[3].isdigit():
                L.append(f'  {f[0]:<20} {f[1]:<22} start {f[2]:>10}  {human(int(f[3]) * 512):>11}')
            else:
                L.append('  ' + l)
        ud = [l.split()[1] for l in pt.splitlines() if l.split()[:1] == ['userdata'] and len(l.split()) > 1]
        L += [f'  userdata -> {ud[0] if ud else "?"}  (tools/push-image-blocks.sh hardcodes /dev/block/sda17)', '']
    fw = read(raw, 'firmware-files.txt')
    if fw:
        hits = [l for l in fw.splitlines() if re.search(r'a630|a6xx|zap|gmu|sqe|^/', l)]
        L += ['## GPU firmware files visible', '\n'.join(hits) or '  (none visible - vendor/firmware not mounted?)', '']
    pdir = os.path.join(raw, 'partitions')
    if os.path.isdir(pdir):
        L.append('## boot / dtbo / vbmeta images (read-only dumps)')
        for p in PARTITIONS:
            b = read(pdir, p + '.img', binary=True)
            if b is None:
                continue
            L.append(f'{p}: {human(len(b))}')
            if p.startswith('boot'):
                info = bootimg_parse(b)
                for k, v in info.items():
                    if k == 'dtbs':
                        L.append(f'  DTBs: {len(v)}')
                        for where, size, ident in v:
                            L.append(f'    [{where}] {size} bytes ' + '; '.join(f'{a}={c}' for a, c in ident.items()))
                    else:
                        L.append(f'  {k}: {redact(str(v))}')
            elif p.startswith('dtbo'):
                info = dtbo_parse(b)
                for k, v in info.items():
                    if k == 'entries':
                        for e in v:
                            L.append('    ' + '; '.join(f'{a}={c}' for a, c in e.items()))
                    else:
                        L.append(f'  {k}: {v}')
            else:
                L.append('  ' + ', '.join(f'{k}={v}' for k, v in vbmeta_parse(b).items()))
        L.append('')
    gv = read(raw, 'fastboot-getvar-all.txt')
    if gv:
        keep = [l for l in gv.splitlines() if re.search(
            r'current-slot|slot-|unlocked|secure|version|product|variant|partition-size:(boot|dtbo|vbmeta|userdata|system|vendor)|'
            r'hw-revision|max-download|is-userspace|anti', l)]
        L += ['## fastboot getvar all (selected, redacted)', redact('\n'.join(keep)), '']
    di = read(raw, 'fastboot-oem-device-info.txt')
    if di:
        L += ['## fastboot oem device-info', redact(di.strip()), '']
    dm = read(raw, 'dmesg.txt')
    if dm:
        rx = re.compile(r'panel|dsi|mdss|sde|splash|synaptics|rmi4|touch|tp_|s3706|s3320|ufs|memory|ddr|'
                        r'pon|pwrkey|resin|gpio-keys|battery|bq27|fg_|board|project|hw_version|msm-id|board-id', re.I)
        hits = [l for l in dm.splitlines() if rx.search(l)][:400]
        L += ['## dmesg (selected lines, redacted)', redact('\n'.join(hits)), '']
    text = '\n'.join(L) + '\n'
    with open(os.path.join(outdir, 'summary.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    return text


# ---------------------------------------------------------------- collection

def write(raw, name, data):
    path = os.path.join(raw, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data if isinstance(data, bytes) else data.encode())


def collect_adb(outdir, use_su, partitions):
    raw = os.path.join(outdir, 'raw')
    phone = Phone(use_su)
    state = phone.connect()
    print(f'adb state: {state}, root: {phone.root}{" (via su)" if phone.wrap_su else ""}')
    skipped = []
    for name, cmd, needs_root in TEXT_COMMANDS:
        if needs_root and not phone.root:
            skipped.append(name)
            continue
        write(raw, name, phone.sh(cmd))
        print(f'  {name}')
    for name, cmd, needs_root in BINARY_COMMANDS:
        if needs_root and not phone.root:
            skipped.append(name)
            continue
        data = phone.sh(cmd)
        write(raw, name, data)
        print(f'  {name} ({len(data)} bytes)')
    if partitions and phone.root:
        byname = phone.sh(f'for d in {BY_NAME_DIRS}; do [ -d $d ] && echo $d && break; done').decode().strip()
        for p in PARTITIONS:
            if NEVER_READ.search(p) or p not in PARTITIONS:
                raise SystemExit(f'refusing to read {p}')
            dev = phone.sh(f'readlink -f {byname}/{p} 2>/dev/null').decode().strip()
            if not dev.startswith('/dev/block/'):
                print(f'  {p}: not found, skipped')
                skipped.append(p)
                continue
            sectors = phone.sh(f'cat /sys/class/block/{dev.rsplit("/", 1)[1]}/size 2>/dev/null').decode().strip()
            data = phone.sh(f'cat {byname}/{p}')
            want = int(sectors) * 512 if sectors.isdigit() else None
            note = '' if want in (None, len(data)) else f'  WARNING: expected {want} bytes'
            write(raw, os.path.join('partitions', p + '.img'), data)
            print(f'  partitions/{p}.img <- {dev} ({len(data)} bytes){note}')
    elif partitions:
        skipped.append('partitions (need root: OrangeFox/TWRP, or --su on rooted Android)')
    meta = [f'mode: adb ({state})', f'root: {phone.root}', f'collected: {datetime.datetime.now():%Y-%m-%d %H:%M}']
    if skipped:
        meta.append('skipped (no root or absent): ' + ', '.join(skipped))
    write(raw, 'meta.txt', '\n'.join(meta) + '\n')


def collect_fastboot(outdir):
    raw = os.path.join(outdir, 'raw')
    fb = tool('FASTBOOT', 'fastboot')

    def run(args):
        if tuple(args) not in FASTBOOT_ALLOWED:
            raise SystemExit(f'refusing fastboot command: {args}')
        try:
            p = subprocess.run(fb + list(args), capture_output=True, timeout=60)
        except FileNotFoundError:
            raise SystemExit(f'fastboot not found ({fb[0]}); install platform-tools or set FASTBOOT=')
        return (p.stdout + p.stderr).decode('utf-8', 'replace')

    devs = [l for l in run(['devices']).splitlines() if l.strip()]
    if not devs:
        raise SystemExit('no fastboot device: hold Volume Up + Power to enter fastboot, then connect USB')
    if len(devs) > 1:
        raise SystemExit('several fastboot devices connected')
    write(raw, 'fastboot-getvar-all.txt', run(['getvar', 'all']))
    write(raw, 'fastboot-oem-device-info.txt', run(['oem', 'device-info']))
    write(raw, 'meta.txt', f'mode: fastboot\ncollected: {datetime.datetime.now():%Y-%m-%d %H:%M}\n')
    print('  fastboot-getvar-all.txt, fastboot-oem-device-info.txt')


# ---------------------------------------------------------------- self-test

def _fdt_build(tree):
    strings, offs, st = bytearray(), {}, bytearray()

    def soff(name):
        if name not in offs:
            offs[name] = len(strings)
            strings.extend(name.encode() + b'\0')
        return offs[name]

    def pad():
        while len(st) % 4:
            st.append(0)

    def emit(node):
        name, props, children = node
        st.extend(struct.pack('>I', 1) + name.encode() + b'\0')
        pad()
        for k, v in props.items():
            st.extend(struct.pack('>III', 3, len(v), soff(k)) + v)
            pad()
        for c in children:
            emit(c)
        st.extend(struct.pack('>I', 2))

    emit(tree)
    st.extend(struct.pack('>I', 9))
    rsv = struct.pack('>QQ', 0, 0)
    off_struct = 40 + len(rsv)
    off_str = off_struct + len(st)
    total = off_str + len(strings)
    hdr = struct.pack('>10I', 0xd00dfeed, total, off_struct, off_str, 40, 17, 16, 0, len(strings), len(st))
    return hdr + rsv + bytes(st) + bytes(strings)


def selftest():
    import gzip
    import tempfile
    U = lambda *w: struct.pack('>%dI' % len(w), *w)
    S = lambda *s: b''.join(x.encode() + b'\0' for x in s)
    tree = ('', {'#address-cells': U(2), '#size-cells': U(2), 'model': S('Test enchilada'),
                 'compatible': S('qcom,sdm845'), 'qcom,msm-id': U(321, 0x20001), 'qcom,board-id': U(8, 0)},
            [('chosen', {'bootargs': S('androidboot.serialno=abc123de msm_drm.dsi_display0=dsi_test_cmd_display: x')}, []),
             ('memory', {'device_type': S('memory'), 'reg': U(0, 0x80000000, 1, 0)}, []),
             ('memory@180000000', {'reg': U(1, 0x80000000, 0, 0x7c8a0000)}, []),
             ('reserved-memory', {'#address-cells': U(2), '#size-cells': U(2)},
              [('cont_splash_region@9d400000', {'reg': U(0, 0x9d400000, 0, 0x2400000), 'no-map': b''}, [])]),
             ('tlmm@3400000', {'phandle': U(5), '#gpio-cells': U(2)}, []),
             ('ldo28', {'phandle': U(7), 'regulator-name': S('pm8998_l28')}, []),
             ('dsi_test_cmd_display', {'qcom,dsi-panel': U(9)}, []),
             ('qcom,mdss_dsi_test_cmd', {'phandle': U(9), 'qcom,mdss-dsi-panel-name': S('test sofef00 cmd'),
                                         'qcom,mdss-dsi-panel-type': S('dsi_cmd_mode')},
              [('qcom,mdss-dsi-display-timings', {},
                [('timing@0', {'qcom,mdss-dsi-panel-width': U(1080), 'qcom,mdss-dsi-panel-height': U(2280)}, [])])]),
             ('i2c@a90000', {'reg': U(0, 0xa90000, 0, 0x4000), '#address-cells': U(1), '#size-cells': U(0)},
              [('synaptics@20', {'compatible': S('synaptics,s3320'), 'reg': U(0x20),
                                 'synaptics,irq-gpio': U(5, 125, 0x2008), 'vcc_ana-supply': U(7)}, [])])])
    blob = _fdt_build(tree)
    root = fdt_parse(blob)
    lines = []
    fdt_report(root, 'msm_drm.dsi_display0=dsi_test_cmd_display:cfg0', lines)
    out = '\n'.join(lines)
    assert '0x80000000 + 0x100000000' in out and 'total: 0x17c8a0000' in out, out
    assert 'cont_splash_region' in out and '<== selected' in out and '= 2280' in out, out
    assert 'pin 125' in out and 'pm8998_l28' in out and 'bus /i2c@a90000 reg 0xa90000' in out, out
    assert 'abc123de' not in out, 'serial leaked through chosen/bootargs'
    # boot image v1: Image.gz followed by two DTBs
    dtb2 = _fdt_build(('', {'model': S('second'), 'qcom,msm-id': U(321, 0x20000)}, []))
    kernel = gzip.compress(b'\0' * 56 + b'ARM\x64' + b'\0' * 4000) + blob + dtb2
    ps = 4096
    hdr = bytearray(ps)
    hdr[:8] = b'ANDROID!'
    osv = ((17 << 14 | 0 << 7 | 0) << 11) | ((2035 - 2000) << 4) | 6
    struct.pack_into('<10I', hdr, 8, len(kernel), 0x8000, 0, 0x1000000, 0, 0, 0x100, ps, 1, osv)
    hdr[64:64 + 12] = b'console=null'
    struct.pack_into('<IQI', hdr, 1632, 0, 0, 1648)
    img = bytes(hdr) + kernel + b'\0' * ((-len(kernel)) % ps)
    info = bootimg_parse(img)
    assert info['header_version'] == 1 and info['kernel_format'] == 'gzip (Image.gz)', info
    assert len(info['dtbs']) == 2 and info['dtbs'][1][2]['qcom,msm-id'] == '0x141 0x20000 (321 131072)', info
    assert info['os_version'] == '17.0.0, patch 2035-06', info
    # dtbo table with one overlay
    ov = _fdt_build(('', {'compatible': S('oneplus,enchilada'), 'qcom,board-id': U(8, 0, 17819, 22)}, []))
    tbl = struct.pack('>8I', 0xd7b7ab1e, 32 + 32 + len(ov), 32, 32, 1, 32, 4096, 0)
    tbl += struct.pack('>8I', len(ov), 64, 0x1234, 1, 0, 0, 0, 0) + ov
    d = dtbo_parse(tbl)
    assert d['entry_count'] == 1 and d['entries'][0]['qcom,board-id'] == '0x8 0x0 0x459b 0x16 (8 0 17819 22)', d
    # redaction
    r = redact('[ro.serialno]: [abc123de]\n[ro.boot.wifimacaddr]: [00:11:22:33:44:55]\n'
               '(bootloader) serialno:abc123de\nandroidboot.serialno=abc123de androidboot.imei=356938035643809\n'
               'mac 00:11:22:33:44:55 imei 356938035643809\n[ro.product.device]: [OnePlus6]')
    assert 'abc123de' not in r and '00:11:22' not in r and '356938035643809' not in r, r
    assert '[ro.product.device]: [OnePlus6]' in r, r
    # guards: every built-in command passes, write-like commands do not
    for _, cmd, _ in TEXT_COMMANDS + BINARY_COMMANDS:
        ensure_readonly(cmd)
    for bad in ('dd if=/dev/zero of=/dev/block/sda17', 'echo 1 > /sys/x', 'mount -o rw /system',
                'setprop a b', 'cat x | tee /data/y', 'rm -rf /sdcard', 'reboot bootloader',
                "cat '/x'", 'blockdev --setrw /dev/block/sda', 'cp /a /b', 'magisk --remove-modules',
                'stop', 'getprop; start adbd', 'for x in a; do sync; done', 'input keyevent 26',
                'toybox touch /data/x', 'cat $(svc power reboot)'):
        try:
            ensure_readonly(bad)
        except SystemExit:
            continue
        raise AssertionError(f'guard let through: {bad}')
    for p in PARTITIONS:
        assert not NEVER_READ.search(p), p
    for p in ('persist', 'modemst1', 'modemst2', 'fsg', 'fsc', 'xbl_a', 'abl_b', 'tz_a', 'modem_a'):
        assert NEVER_READ.search(p), p
    # summary end-to-end on a synthetic dump
    with tempfile.TemporaryDirectory() as t:
        raw = os.path.join(t, 'raw')
        write(raw, 'meta.txt', 'mode: selftest\n')
        write(raw, 'getprop.txt', '[ro.product.device]: [OnePlus6]\n[ro.serialno]: [abc123de]\n[ro.boot.slot_suffix]: [_a]\n')
        write(raw, 'cmdline.txt', 'androidboot.serialno=abc123de msm_drm.dsi_display0=dsi_test_cmd_display:cfg0\n')
        write(raw, 'live-fdt.dtb', blob)
        write(raw, 'partition-table.txt', 'userdata /dev/block/sda17 1234 223338299\nboot_a /dev/block/sde11 10 131072\n')
        write(raw, os.path.join('partitions', 'boot_a.img'), img)
        write(raw, os.path.join('partitions', 'dtbo_a.img'), tbl)
        s = summarize(t)
        assert 'abc123de' not in s and 'userdata -> /dev/block/sda17' in s and 'DTBs: 2' in s, s
    print('selftest: ok')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--fastboot', action='store_true', help='phone in fastboot mode: getvar all + oem device-info')
    ap.add_argument('--su', action='store_true', help='rooted Android: read root-only files through su')
    ap.add_argument('--no-partitions', action='store_true', help='do not read boot/dtbo/vbmeta partitions')
    ap.add_argument('--out', help='output directory (default facts/<date>-<time>)')
    ap.add_argument('--summarize', metavar='DIR', help='only rebuild DIR/summary.txt from DIR/raw')
    ap.add_argument('--selftest', action='store_true', help='offline test of parsers and guards')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.summarize:
        summarize(a.summarize)
        print(os.path.join(a.summarize, 'summary.txt'))
        return
    here = os.path.dirname(os.path.abspath(__file__))
    out = a.out or os.path.join(here, '..', 'facts', datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    out = os.path.normpath(out)
    os.makedirs(os.path.join(out, 'raw'), exist_ok=True)
    if a.fastboot:
        collect_fastboot(out)
    else:
        collect_adb(out, a.su, not a.no_partitions)
    summarize(out)
    print(f'done: {os.path.join(out, "summary.txt")}  (raw/ holds unredacted data - keep it private)')


if __name__ == '__main__':
    main()
