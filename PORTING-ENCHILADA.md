# Porting ios-fajita to the OnePlus 6 (`enchilada`)

The OnePlus 6 and the OnePlus 6T share the SDM845 board design almost completely: same SoC
revision, same PMICs, same touch controller wiring, same framebuffer region, same partition
scheme. What differs is the **panel height (2280 instead of 2340)**, the board id, the battery,
and whatever is specific to one unit (RAM size, firmware, slot state). This file lists every
difference that touches code, what is already known, what still has to be read from the phone,
and the bring-up plan.

Conventions used below:

- **observed (6T)** / **observed (OP6)**: seen on real hardware (the 6T work in `NOTES-FAJITA.md`;
  the OP6 attempt in `awa-xaga/ios-enchilada`, remote `enchilada`, its `NOTES.md`).
- **DT / source**: from the mainline or downstream device trees and drivers, or from this tree.
- **this unit**: read from the phone this port targets with `tools/enchilada-facts.py`
  (`facts/<date>/summary.txt`, not in git).
- **inference**: a conclusion, not a measurement.

## 1. This unit (measured 2026-10-28 with `tools/enchilada-facts.py`, root pass)

| Item | Value | Note |
| --- | --- | --- |
| Model | ONEPLUS A6003, `project_name 17819`, `hw_version 22`, `rf_version 34`; live FDT model "SDM845 v2.1 MTP PVT", `qcom,board-id <8 0 17819 22>` | the enchilada PVT board |
| SoC | SDM845 v2.1, `qcom,msm-id <321 0x20001>`, PMIC PM8998 (`pmic_model 65556`), SPMI slaves 0–5 | same msm-id as the 6T unit |
| RAM | `/memory` 0x80000000+0x100000000 and 0x180000000+0xfc8a0000 (7.95 GiB, `MemTotal 7824764 kB`); `/proc/iomem` System RAM 0x97d00000–0x27c89ffff | **identical to the 6T unit**: `mkadt.py` `HIGH_MEM_SIZE 0x17c8a0000` is already right |
| Carve-outs | all below 0xad200000: hyp 0x85700000, xbl, removed_region 0x85fc0000–0x8ab00000 (holds the cmd-db at 0x85fe0000), qseecom, camera, ips/ipa, `gpu_region 0x8c415000` (8 KiB), adsp, wlan, modem 0x8e000000 (120 MiB), video, cdsp, mba, slpi, spss, `cont_splash_region 0x9d400000+0x2400000`, bootloader_log 0x9fff7000, param 0xac200000, ramoops 0xac300000 (4 MiB), mtp_mem 0xac700000 | nothing above 4 GiB; the same picture as the 6T |
| OS | LineageOS 22 (Android 15, **user** build `BP1A.250505.005`, vendor built 2025-12-24) + Magisk 30.7 | `adb root` impossible; root only through Magisk `su` (grant "Shell") |
| Lock state | ABL cmdline `androidboot.verifiedbootstate=orange`; `vbmeta_a/b` flags 3 (hashtree + verification disabled) | **unlocked**; the `getprop` "locked/green" values are spoofed by a Magisk module |
| fastboot (`getvar all`, `oem device-info`) | `unlocked: yes`, `Device critical unlocked: false`, `secure: yes`, `Verity mode: true`; `current-slot: b`, `slot-successful a/b: yes`, `slot-unbootable: no`, `slot-retry-count a: 7, b: 6`; `max-download-size 0x30000000` (768 MiB); `boot_a/b 0x4000000`, `dtbo 0x800000`, `vbmeta 0x10000`, `userdata 0x1B800BB000` (ext4); `product sdm845`, `variant SDM UFS`, `hw-revision 20001`, `version-bootloader` empty; battery 3.84 V | the ABL does not report its version; flashes above 768 MiB need `-S 512M`; each boot without "successful" consumes one retry, at zero ABL switches slots |
| Slots | active `_b`; `boot_a` and `boot_b` hold the same LineageOS kernel | slot `a` is the test slot |
| Boot image (LineageOS) | header v1, page 4096, kernel 0x8000, ramdisk 0x1000000, tags 0x100, `Image.gz` 15.2 MB → 37.6 MB, os_version 15.0.0 / 2025-12; 3 appended DTBs: SDM845 **v1** (`msm-id 0x141 0x10000`), **v2** (`0x20000`), **v2.1** (`0x20001`), all `board-id 0`; `dtbo` with 16 board overlays (index 5 = PVT 17819/22, index 10 = the 6T's 18801/41) | ABL chose `dtb_idx 2` (v2.1) + `dtbo_idx 5`; the shim appends the v2.1 SoC DTB, the overlay comes from the `dtbo` partition as on the 6T |
| Panel | ABL: `msm_drm.dsi_display0=dsi_samsung_sofef00_m_cmd_display:`; node `qcom,mdss_dsi_samsung_sofef00_m_cmd` (primary, `dsi-display@18`): `dsi_cmd_mode`, 24 bpp, 4 lanes, burst, TE pin 1, 1080×2280 @ 60 Hz, porches h 112/36/16, v 36/12/8, no DSC, 68×145 mm, reset gpio 6, VCI gpio 26, POC gpio 25, reset sequence 1-5/0-2/1-12 ms, DCS backlight 1..1023 (at 1023); DRM mode `1080x2280x60`, 151.372 MHz | command-mode AMOLED kept alive by ABL |
| Touch | `/soc/i2c@a90000/synaptics-rmi-ts@20`, `HWK,synaptics,s3320`, input "synaptics,s3320"; IRQ tlmm 125, reset tlmm 99, 1.8 V enable tlmm 88, `vdd_2v8-supply` → `pm8998_l28` (rpmh `ldoa28`) 3.008 V, tx/rx 15×30, `display-coords`/`panel-coords` 1080×2160 | identical to the 6T wiring |
| Keys | PON: `pon_1` KEY_POWER, `pon_2` (RESIN) KEY_VOLUMEDOWN; `gpio_keys`: vol_up = PM8998 GPIO6, vol_down = GPIO5 (active low), hall sensor tlmm 124; alert slider = `uinput-tri-state-key` | as the 6T (volume down also on RESIN) |
| Storage | Samsung KLUDG4U1EA-B0C1 UFS 2.1 (128 GB), LUN0 116 GiB; `userdata = sda17`, 110 GiB, first 4 KiB block 0x186f40 (same as the 6T); `boot_a sde11`, `boot_b sde39`, `dtbo sde18/46`, `vbmeta sde17/45`, `persist sda2`, `modemst1/2 sdf2/3`, `fsg sdf4`, `fsc sdf5`, `xbl sdb1/sdc1`, `abl sde8/36`, `LOGO sde20/48` | the 6T layout; `tools/push-image-blocks.sh` default is right |
| Battery | `OP_3300mah`, design 3240 mAh (full 3057 mAh now), bq27541 gauge, SMB1355 chargers | 6T: 3700 mAh; no code depends on it |
| GPU firmware | `/vendor/firmware/a630_gmu.bin` (32768 B), `a630_sqe.fw` (32136 B), `a630_zap.mdt` (6684 B), `.b00/.b01/.b02` (148/6536/1968 B), `.elf` | the OP6's own copies for the payload blobs |
| Other | fingerprint FPC1020 (the DT also has a goodix node), MAX98927 amp, NQ NFC, `oneplus_fastchg` | unused by the port |

Still unknown: whether this ABL accepts `fastboot boot`, the APCS watchdog behaviour, the raw touch
range and the key PPIDs (kernel log on the first boots).

## 2. Differences at a glance

| Area | OnePlus 6T (`fajita`) | OnePlus 6 (`enchilada`) | Status | Code |
| --- | --- | --- | --- | --- |
| Panel | Samsung S6E3FC2X01, 1080×2340, 68×148 mm | Samsung SOFEF00 (AMS628NW01), 1080×2280, 68×144 mm | DT; 2280 confirmed by the OP6 lock screen | §3.1 |
| Panel mode | downstream `dsi_cmd_mode` + TE, no DSC; mainline video-burst | `dsi_samsung_sofef00_m_cmd_display`: `dsi_cmd_mode`, TE, no DSC, 60 Hz (this unit) | measured; the port never programs DSI | §3.1 |
| Framebuffer | `cont_splash` 0x9d400000, 36 MiB, stride 4320, ARGB8888 | same address and size (this unit's FDT, observed (OP6)) | **same** | §3.1 |
| Logical screen | iPhone X 1125×2436, panel centred, fOffY = 48 | fOffY = 78 on the display side, HID still hardcodes 48 | source | §3.2 |
| Touch IC | Synaptics RMI4 (S3320 downstream / S3706B mainline) on SE12 `0xa90000`, 0x20, ATTN 125, reset 99, VIO gpio88, VDD `ldoa28` 3.008 V | identical wiring (this unit's FDT: `HWK,synaptics,s3320`, irq 125, reset 99, 1v8 88, `pm8998_l28` 3.008 V); Y clip 2279 instead of 2339 | **same hardware**, scaling changes | §3.3 |
| Keys | PM8998 PON (power), GPIO5 (vol−), GPIO6 (vol+) | identical (this unit's FDT; vol− also on PON RESIN) | same, PPIDs still to probe | §3.4 |
| Alert slider | tlmm 126/52/24 | identical | not handled anywhere | §3.4 |
| RAM | 6/8/10 GB; the 8 GB unit: 0x80000000+0x100000000, 0x180000000+0xfc8a0000 | 6/8 GB; **this unit: the same two banks and the same carve-outs** (the OP6 attempt's unit had 0x180000000+0xfcba0000) | same, measured | §3.5 |
| Board id | `<8 0 18801 41>` | `<8 0 17819 22>` (this unit) | known | §3.6 |
| Boot image | header v1, `Image.gz` + appended DTB table, page 4096, base 0 | identical: this unit's LineageOS `boot_a/b` are v1 with 3 SoC DTBs (v1/v2/v2.1) + a 16-entry `dtbo`; AVB verification disabled | same, measured | §3.6 |
| `fastboot boot` | not used for the shim on the 6T (flash `boot_a` + `--set-active=a`); works for OrangeFox | worked for every OP6 attempt boot on that unit's firmware | **test on this unit** | §3.6 |
| Watchdog | nothing in the fajita tree; boots for hours | OP6 attempt saw a hard reset at ~150 s until a kernel thread petted the APCS WDT at 0x17980000 | **test on this unit** | §3.9 |
| Panic log `/pram` | top of the XNU DRAM range (`mkadt.py`) | OP6 attempt: top of range hung early boot, 0x100000000 worked; this unit's map equals the 6T's, so the 6T placement is the first thing to try | unexplained | §3.5 |
| IMEM restart reason | 0x146bf65c | same (SoC); the sweet value sent the OP6 into 900E | same | §3.9 |
| UFS | host 0x1d84000, UFS 2.1, `userdata=sda17` from block 0x186f40 | same (this unit: Samsung KLUDG4U1EA 128 GB, `userdata=sda17` at 0x186f40, 110 GiB) | same | §3.8 |
| Battery | 3700 mAh | 3300 mAh | no code depends on it | §3.10 |
| Audio amp | TFA9894 | MAX98927 | irrelevant | — |
| GPU | Adreno 630, firmware + OnePlus-signed zap | same SoC; this unit's `/vendor/firmware` has `a630_gmu.bin`, `a630_sqe.fw`, `a630_zap.mdt/.b00-.b02` | SoC-level | §3.10 |

## 3. Details

Each item: what is known, what to measure on the phone (read-only), where it is in the code.

### 3.1 Display panel and framebuffer

Known:

- The port does not drive DSI, the MDP or the backlight. ABL initialises the panel and leaves it
  scanning out the continuous-splash buffer; the shim, the early console and `AppleCLCD`
  (patches 0010/0012/0046/0056/0061) just write pixels into that buffer. Panel mode (command vs
  video), DSC and timings therefore do not matter as long as ABL keeps scanning out. Observed (OP6):
  the shim console and the iOS lock screen rendered this way on the OP6's command-mode panel.
- Both phones: `splash@9d400000 reg <0 0x9d400000 0 0x02400000>` (`sdm845-oneplus-common.dtsi`),
  `stride 4320`, `a8r8g8b8`; only `height` differs (`sdm845-oneplus-enchilada.dts`: 2280;
  `-fajita.dts`: 2340). Observed (OP6): live FDT `SPLASH 0x9D400000 / SPLSIZE 0x2400000`.
- Downstream panel: `dsi-panel-samsung_sofef00_m_cmd.dtsi` (`dsi_cmd_mode`, TE pin, no
  `compression-mode`), node label `dsi_samsung_sofef00_m_cmd_display`; a `_video` variant exists.
  Mainline: `panel-samsung-sofef00.c` (video burst, 4 lanes, RGB888, htotal 1244, vtotal 2336).
- This unit (live FDT): `qcom,mdss_dsi_samsung_sofef00_m_cmd` is the primary display
  (`dsi-display@18`): `dsi_cmd_mode`, 24 bpp, 4 lanes, burst, TE pin 1 with `te-using-te-pin`, no
  `compression-mode`, timing 1080×2280 @ 60 Hz (h 112/36/16, v 36/12/8), 68×145 mm, reset gpio 6,
  VCI gpio 26, POC gpio 25, reset sequence 1-5 ms / 0-2 ms / 1-12 ms, DCS backlight 1..1023; DRM mode
  `1080x2280x60`, 151.372 MHz. Brightness is whatever ABL leaves (Android had it at 1023).
- Rows 2280..2339 of the 6T layout exist in memory but are never scanned out on the OP6: the
  early-console stage band at row 2308 and the stage markers (patch 0010) become invisible.

Measure (root): `cat /proc/cmdline | tr ' ' '\n' | grep msm_drm` (the panel ABL selected),
`xxd /proc/device-tree/reserved-memory/*splash*/reg`, the panel node under the live FDT
(`qcom,mdss-dsi-panel-type`, width/height, `qcom,compression-mode`), `cat /sys/class/drm/card0-DSI-1/modes`,
`dmesg | grep -iE 'splash|dsi|panel'`. `enchilada-facts.py` prints all of these.

Code (height 2340 → 2280, the base stays if the FDT confirms 0x9d400000):

| Location | What |
| --- | --- |
| `shim/console.h:6` `FB_H` | shim console and `boot_args.Video` (`shim/loader.c:371`) |
| `shim/mmu.h:4` `FB_PHYS` | 32 MiB block mapping, unchanged if the base is the same |
| `tools/fajita.env:6-12` | `FB_H`; documentation values |
| `tools/mkadt.py:35-37` | `FB_H` in the `sweet-fbcon` node |
| `xnu/patches/0010:99` `(0x9d400000 + 2308*4320)`, `:163` `EARLY_HEIGHT 2340u` | stage band row = height−32; early console rows |
| `xnu/patches/0012:104,142` | same base and `+0x1400000` offset into the 0x9c000000 block, unchanged |
| `xnu/patches/0084` | inherits `EARLY_HEIGHT` |

### 3.2 iPhone X presentation and HID geometry

Known (source): patch 0061 presents a 1125×2436 plane and shows the centred panel-sized part of
it with no scaling. The display side computes `fOffY = (2436 − fHeight)/2` from `PE_Video`, so it
adapts by itself: 78 on the OP6 instead of 48 (more of the status bar and the home indicator are
cropped). The HID side does not adapt:

| Location | Problem | Fix |
| --- | --- | --- |
| `xnu/patches/0061:107-109` `fLogicalH = native ? 2340 : 2436; fOffY = (fLogicalH - 2340)/2` | touch offset hardcoded for 2340 → touches land 30 px too high on 2280 | take width/height from `AppleCLCD` (the OP6 attempt did this in its patch 0087 `sweet_panel_w/h`) |
| `xnu/patches/0071:32` `y > 2399 - SWEET_TOUCH_EDGE_PX` | bottom-edge flag unreachable on 2340 and 2280 (sweet leftover) → bottom-edge gestures never flagged | `y > panel_h - 1 - EDGE` |
| `xnu/patches/0058:~21042` `y > 2399 ? 2399` | sweet clamp | `panel_h - 1` |
| `xnu/patches/0090:78,208,245` `ts_yraw = 2340`, `py = ry*2340/ts_yraw`, clamp 2339 | raw→pixel scale | 2280 / 2279; raw maxima from the touch log |
| `xnu/patches/0058:~21024` `SurfaceHeight 148 << 16` | digitizer size in mm | 144 for the OP6 |

Observed (OP6): the attempt's synthetic unlock swipe failed until these constants were derived
from the panel, and still did not unlock afterwards (cause unknown).

### 3.3 Touch controller

Known: identical on both phones in every public source and on this unit (`synaptics-rmi-ts@20`
under `i2c@a90000`): QUPv3 SE12 (`GCC_QUPV3_WRAP1_S4`, vote bit 26 + AHB bits 20/21 at `0x5200c`,
RCG `0x184d8`, CBCR `0x184d4`), I²C 0x20, pins gpio49/50 (qup12), reset gpio99, 1.8 V enable gpio88,
ATTN gpio125, VDD `pm8998_l28` (RPMh `ldoa28`) 3.008 V, `syna,reset-delay-ms 200`. Mainline
per-device values: `syna,clip-y-high 2279` / `touchscreen-y-mm 144` (OP6) vs 2339 / 148 (6T).

Observed (6T), to keep as-is: gpio88 and gpio125 live in the TLMM **EAST** tile (0x03500000), gpio99
and 49/50 in NORTH (0x03900000) — patch 0096; the first guess (SOUTH/NORTH, which the OP6 attempt's
patch 0088 still uses) froze the SoC. Two-transaction RMI reads (0098), both TX/RX lengths (0097),
RPMh apps RSC 0x179e0000 / TCS 0x179e0d00 (boot-args `rpmhrsc`/`rpmhtcs`, patch 0093); the OP6
attempt's note "RSC 0x179c0000" contradicts the hardware-verified value and must not be used.
The 6T raw maxima seen were 1063/2326, so the real OP6 range must be read from the
`SWEET TS: raw max` log line (boot-args `sweetts_xraw`/`sweetts_yraw` override the defaults).

Measure (root): the touch node's properties (`enchilada-facts.py` prints reg, irq/reset/1v8 gpios,
supplies), `getevent -lp` for `ABS_MT_POSITION_X/Y` max on Android,
`dmesg | grep -iE 'synaptics|rmi|s3320|s3706'`, `/proc/interrupts | grep -i touch`.

Code: `tools/fajita.env:36-41` (documentation), `xnu/patches/0090` (`FJ_*` constants are SoC-level;
only the 2340/2339 scaling changes), 0092 (ldoa28 voltage window is fine), 0095 (bisect switches
`sweetts_nogpio/noclk/nose/norail`, `sweettouchdelay`), 0096/0097/0098 (reuse unchanged).

### 3.4 Keys, PMIC, alert slider

Known (DT, both phones): power = PM8998 PON (KPDPWR), volume down = `pm8998_gpios 5`, volume up =
`pm8998_gpios 6`; SPMI arbiter core 0xc440000, observer 0xe600000, config 0xc40a000 (SoC). Observed
(6T): PPID 0x0c4 (GPIO5) / 0x0c5 (GPIO6), HID usages 0x30/0xea/0xe9; patch 0091 finds the pair by
PPID, patch 0089 adds the read-only scan `sweetkeysprobe=1`. The alert slider (tlmm 126 silent,
52 vibrate, 24 ring) and the hall sensor (tlmm 124) are handled by neither port. PMIC model on this
unit: PM8998 (`pmic_model 65556`).

Measure: `cat /proc/bus/input/devices` (root on this ROM), `getevent -lp`; the key PPIDs with one
boot of the kernel with `sweetkeysprobe=1`.

Code: `xnu/patches/0091` (should work unchanged), `tools/fajita.env:44-46`.

### 3.5 RAM and the memory map

Known:

- The ADT tells XNU `dram-base 0x100000000`, `dram-size 0x17c8a0000 − 1 MiB`, and the payload
  header copies the same numbers (`tools/mkadt.py:21-22`, `tools/mkpayload.py:158`). They were
  **measured on one 8 GB 6T** (`/memory` = 0x80000000+0x100000000 and 0x180000000+0xfc8a0000; all
  `reserved-memory` below 0xac800000). The `/pram` panic-log region is carved out of the top of
  that range (`PANIC_LOG_SIZE 0x100000`). Observed (OP6, another 8 GB unit): second bank
  0x180000000+0xfcba0000, i.e. 3 MiB more; a 6 GB unit will be very different. A wrong size is a
  silent early hang (the kernel maps or touches RAM that is not there).
- **This unit**: `/memory` = 0x80000000+0x100000000 and 0x180000000+0xfc8a0000, `System RAM`
  0x97d00000–0x27c89ffff, every carve-out below 0xad200000 — the same as the 6T unit, so
  `HIGH_MEM_SIZE 0x17c8a0000` and the `/pram` placement at 0x27c7a0000 can be tried unchanged. The
  rule stays for any other unit: measure first.
- `mkadt.py --dram-size=0x...` already overrides the size without editing the file.
- Observed (OP6): `/pram` at the top of the range hung in `check_for_panic_log`, 1 MiB below the
  base hung too, 0x100000000 (inside the low bank, outside the ADT DRAM) worked. On the 6T the
  top-of-range placement works. Unexplained; keep both options available.
- Low bank: the cmd-db at 0x85fe0000 (0099/0135) and the zap carve-out `gpu_region` at
  0x8c415000 (0146) are DT carve-outs the GPU path relies on and are not declared to XNU; patch
  0110 also introduced `GPU_SCRATCH_PA 0x0b000000` for the first HFI experiments (later stages
  moved the GMU memory into the `gmem` payload blob — check what the final tree still uses). The
  same addresses are expected on the OP6 (same SoC DT base) but must be checked against this
  unit's `reserved-memory`.
- Pages below `gPhysBase` are an allocator trap (`kmem_alloc_contig`/`IOBufferMemoryDescriptor`
  panic on them, `NOTES-FAJITA.md` console80); GPU/DMA memory comes from payload blobs
  (`sweetfwN=<pa>:<size>`), whose addresses move with the kernel size.

Measure (root): `xxd /proc/device-tree/memory*/reg`, every `reserved-memory/*/reg`,
`cat /proc/iomem` (`System RAM` ranges), `grep MemTotal /proc/meminfo`. `enchilada-facts.py` decodes
the FDT into a sorted carve-out list and the total.

Code: `tools/mkadt.py:15-29` (`HIGH_MEM_SIZE`, `PANIC_LOG_SIZE` placement), `tools/fajita.env:17-24`,
`shim/mmu.c:272` (diagnostic identity map covers 8 GiB; the 8 GB map ends below 10 GiB).

### 3.6 Boot image, DTB selection, ABL

Known:

- Both ABLs want **header v1**, `Image.gz` with the DTB table appended, page 4096, base 0, kernel
  offset 0x8000, ramdisk 0x1000000, tags 0x100 (LineageOS `sdm845-common` `BoardConfigCommon.mk`,
  pmOS deviceinfo). Observed (6T): header v2 or a raw `Image` is rejected (back to fastboot after
  ~20 s). Observed (OP6): the same v1 container booted through `fastboot boot`
  (`enchilada:tools/mkenchilada.py`: gzip(shim) + the three FDTs of the stock `Image.gz-dtb` + the
  payload as ramdisk; `os_version 0x220001a8` copied from stock). `shim/build.sh` with
  `SHIM_HDR=1` produces the same layout.
- ABL selects the DTB by `qcom,msm-id` / `qcom,board-id` and passes the chosen, patched tree in
  `x0` (observed on both phones at 0x853FD000); `shim/fdt.c:fdt_locate` also scans from `_end`.
  The 6T build appends only the matching DTB (`fajita2.dtb` = SDM845 v2.1). For this unit
  `ro.boot.dtb_idx=2` says ABL picked the third appended DTB of the LineageOS boot image; its
  identity (expected `qcom,msm-id <321 0x20001>`, `qcom,board-id <8 0 17819 22>`) comes from the
  `boot_b` dump: **three SoC DTBs** — SDM845 v1 (`msm-id 0x141 0x10000`), v2 (`0x20000`), v2.1
  (`0x20001`), all with `board-id 0` — so index 2 is the v2.1 SoC tree, exactly like `fajita2.dtb`
  on the 6T; the board part is the `dtbo` overlay (16 entries, index 5 = `17819/22` PVT, index 10 =
  the 6T's `18801/41`), which ABL merges before passing the tree in `x0`. The port never reads the
  overlay itself.
- `fastboot boot`: used for every OP6 attempt boot (nothing flashed) and for OrangeFox on the 6T,
  but `PORTING.md` records "unknown command" on OOS 10/11 ABLs. This unit runs LineageOS 22 on
  OOS 11 firmware; the only way to know is to try it. The cheapest test needs no shim: `fastboot boot`
  the dumped `boot_b.img` (the Android image already in the active slot) — if ABL takes it, Android
  simply boots from RAM; if it answers "unknown command", the shim goes to `boot_a`.
- AVB: this unit's `vbmeta_a/b` carry flags 3 (hashtree and verification disabled) and ABL's own
  cmdline says `androidboot.verifiedbootstate=orange`, i.e. the bootloader is unlocked and an
  unsigned `boot_a` boots; the getprop `locked/green` values are a Magisk module's spoof. Confirm
  once more with `fastboot getvar unlocked` when the bootloader driver is in place.

Measure: in fastboot (`python3 tools/enchilada-facts.py --fastboot`): `getvar all` →
`unlocked`, `current-slot`, `slot-successful:a/b`, `slot-retry-count:a/b`, `slot-unbootable:a/b`,
`version-bootloader`, `partition-size:boot_a`, `is-userspace`. With root: `boot_a`/`boot_b` headers
and DTB identities (the facts tool decodes them), `dtbo` entries.

Code: `shim/build.sh:9` (`DTB=` default `fajita2.dtb` → the OP6 DTB), `:38-50` (header fields),
`tools/build-fajita.sh:15-18`, `tools/fajita.env:26` (`DTB_DEFAULT`), `tools/extract-dtb.py`
(extract the appended table from the dumped `boot_b`), `tools/unpack_bootv2.py`.

### 3.7 cmdline and boot-args

The boot image cmdline is `console=null` (ABL appends `androidboot.*`, the serial number and
`msm_drm.dsi_display0=`; the shim ignores it). The XNU boot-args travel in the payload
(`tools/build-fajita.sh:50`). For the OP6:

| Boot-arg | 6T default | First OP6 boots | Why |
| --- | --- | --- | --- |
| `cpus=8 sweetsmp=1` | on | `cpus=1 sweetsmp=0` first, then 8 | PSCI is SoC-level, but one less variable per boot |
| `sweetfb_noconsole=1 sweetecon=1` | on | `sweetfb_console=1 sweetecon=1`, no `noconsole` | keep the kernel console on the panel until the GUI is known to present; the OP6 attempt saw a black panel with `noconsole=1` (older base) |
| `sweetfb_hz=10` | on | keep | memcpy refresh rate |
| `sweettouch=1 sweetts=1 sweettouchdelay=20` | on | `sweettouch=0 sweetts=0` until the FDT confirms the wiring, then on with the bisect flags | a wrong pin tile freezes the SoC |
| `sweetkeys=1` | on | `sweetkeys=0`, then `sweetkeysprobe=1` once, then on | read-only probe first |
| `rpmhrsc=0x179e0000 rpmhtcs=0x179e0d00` | on | keep | SoC-level, hardware-verified |
| `sweetlog=1` | on | keep (`ufslogsecs=` to space the flushes) | the OP6 attempt had flush stalls on an older base without patch 0069 |
| `wdt=-1 wdt_test=no_user_checkin nointr_consio=1 rd=ufsroot0 ufsrw=1 rootrw=1 launchd_unsecure_cache=1 unentitled_ios_sim_launch=1 ignition_level=1 keepsyms=1 -noprogress debug=0xc serial=3` | on | keep | device-independent |
| `sweetts_xraw/yraw` | — | add after the first touch log | raw range of the OP6 sensor |
| `adreno=… zap=1 gpuhold=1` | optional | off until the home screen works | GPU ladder |

`sweetfwN=` entries are generated by `mkpayload.py`; never hardcode them.

### 3.8 Storage, root, log ring

Known: UFS host 0x1d84000 (SoC), UFS 2.1, 4 KiB blocks. The kernel finds the root by GPT name
(`rd=ufsroot0`, default `userdata`, patch 0028) and keeps the 4 MiB log ring in the last 1025
blocks of the same partition (0047/0094). On this unit (Samsung KLUDG4U1EA-B0C1, 128 GB)
`userdata` is `/dev/block/sda17`, 110 GiB from 4 KiB block 0x186f40 (the 6T's first block too), so
`tools/push-image-blocks.sh:19` and `tools/sweet-log-pull.sh` work; the iOS root image (16 GiB
HFS+ from `tools/mkiosroot.sh`) fits a 128 GB phone's ~110 GiB userdata. **Flashing userdata
erases all Android user data** (apps, photos, Magisk modules); Android itself (slot b) stays
bootable and starts fresh.

Measure (root): `blockdev --getsize64 /dev/block/by-name/userdata`, `/sys/block/sda/size`.

### 3.9 Watchdog, reset path, 900E

- IMEM restart reason 0x146bf65c and PS_HOLD 0x0c264000 are SDM845 constants (`shim/shim.c:16-18`).
  Observed (OP6): the sweet address 0x146aa65c put the phone into Qualcomm 900E (EDL) after the
  diagnostic shim. The corrected value is already in this tree.
- APCS/KPSS watchdog `qcom,wdt@17980000`: observed (OP6 attempt) hard reset ~144–167 s into the
  boot with nothing on the panel; an SCM "disable secure wdog" call and zeroing the registers did
  not help, a kernel thread writing `+0x04=1, +0x08=0, +0x38=1, +0x40=0` every 2 s did
  (`enchilada:xnu/patches/0082`). The fajita tree has no such code and the 6T runs for hours. Whether
  this depends on the firmware or on that unit is unknown: watch for a reset at ~150 s on the
  first kernel boot and port the pet thread only if it appears.
- The shim's self-reset (restart reason + PSCI `SYSTEM_RESET` + PS_HOLD) is unreliable on both
  phones; after a hang, power-cycle by hand (Power + Vol−; Power + Vol+ for fastboot on the OP6).
  Observed (OP6): after a test boot the phone could land in 900E; a 10–15 s power hold, then
  Vol+/Vol− + USB, brought back fastboot.

### 3.10 GPU, battery, USB

- GPU: every register base and the ladder (`xnu/patches/0099-0167`) are SoC-level. Board-level
  inputs: the firmware files `a630_gmu.bin` (32768 B), `a630_sqe.fw` (32136 B), `a630_zap.mdt`
  (6684 B) with `.b00/.b01/.b02` (148/6536/1968 B) — all present in **this phone's**
  `/vendor/firmware`; copy them from there (the zap is OEM-signed; do not reuse the 6T copies), the DT carve-outs (§3.5), and the `qcom,gpu-speed-bin` if the GX vote
  misbehaves. Keep the GPU boot-args off until the home screen works.
- Battery: 3300 mAh vs 3700 mAh; the port has no battery/charger driver for PM8998/PMI8998 (the
  `SweetBattery` SPMI addresses are sweet's PM6150 ones) — nothing to change for the bring-up.
- USB: patch 0072–0077 use sweet (SM7150) offsets and are not part of the boot path; the OP6 DWC3
  is at 0xa600000 like the 6T.

### 3.11 Identity / ADT

Unchanged: `D22AP`/`iPhone10,3`, the real `/product` of the iPhone X, `display-scale 3`, canvas
1125×2436, `xiaomi,sweet` kept in `compatible` because the platform expert matches it; add
`oneplus,enchilada` next to `oneplus,fajita` (`tools/mkadt.py:322`). `qcom,kryo385` CPU match
(patch 0086) holds for the same SoC.

### 3.12 Hardcode inventory

Everything in this tree that encodes a 6T or one-unit fact (grep `fajita|2340|sda17|17c8a0000|
fajita2|0x9d4|146bf65c`):

| File:line | Value | Scope | OP6 action |
| --- | --- | --- | --- |
| `shim/console.h:6` | `FB_H 2340` | board | 2280 |
| `shim/console.h:4`, `shim/mmu.h:4` | `0x9d400000` | board (same on OP6) | keep after the FDT check |
| `shim/build.sh:9` | `fajita2.dtb` | unit | OP6 DTB from the `boot_b` dump |
| `shim/build.sh:38-50` | header v1 fields, `os_version 17.0.0`, `os_patch_level 2035-06` | ABL | keep |
| `shim/shim.c:382,417`, `shim/ufs.c:197` | "fajita milestone" banners | cosmetic | rename |
| `tools/fajita.env` | all FB/RAM/touch/key constants, `DTB_DEFAULT` | board/unit | `tools/enchilada.env` holds the measured OP6 values; `BOARD_ENV=tools/enchilada.env tools/build-fajita.sh` sources it, `FB_H` reaches `shim/build.sh` (`-DFB_H`, `console.h` now `#ifndef`) and `mkadt.py --fb-h`, `RAM_HIGH_SIZE` becomes `--dram-size` |
| `tools/mkadt.py:21-22` | `HIGH_MEM_SIZE 0x17c8a0000` | unit | measured size (`--dram-size`) |
| `tools/mkadt.py:35-37` | FB 0x9d400000, 2340 | board | 2280 |
| `tools/mkadt.py:322` | `oneplus,fajita` | cosmetic | add `oneplus,enchilada` |
| `tools/build-fajita.sh:15-18,50` | DTB default, cmdline | unit/board | `build-enchilada.sh` or variables |
| `tools/push-image-blocks.sh:19` | `/dev/block/sda17` | unit (true here) | resolve `by-name/userdata` anyway |
| `tools/qemu-sweet.py:27,186` | comments | — | none |
| `xnu/patches/0010:99,131,161-164` | `0x9d400000 + 2308*4320`, `EARLY_HEIGHT 2340` | board | 2248 / 2280 |
| `xnu/patches/0012:104,142` | base + `0x1400000` | board (same) | keep |
| `xnu/patches/0058:~21024,~21042` | `SurfaceHeight 148`, clamp 2399 | board / sweet leftover | 144 / `panel_h-1` |
| `xnu/patches/0061:14,107-109` | 2340 ×3 | board | panel size from `AppleCLCD` |
| `xnu/patches/0071:32` | 2399 | sweet leftover | `panel_h-1` |
| `xnu/patches/0090:78,208,216,245` | 2340 / 2339 | board | 2280 / 2279 |
| `xnu/patches/0091` | `keys_fajita` naming, PPID 0x0c4/0x0c5 | board (same) | keep |
| `xnu/patches/0093:14-25` | RSC defaults, boot-args | SoC | keep |
| `xnu/patches/0099:39`, `0135`, `0146:22` | cmd-db 0x85fe0000, zap region 0x8c415000 | DT carve-outs | verify in this unit's FDT |
| `xnu/patches/0110:25` | `GPU_SCRATCH_PA 0x0b000000` | early GPU experiment | check whether later patches still use it |
| `.github/workflows/xnu.yml:94` | message text | — | none |

## 4. What the OnePlus 6 attempt (`awa-xaga/ios-enchilada`) established

Its `README.md` ("has not booted yet") is stale; its `NOTES.md` shows the iOS 16 **lock screen on an
8 GB OnePlus 6** on 2026-10-22, via `fastboot boot`, reproduced in three clean boots. It never got
further: no touch (S3320 probe only, with the TLMM tile layout that froze the 6T), no keys, no GPU.
It is a fork of `ios-sweet`, so its patch numbers 0082–0089 do not correspond to this tree's and
must not be merged; take the facts and ideas:

- Observed on the OP6: header v1 + appended DTB table accepted; FDT in `x0` at 0x853FD000; splash
  0x9d400000/0x2400000; memory 0x80000000+0x100000000, 0x180000000+0xfcba0000 (its unit); UFS
  2.1 at 0x1d84000, LUN0 last LBA 0x1D06FFF; IMEM 0x146bf65c; APCS WDT bite at ~150 s; `/pram`
  only at 0x100000000; `sweetfb_noconsole=0` needed on that base; `sweetlog=0` to avoid
  flush stalls on that base; EDL HWID 0x0008b0e10051459b (the `op6t` firehose loader works).
- Ideas worth porting: panel size exported from `AppleCLCD` for HID (its 0087); the WDT pet thread
  (its 0082) if the reset shows up; `shim/board.h` as the per-board constants pattern; its
  `tools/gpt-list.py` (offline GPT parser).
- Not to use: `tools/edl-backup.sh` / `edl-read-log.sh` (EDL with firehose loaders; this port backs
  up from Android root or recovery), its touch patches as code.

## 5. Collecting facts from the phone

`tools/enchilada-facts.py` only reads: `getprop`, `/proc/cmdline`, `/proc/meminfo`, `/proc/iomem`,
the partition table (`by-name` → device → start/size), `/sys/devices/soc0`, I²C/SPMI/input/DRM/
backlight/power-supply sysfs, `dmesg`, the live FDT and `/proc/device-tree`, and the
`boot_a/b`, `dtbo_a/b`, `vbmeta_a/b` images (never persist, modem, fsg, fsc or the bootloaders).
Output goes to `facts/<date>/` (ignored by git): `raw/` holds the unredacted dumps (serial number,
MACs), `summary.txt` is redacted and decodes the FDT (memory, carve-outs, selected panel, touch
node, keys, splash), the boot header and its DTB identities, the dtbo table and vbmeta flags.

```sh
python3 tools/enchilada-facts.py --su          # Android with Magisk: allow "Shell" in Magisk first
python3 tools/enchilada-facts.py               # OrangeFox/TWRP (adb is root there)
python3 tools/enchilada-facts.py --fastboot    # bootloader: getvar all, oem device-info
python3 tools/enchilada-facts.py --selftest    # offline test of the parsers and the write guard
```

## 6. Bring-up plan

Principle: one new variable per boot, nothing flashed that is not needed, slot `b` (LineageOS)
never written, `userdata` written once.

| Step | Goal | Flashes | Success | Rollback |
| --- | --- | --- | --- | --- |
| 0 | Done: root facts, bootloader driver, `fastboot getvar all` (unlocked, both slots successful, retry 7/6). Partition backups were declined by the owner: rollback = slot `b` + MSM tool. Left: WSL + `tools/setup-wsl.sh --wsl-kernel` (§8), a recovery image for enchilada that `fastboot boot`s (the crDroid recovery is the candidate), copy of Android user data before step 2b | 0 | the shim builds in WSL | — |
| 1 | Diagnostic shim without payload: `FB_H=2280 SHIM_HDR=1 DTB=$(realpath dtb/boot_b_unpacked/enchilada2.dtb) shim/build.sh` → paints the console, prints the live memory nodes and the read-only UFS probe | 0 if `fastboot boot` works; else 1 (`boot_a` + `--set-active=a`) | text on the panel, memory nodes = §1, UFS `rc 0` | `fastboot --set-active=b` |
| 2a | Kernel from CI + `BOARD_ENV=tools/enchilada.env tools/build-fajita.sh` (ADT with `--fb-h=2280`, the measured DRAM size, conservative boot-args from §3.7), no root yet | 0–1 (`boot_a`) | early console, `SWEET UFS` finds `userdata`, stops at the root mount with a clear message; no reset at ~150 s | same |
| 2b | iOS root image (`tools/mkiosroot.sh` + `sweet-root-tweaks.py`, WSL) → `fastboot -S 512M flash userdata` | 1 (userdata, destructive) | HFS+ mounts, launchd starts, Apple logo, 10–15 min migration, lock screen with the console on | Android reinstall of data only; system stays in slot b |
| 3 | Input: HID geometry fix (§3.2), `sweetkeys=1` after `sweetkeysprobe=1`, `sweetts=1` with `sweettouchdelay`, raw range from the log | 1 per kernel (`boot_a`) | unlock swipe, home screen, buttons | same |
| 4 | `cpus=8`, `sweetfb_noconsole=1`, status-bar crop review, GPU ladder with the OP6's firmware (`adreno=…`), block-level root updates with `push-image-blocks.sh` | 1 per kernel | as on the 6T | same |

Every boot image is a new kernel or shim; the only partition written repeatedly is `boot_a`
(64 MiB). If `fastboot boot` works on this ABL, steps 1–3 need no `boot_a` writes at all.
After a few failed boots the OnePlus ABL may switch the active slot back to `b` on its own
(observed on the 6T): check `fastboot getvar current-slot` before blaming an image.

## 7. Rollback and recovery

- **Slots**: Android lives in `boot_b`/`system_b`; the test slot is `a`. `fastboot --set-active=b`
  (or the bootloader menu) returns to Android at any time. Keep `backup/boot_a.img` to restore
  the previous content of slot a.
- **Userdata**: after step 2b Android boots factory-reset. Before step 2b copy `/sdcard` and
  anything else wanted off the phone.
- **Recovery with adb root**: a TWRP/OrangeFox image for enchilada booted with `fastboot boot`
  (nothing flashed) is the path for log pulls (`tools/sweet-log-pull.sh`), block pushes and
  partition backups.
- **MSM Download Tool** (last resort, bricked or unbootable bootloader): the OnePlus 6 packages
  are `enchilada_22_J.50_*` (OOS 10.3.x) and `enchilada_22_*` 9.0.x with `MsmDownloadTool V4.0`;
  EDL: power off, hold Vol+ and Vol−, plug USB (device `05c6:9008`, Qualcomm HS-USB QDLoader
  9008 driver, USB 2.0 port); the tool rewrites all partitions, wipes data and **relocks the
  bootloader** (re-unlock afterwards: `fastboot oem unlock`, which wipes again). It restores a
  stock OxygenOS that LineageOS/OOS 11 firmware was built on top of, so firmware must be updated
  again before LineageOS. Whether it rewrites `persist`/`modemst*` is undocumented — the backups
  of §6 step 0 exist for that case.
- **Never written** by this port: `persist`, `modemst1`, `modemst2`, `fsg`, `fsc`, `modem_*`,
  `xbl*`, `abl*`, `tz*`, `hyp*`, `aop*`, `keymaster*`, `cmnlib*`, `devcfg*`, `dtbo*`, `vbmeta*`,
  `boot_b`, `system_*`, `vendor_*`.

## 8. Host environment

Windows 11 host, Git Bash + PowerShell, Python 3. Present: `git`, `python3`, Google
platform-tools (`adb`/`fastboot`) in `%USERPROFILE%\platform-tools` (not on `PATH`), `curl`.
Missing: `gh`, WSL (not installed), `aarch64-linux-gnu-gcc`, `mkbootimg`, `apfs-fuse`,
`hfsprogs`, `img2simg`, `dtc`, `lz4`, `cpio`, `7z`.

| Need | Install |
| --- | --- |
| GitHub CLI (kernel CI runs/downloads) | `winget install --id GitHub.cli` |
| adb/fastboot on `PATH` | add `%USERPROFILE%\platform-tools` to the user `PATH` (or use the full path) |
| fastboot in bootloader mode | Windows enumerates the phone only in adb mode ("Android ADB Interface"); in fastboot mode no driver bound and `fastboot devices` stayed empty: install the Google USB driver (Android Bootloader Interface) through Device Manager → Update driver while the phone sits in fastboot, then `fastboot devices` must list it |
| Linux for the shim and the root image | admin PowerShell: `wsl --install -d Ubuntu-24.04`, reboot |
| inside WSL: cross toolchain, HFS+, sparse, dtc, misc | `sudo apt install gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu hfsprogs android-sdk-libsparse-utils device-tree-compiler lz4 cpio p7zip-full python3` |
| apfs-fuse, mkbootimg, WSL kernel with `CONFIG_HFSPLUS_FS=y` | `tools/setup-wsl.sh --wsl-kernel` (then `.wslconfig` `kernel=`, `wsl --shutdown`) |
| Qualcomm 9008 driver, MSM tool | only for §7, not for the bring-up |

`fastboot` is run from Windows (USB passthrough into WSL is not needed); WSL only builds files.
The repo must stay LF (`core.autocrlf=false`), otherwise the shell scripts break inside WSL.

## 9. Open questions (answered by steps 0–2)

1. Does this ABL accept `fastboot boot`? (`unknown command` → flash `boot_a` + `--set-active=a`.)
2. Does the APCS watchdog reset the OP6 at ~150 s with the fajita kernel?
3. Does `/pram` at the top of the DRAM range work here as on the 6T, or only 0x100000000?
4. Raw touch range of this unit's sensor; key PPIDs (first kernel boots).
5. A recovery for enchilada that boots with `fastboot boot` and gives adb root (TWRP by Nebrassy;
   the crDroid recovery image at hand is the first candidate to test).

Answered on 2026-10-28 from the phone: the memory map (identical to the 6T unit), the panel
(`sofef00_m_cmd`, 1080×2280, command mode, no DSC), the lock state (`unlocked: yes`, critical
locked), the slot state (both successful, retry counters 7/6 — a slot that never reports success
loses one per boot and ABL switches at zero; `fastboot --set-active=a` re-arms it), the DTB table
and the `dtbo` selection, the GPU firmware location, the partition layout and sizes.
