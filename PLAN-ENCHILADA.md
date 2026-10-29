# iOS on the OnePlus 6: roadmap after the first boot

## 0. Purpose and principles

This is the work plan for the OnePlus 6 (`enchilada`) port after iOS 16.7.16 reached the lock
screen on 2026-10-29. It orders the remaining work, says what each step must show on the phone
before the next one starts, and records the decisions taken so far. Hardware facts and the boot
path are in `PORTING-ENCHILADA.md`; the 6T journal is `NOTES-FAJITA.md`, where later entries
supersede earlier ones.

- **Upstream first.** The kernel series, shim and tools are the 6T tree (`fajita/main`) plus a
  thin board layer. SoC-level fixes are written against `fajita/main` and offered there. This tree
  merges `fajita/main` often and never rebases published history. `awa-xaga/ios-enchilada` (the
  parallel OnePlus 6 attempt) and `dipa-studio/ios-sweet` are read for ideas and never merged.
- **Patch numbering** follows §3.2 everywhere: generic fixes waiting for upstream in 08xx,
  board-only patches in 09xx after the shared series. The local 0173 is board-neutral (it reads the
  boot video), so it is offered to fajita and carried as 08xx until fajita numbers it; only
  board-only patches take 09xx.
- **One variable per boot.** Each boot names the known-good image or argument set it extends and
  adds one change. Every feature sits behind a boot-arg that defaults to off.
- **Flash discipline.** Kernels and shims iterate through `fastboot boot`, which writes no
  partition; each boot still changes phone state and is agreed at its step. The only partition
  writes in this plan are confirmed `userdata` flashes of the iOS root, each shown first with the
  exact command and what it overwrites (about 6 min plus 10-15 min of migration; the previous
  `.simg` is kept).
- **Never written:** `persist`, `modemst1`, `modemst2`, `fsg`, `fsc`, `modem_*`, the bootloader
  partitions (`xbl*`, `abl*`, `tz*`, `hyp*`, `aop*`, `keymaster*`, `cmnlib*`, `devcfg*`), `dtbo*`,
  `vbmeta*`, `boot_b`, `system_*`, `vendor_*` (PORTING-ENCHILADA.md §7). EFS partitions are read
  only with the owner's explicit approval (§10), and their bytes never leave the phone.
- **Android in slot b stays restorable but is not booted while `userdata` holds the iOS root.** It
  would boot factory-reset and offer "Format data"; accepting destroys the root (a 12 GB re-flash)
  and loses Magisk `su`. Refuse every format, wipe, factory-reset or fsck prompt, also from a
  recovery. Facts that once needed Android `su` come from a fastboot-booted recovery or public
  firmware packages.
- **Exit procedure for every boot.** Hold Power about 15 s, then Power+Vol+ until fastboot. If an
  Android boot animation appears, power off at once. 900E: PORTING-ENCHILADA.md §3.9. If fastboot
  shows `????????????` after a large flash, re-plug the cable.
- **Privacy.** Firmware, DTB dumps, root images, logs, panel photos, EFS data, MAC/BD addresses,
  SSIDs and serials stay out of git, public CI and releases. The ABL command line carries
  `androidboot.serialno`; scrub it before quoting a log.
- **Observed vs inferred.** Each section marks what was verified, and where. Routes are chosen on
  numbers measured on this phone.

**Estimates** are working days for one engineer, including CI builds (about 7-15 min each) and
one retry where stated, excluding waits for consent, purchases or a Mac. Every step has an
acceptance test (what must appear on the panel, in the pulled log or on video); large steps also
have a kill criterion that sends the work to a named fallback.

## 1. Where the port stands (2026-10-29)

**Works on this unit** (PORTING-ENCHILADA.md §9):

- This ABL accepts `fastboot boot`; no `boot_a` write is needed.
- Kernel: the 6T CI build of the merged series through 0171 (tree at 25a58ab, which predates 0172;
  the CI run's headSha was not recorded, so record it with every image from now on, §6 step 3), ADT
  `fb-h` 2280, the phone's own SoC v2.1 DTB plus `dtbo` index 5, `ARENA_MIB=1`, GPU ladder off.
  Root: the 20H392 HFS+ image flashed once into `userdata` (`fastboot -S 512M flash userdata`,
  12.1 GB sparse).
- `cpus=1 sweetsmp=0 sweetfb_noconsole=1 sweetecon=1 sweettouch=0 sweetts=0 sweetkeys=0`: Apple
  logo, about 15 min of first-boot migration, lock screen.
- `cpus=8 sweetsmp=1 sweetkeys=1 sweettouch=1 sweetts=1 sweettouchdelay=20`: lock screen within
  minutes; touch, power and volume keys work; Settings is usable.
- No APCS watchdog reset (247 s without a root; no reset seen in the GUI boots); `/pram` at the top
  of DRAM works as on the 6T.
- 0173 (panel geometry from the boot video) is pushed and its images are built (not in git); §5
  step 1 records their result.

**Does not work:** touch lands up to 30 px off and bottom-edge gestures miss (§5); rendering is
CPU-only and nothing GPU-specific has run here (§3); the clock starts at 1969 (§4); 0079 turns the
panel off on auto-lock and only the power key wakes it, `sweetfb_console=1` means console only,
and the off fade is stepped at `sweetfb_hz=10` (§5 step 8); the only log is the panel console and
photos (no enchilada recovery yet; the 0077 USB live log does not work on SDM845) (§6); PosterBoard
crashes and some daemons crash-loop (§7); the battery reads a static 100 % (§12); no Wi-Fi,
Bluetooth, modem, audio, camera or sensors; AMFI, sandbox and code signing are permissive stand-ins
(§11).

**Measured facts the plan depends on** (`facts/20261028-213313/summary.txt`, PORTING-ENCHILADA.md §1):

| Item | Value |
| --- | --- |
| Board | A6003, `qcom,board-id <8 0 17819 22>`, SDM845 v2.1, 8 GB |
| Memory | both banks and every carve-out byte-identical to the 6T unit; `wlan_fw_region` 0x8df00000 (1 MiB), `modem_region` 0x8e000000 (120 MiB), `mba_region` 0x96600000 (2 MiB), `removed_region` 0x85fc0000-0x8ab00000, `cont_splash_region` 0x9d400000; no rmtfs region |
| Panel | samsung sofef00, 1080×2280, command mode, 68×145 mm |
| Touch | Synaptics S3320 on SE12 0xa90000 (6T wiring); DT `display-coords`/`panel-coords` 1080×2160 |
| Keys | PM8998 PON, GPIO5, GPIO6; alert slider on tlmm 126/52/24 |
| Storage | `userdata` = sda17 (110 GiB); EFS on sdf2-sdf5 |
| fastboot | `max-download-size` 768 MiB, `boot_a` 64 MiB, retry counters 7/6, unlocked (`verifiedbootstate=orange`) |
| Firmware | a630 GMU, SQE and zap in `/vendor/firmware`; `/vendor/firmware_mnt/image` listed empty under Android |
| Battery | bq27541 at 0x55 on `i2c@a88000` (SE10), design 3240 mAh |

## 2. Priority order and dependencies

Hardware acceleration is priority one. The clock is the cheap second. Input geometry is third;
it is small and already in flight (0173). Infrastructure follows; it speeds up everything after
it, and its first steps run inside the GPU section's first week (I1-I3). The radios come after
the UI is complete.

| # | Workstream | Value | Days | Prerequisites | When |
| --- | --- | --- | --- | --- | --- |
| 1 | §3 GPU Stage 1 (GLES compositor) | usable UI speed | ~32 critical path, 40-45 with retries | I1-I3, K0-K6, S-G | now |
| 1b | §3 GPU Stage 2 (Metal device) | PosterBoard, Metal apps | ~32, 40 with one retry | Stage 1 kernel work, loader | after G4 |
| 2 | §4 Clock | correct date; TLS and activation possible | 7 | none for steps 1-3 | weeks 1-2 |
| 3 | §5 Display, touch, keys | taps under the finger, home gesture | 5-6 | green CI for 0173 | weeks 1-2 |
| 4 | §6 Infrastructure | log pulls, CI fetch, <10 min loop | ~4.4 | owner: `gh`, push, toolchain consent | weeks 1-3, with I1/I3 |
| 5 | §7 UI completeness | no crash loops, decoded logs, wallpaper | ~16 | recovery, stay-on, loader; Stage 2 | weeks 4-16, interleaved |
| 6 | §11 Security stand-ins | documented model; `@rpath` answer | 5.5-6.5 (+ optional) | step 0 offline now | step 0 week 1, rest by M4 |
| 7 | §8 Bluetooth | first radio, modem-free | ~44 (step 8 budgeted at 15, open-ended) | log path, RPMh proof | after M5 |
| 8 | §10 Modem (MPSS to QRTR) | prerequisite for Wi-Fi | ~30 | clock, D1 decision | after Bluetooth step 7 |
| 9 | §9 Wi-Fi | network | 25-34 on top of the modem | modem S7, RTC, USB log or ring reader | after the modem |
| 10 | §12 Battery, charger, slider, audio, haptics | real battery %, ring/silent | 7.5-10.5 battery+charger+slider; 4-6 audio contract; 7-10 haptics; 20-40 speaker | keys boot, SPMI whitelist, loader | battery by M4; speaker after Wi-Fi |

```
                                     fajita/main merges (continuous)
                                                    |
     +----------------------------------------------+-------------------------------+
     |                                              |                               |
 clock 1-3                                   I1 recovery log               security 0 -> S-G
                                                    |                               |
                                        I2 stay-on + CPU baseline -> display 1-4    |
                                                    |                               |
                                     I3 loader (one userdata flash) <---------------+
                                                    |  \
                                                    |   UI 1-3
                                                    v
 K0 ladder -> K1 size -> K2 hygiene -> K3 arena -> G2 triangle -> K4 SURFACE_BO -> G3 EAGL test
                                       |            ^                               |
                              K5 (if K1/K3 need it) |                          K6 flip wait
                                                G1 OSMesa                           |
                                                                       G4 backboardd -> G5
                                                                           |
                                                Stage 2 S-B, P1-P5 (Metal) -> wallpaper
                                                                           |
 RTC (clock 1-3) ---------------------------------------------------------> radios:
                                                                     Bluetooth 1-7 (UART, no modem)
                                                                           |
                                                                     modem S-1..S9
                                                                           |
                                                                     Wi-Fi WLFW .. en0
```

## 3. Hardware acceleration (GPU-composited UI, then Metal, on Adreno 630)

### 3.1 Starting point

Verified:
- iOS 16.7.16 reaches the lock screen on the OnePlus 6 with the CPU renderer and the GPU ladder off. Nothing GPU-specific has run on this unit yet.
- The kernel GPU stack (0099-0172) is the 6T's. The last proven state on the 6T was a userspace IOKit submission (console101) and Mesa reaching submitqueue creation (0168).
- 0169-0171 are in the kernel that booted here, with `ARENA_MIB=1`. No kernel with an arena above 1 MiB has completed a boot (0170 and 0171 panicked in `kmem_alloc` on the 6T, NOTES-FAJITA.md 2026-10-28); 0172 itself has no recorded boot on either phone.
- Defects found by reading the code (each to be confirmed on the phone by the K2-K4 self-tests before it is fixed):
  - `mapGem()` and the `SET_IOVA` loop step 16 KiB per 4 KiB GPU PTE;
  - SUBMIT refuses every flag except `NO_IMPLICIT`;
  - `FAULTS`/`SUSPENDS` are not answered;
  - arena pages are never freed;
  - two VA allocators overlap;
  - `SURFACE_BO` (0x71) has never run.
- hackios draws the iOS 16.5 UI on the GPU without Metal. It uses CoreAnimation's GLES render server in backboardd, on Mesa 25.0.7 OSMesa+freedreno, over an msm-numbered IOKit client of the same shape as `SweetAdreno630`. Settings scrolls at 56-58 fps on the GPU against 28-35 fps in software. Bergamota repeated this on an Adreno 630 (iOS 18.7.8).
- The journal's statement that GLES cannot accelerate CoreAnimation on iOS 16 is therefore withdrawn.

This section has two stages:
- **Stage 1** puts the compositor on the GPU through the GLES path.
- **Stage 2** builds the Metal device for apps and PosterBoard, reusing Stage 1's Mesa, stand-in and kernel work.

### 3.2 Rules for this workstream

- Change one variable per boot. Each kernel change is its own CI build and its own `fastboot boot`.
- Every GPU piece is off by default and falls back to the CPU renderer. A boot without `sweetgl=1` behaves exactly like today's known-good image.
- Each boot names the known-good boot-args it extends. That is the lock-screen set or the 8-core input set (§1). The GPU arguments are the only addition.
- The only phone write is the single confirmed userdata flash in I3. Everything else is `fastboot boot`.
- Patch numbering:
  - Generic fixes are written against `fajita/main` and offered upstream. Until fajita assigns them numbers, they are carried here in a pending-upstream range (08xx).
  - Board-only patches move to their own range (09xx), applied after the shared series. The local `0173-enchilada-panel-geometry` is board-neutral (it reads the boot video), so it is offered to fajita and carried as 08xx until fajita numbers it; only board-only patches take 09xx.
- Routes are chosen on numbers measured on this phone, never on a neighbour's numbers.

### 3.3 Infrastructure (before any GPU userland)

| # | Milestone | Days | Acceptance | Kill / fallback |
|---|---|---|---|---|
| I1 | Log channel: `fastboot boot` a candidate enchilada recovery (agreed at that step) and read the 0047 ring with `tools/sweet-log-pull.sh`. The ring is the last 1025 blocks of `userdata`, beyond the 16 GiB root image (PORTING-ENCHILADA.md §3.8). Check that `sweetlog=1` is in the actual cmdline. Refuse every format, wipe or fsck prompt. `push-image-blocks.sh` stays unused. | 1 | Pulled log with a valid `SWEETLOG` header and the previous boot's kernel lines | No recovery with adb root within a day: keep using panel photos and plan USB networking separately. Never block on it. |
| I2 | Stay-on switch, plus a CPU baseline. A fajita-generic `sweetfb_stayon` modelled on topaz 0085 (awa-xaga 0084 as a read-only reference) keeps 0079 from blanking the panel on auto-lock. A once-per-second present counter in the framebuffer driver, if none exists, measures both renderers with the same instrument. | 1.5 | Panel stays on for 10 min. Settings-scroll and lock-screen fps for the CPU renderer recorded on this unit. | Patch fails: set auto-lock to "Never" in the I3 root tweaks |
| I3 | Payload loader, delivered in **one** confirmed userdata flash. Contents: a read-only `/dev/sweetpayload` over a FILES blob; `sweet-install`, started from the DumpPanic hand-over, idempotent, keeping `.orig` copies, writing only `/usr/local` and named bundle directories; a backboardd gate library. The gate is installed on the root and never removed by the loader, and it does nothing unless `sweetgl=1` is set and the GL files are present. The loader prints its build string before anything else, and a `sweetinstall=restore` boot-arg puts every `.orig` back. The image is frozen only after S-G (3.5) has answered the insertion question. Keep the previous `.simg`. | 3 | Two consecutive boots with no flash in between print two different payload build strings. The gate-installed boot without `sweetgl` matches today: lock screen, same process count. | The loader corrupts the root twice: go back to one flash per round and cut iteration to weekly |

### 3.4 Kernel prerequisites

Each item below is proven by an in-kernel self-test behind a boot-arg where possible.

| # | Milestone | Days | Acceptance |
|---|---|---|---|
| K0 | Ladder regression. Use this unit's own `/vendor/firmware` a630 files, `ARENA_MIB=1`, and add only `adreno=9 zap=1 gpuhold=1`. | 1 | The console shows, in order: `zap authenticated and started (PAS 13`, `CP NOP TEST PASSED`, `cp ib test: PASSED`, `bo test: PASSED`, `abi test: PASSED`, `GPU KEPT UP`, `SWEET GPU: SweetAdreno630 published`, then the lock screen. **Kill on the first** refused zap or hang: compare facts, do not patch blind. |
| K1 | `fastboot boot` size probe. Kernel unchanged, `ARENA_MIB=1`, image padded to about 90 MB with an inert blob. | 0.5 | The result is recorded either way. The bound that matters is ABL's RAM placement, not the 64 MiB `boot_a` (that limit applies only to a flash). |
| K2 | Hygiene, four patches booted one at a time. (a) Stride fix in `mapGem()` and `SET_IOVA`. (b) `FAULTS`/`SUSPENDS` answer 0, and `TIMESTAMP` comes from the always-on counter. (c) SUBMIT accepts and ignores the `MSM_PIPE_3D0` (0x10) pipe bits; read `sweet_drm.c` first to see whether it already masks them. (d) CB1 `FSR`/`FAR` logged on a fence timeout. | 4 | (a) `sweet-iokit-test` with the command buffer at +0x1000 and writes to +0x1010, +0x2020 and +0x3ff0 reads all three back and logs `wait fence N -> 0`. The unfixed kernel times out (negative control). (b) GET_PARAM 0x09/0x0a return success with 0, and two `TIMESTAMP` reads 100 ms apart differ by about 1.92e6. (c) A submit with flags 0x10 returns a fence. (d) A deliberate bad iova logs `fault at 0x…`. |
| K3 | 0172 proof and arena reuse. In its own boot, raise `ARENA_MIB` to the largest size K1 allowed, at least 64. A 4 MiB alias-less BO is written by the CP and copied with `CP_MEM_TO_MEM` into an aliased buffer. Audit that the dump and reloc paths never dereference `kva == NULL`. Then add a free-list with fence-deferred release and one VA allocator for the chardev and IOKit. | 4 | `1024 KiB with a kernel alias`, and the copied dword matches. 1000 rounds of alloc/free keep the arena high-water mark flat. Chardev and IOKit iovas are disjoint. **Kill** after two panics with different fixes: add VM diagnostics behind a boot-arg (`gPhysBase`/`gPhysSize`, the managed pfn range, the largest `kernel_map` hole) and use K5's reserve-only blob. |
| K4 | `SURFACE_BO` on hardware, after I3. A payload probe, delivered by the I3 loader, imports one CoreAnimation-created IOSurface and the framebuffer surface (`cont_splash` 0x9d400000), lets the GPU write them, and reads back through `IOSurfaceGetBaseAddress`. Print each physical address against the DRAM start and `gPhysBase`. | 1.5 | GPU-written pattern visible. All addresses at or above 0x80000000. |
| K5 | Memory beyond the boot image, only if K1 refused large images, or K3's kill fired: a reserve-only blob (size without bytes, zero-filled by the shim) and an L3 pool of more than 64 tables (64 tables cover 128 MiB). | 3 | `buffer arena 262144 KiB`, boot image about 18 MB, a 64 MiB BO reads back zero |
| K6 | Flip waits for the GPU, after G3. `finish_update`/present waits for the frame's last fence before the sweetfb refresh pushes to the command-mode panel, and the display advertises a waits-for-GPU property so the EAGL layer can drop `glFinish`. | 2 | No torn or stale frames over 1000 presents, checked with a frame-number overlay against the present counter, measured with the G3 test tool extended to present its IOSurface through IOMFB every frame |

### 3.5 Stage 1: GPU-composited UI through the GLES render server

**Status, later on 2026-10-29 (host only, nothing booted yet).** S-G and G1 are done, and the
insertion question of S-G (1) is settled without relying on `DYLD_INSERT_LIBRARIES`:

- `tools/build-osmesa-ios.sh` builds Mesa 25.0.7 OSMesa (freedreno + softpipe) on Linux with
  Bergamota's `bergamota-mesa-25.0.7.patch` instead of hackios' Mesa patches: it already targets
  `SweetAdreno630` through the libdrm stand-in and brings the GLES profile and the IOSurface
  import (`OSMesaSweetWrapTexture`). 1296 `gl*` exports, ad-hoc signed.
- `tools/gles-ca/build.sh` builds `libsweetca.gl.dylib` (hackios `eagl.c` with its generated
  20F66 table, plus `sweetca_gl.c`, the OSMesa glue for Bergamota's profile value 0x36),
  `libsweetca.dylib` (`sweetca_inject.c`: the render-server hooks at the 20H392 addresses,
  boot-arg `gl=0` turns everything off) and a copy of backboardd with a weak
  `LC_LOAD_WEAK_DYLIB` of the latter (`tools/macho-add-dylib.py`, page hashes recomputed in place;
  if the library is missing backboardd runs as before). All five files pass a page-by-page hash
  check; every dependency is an absolute `/usr/local/lib` path.
- Next is installing them into the root image (one confirmed `userdata` flash) and the first boot
  with the GPU ladder on; G2/G3 below can be skipped straight to G4 when that boot shows
  `sweetca: the window server has an OpenGL ES renderer`, with `gl=0` as the way back.

**S-G, host spike: 1 day. Off the critical path, no phone.**
- Done on the host: `docs/gles-route-20H392.md` (tools `dsc-vtables.py`, `dsc-gles-slots.py`) shows the render-server classes exist in 20H392 and gives the nine hooked slots and their targets (`begin_update`/`finish_update` moved to 0x178/0x180 by the new `IOMFBDisplay::work_interval`). All 457 macro-context offsets equal 20F66, so hackios' table is used unchanged.
- Remaining:
  - (1) whether dyld honours `DYLD_INSERT_LIBRARIES` for backboardd under our AMFI stand-in (shared with §11 step 0(b)); fallback an `LC_LOAD_DYLIB` copy under `/usr/local` with the launchd plist pointed at it in the I3 flash;
  - (2) whether CA picks `AppleCLCDDisplay` for our IOMFB (0046), answered by the first G4 boot.
- *Kill:* insertion cannot be made to work; see 3.8 (a).

**G1, OSMesa build: 3 days, host, in parallel with K0-K3.**
- Mesa is **pinned to 25.0.7**. OSMesa is believed to be removed from later releases (inferred), so the build must not drift to a newer tree.
- Use hackios `tools/mk-mesa.sh` (Mesa 25.0.7, `-Dosmesa=true -Dgallium-drivers=softpipe,freedreno -Dfreedreno-kmds=msm -Dgles2=enabled -Dshared-glapi=enabled -Dllvm=disabled`, …) and its patches `freedreno-darwin` (with our `sweet_drm.c` in place of hakios-drm, and IOSurface import mapped to `SURFACE_BO`), `osmesa-es-profile` and `ir3-round-default`.
- hackios applies every `tools/mesa/*.patch`; `air-frontend.patch` and `air-ir3.patch` are left out of Stage 1 (Metal only), and the build is checked without them.
- Use absolute install names everywhere, because AMFI refuses `@rpath`.
- *Accept:* `libOSMesa.8.dylib` is arm64 and links only libSystem, libz, libc++ and `libdrm.2.dylib`.

**G2, first verified frame: 4 days, at most 6 boots. Depends on K2, K3 and I3.**
- `sweet-tri` draws a red triangle on blue at 256×256 on freedreno and on softpipe. It reaches the phone through the I3 loader.
- *Accept:*
  - the line `sweet-tri: gpu red=N blue=M crc=X` matches the softpipe line, with exact pixel counts;
  - `WAIT_FENCE -> 0`;
  - no fault line;
  - a flat arena high-water mark over 100 frames.
- *Kill:* after 5 days or 6 boots, the S-B Turnip smoke test (3.6) takes the slot to separate an ABI fault from a Gallium fault.

**G3, EAGL in a test process: 3 days. Depends on G2 and K4.**
- Port hackios `eagl.c` with hackios' 20F66 macro-context table (unchanged in 20H392).
- A standalone tool creates an `EAGLContext`, renders into an IOSurface through `glEGLImageTargetTexture2DOES(IOSurfaceID)` and reads it back.
- This proves the EAGL layer before backboardd is touched.
- *Accept:* the expected pattern in the surface, and `glGetString(GL_RENDERER)` names the Adreno 630.

**G4, backboardd on the GPU: 12 days. Depends on G3, I2, I3 and K6.**
- Port hackios `inject.c` with the 20H392 addresses from `docs/gles-route-20H392.md`. It refuses on any byte mismatch.
- The gate loads the GPU path only with `sweetgl=1`, the GPU ready and no off-flag present.
- Dead-man: no frame within 30 s of the first, 3 failed submits, or GPU lost → write the off-flag and `_exit(0)`, so launchd relaunches backboardd on the CPU renderer.
- Set the arena explicitly (the K3 size) and log its high-water mark once per second, so an out-of-memory stall can be told apart from a hook bug.
- *Accept:*
  - the lock screen and the unlock are drawn while `sweetgl: frame N via GPU` counts and the fences move;
  - Settings scroll is at least 1.3× the I2 CPU baseline;
  - backboardd uses under 90 % of one core;
  - a forced failure recovers to the CPU path in one relaunch;
  - a `sweetgl=0` boot matches today.
- *Kill:* three boots with an unexplained crash loop or wrong frames, or fps below the CPU baseline after K6. Then see 3.8 (c).

**G5, robustness and the daily image: 5 days.**
- Minimal CP reset path, asynchronous submit if the synchronous drain caps the frame rate, and a cache-maintenance check on write-combined buffers.
- *Accept:* 10 minutes of UI use with no GPU-lost event. `sweetgl=1` enters the daily image only after one week of use without a dead-man trip.

Estimate: about 32 working days on the critical path to the first GPU-composited lock screen (K0 → K2 → K3 → G2 → K4 → G3 → K6 → G4, with I3 in place before G2), and 40-45 days with retries. S-G and G1 run in parallel.

### 3.6 Stage 2: Metal device for apps and PosterBoard

backboardd stays on the Stage 1 GLES path. The Metal device is refused in backboardd and offered to other processes, as on hackios, where apps currently get nil. The Stage 2 milestones are P1-P5, distinct from the roadmap milestones M1-M6 in §13.

| # | Milestone | Days | Acceptance / kill |
|---|---|---|---|
| S-B | Host spike, a 2-day box. Turnip from Mesa 26.2.5 with Chlorophyll's `turnip-ios.patch`. `tu_smoke` linked directly to the ICD. No Rust until the owner agrees. | 2 | `libvulkan_freedreno.dylib` exports `vk_icdGetInstanceProcAddr`. No link: route B is parked until P2. |
| P1 | ABI for several clients: per-connection BO tables, absolute `CLOCK_MONOTONIC` deadlines as ABI version 2 (changed in lock-step with the stand-in), `PC_CCU_INVALIDATE_DEPTH/COLOR` with numbers taken from the a6xx definitions, and a boot-arg for the plugin name on the 0167 service. A macos-14 CI job builds `bg_kernels`/`bg_render`/`bg_quad` `.metallib` with `-mios-version-min=16.0`. | 5 | `wait fence N (X ns)` within 10 % of the request for three clients: the stand-in, the hakios-metal probe and the repository tester. Two processes hold BOs at once. Self-tests still pass. CCU events in their own boot. |
| P2 | Decision gate, one payload boot each: `mtl_gap`/`mtl_introspect`, `bgmtl-adddev` with `bgmtl_probe` (route A), and the `tu_smoke` 200-draw bench (route B). | 3 | Gap list, 12/12, the readback (8192 red + 57344 blue of 65536 pixels) and a µs/draw figure. The decision is written into PORTING-ENCHILADA.md §10 with this phone's numbers. |
| P3 | Probes on the chosen route: `bgmtl_render_probe`, the hakios-metal probe, `bgmtl_layer_probe` (through `SURFACE_BO`) and `bgmtl_ca_probe` on the 16.7.16 QuartzCore library. | 8 | 18/18, `probe: ok`, the triangle found in the IOSurface, the ca_probe count recorded. **Kill:** below 18/18 after 8 days, or more than 30 % of fragment functions failing: switch to route B. |
| P4 | Plugin roll-out, one process per boot. Gates refuse in `+allocWithZone:`, never in `init`. libbgair and libdrm sit inside the bundle with absolute install names. Allow/deny files come through the loader. Order: test process → PosterBoard → SpringBoard → apps. | 6 | Per stage: `<process>: device made`, no launchd crash loop, the PosterBoard wallpaper no longer crashes. With the switch set, the boot runs as today. |
| P5 | Memory at scale: a GPU pool withheld from XNU-managed RAM in the ADT memory description above 4 GiB, checked against this unit's carve-outs, in its own boot with the previous image kept for rollback. Check that `/var/local` survives reboots (shader cache), and record the cold compile time. | 8 | `GPU pool 262144 KiB at 0x…`. 10 minutes with PosterBoard, Settings and one Metal app and no GPU-lost event. |

Estimate for Stage 2: about 32 working days, 40 with one retry on P3 and P5.

### 3.7 First week

1. Run I1. Build the K0 image. Start S-G (insertion question).
2. K0 boot, then the K1 padded boot. Write K2a and K2b with their self-tests and send them to CI.
3. Boot K2a. Write K2c and K2d. Write the I2 stay-on patch. Start the loader. Start G1.
4. Boot K2b, then the I2 boot with the CPU baseline. S-G verdict on insertion.
5. Freeze the I3 image according to the S-G answer and ask for the flash confirmation. Weekly review against every kill criterion.

### 3.8 Fallbacks

The chain is: GLES render server (G) → Metal device as compositor (route A, Gallium bgmtl) → Turnip (route B; B' = Chlorophyll's MIT `chl` runtime; metal2vulkan last) → CPU renderer. The CPU renderer is never removed, and every layer can be reached by boot-arg alone.

- (a) If S-G fires (insertion cannot be made to work), the route A plugin with Chlorophyll's compositor profile and dead-man becomes the compositor route. Stage 2 is then pulled forward with backboardd added last.
- (b) If G2 fails, S-B decides whether the fault is in the kernel ABI (fix it there) or in Gallium (Stage 1 is parked).
- (c) If G4 does not beat the CPU baseline, the daily image keeps the CPU renderer and Stage 2 goes ahead for apps only.

### 3.9 Decision record

The GLES route comes first for four reasons:
- It is the only route with a measured GPU-composited UI on iOS 16: 56-58 fps against 28-35 fps in software, on 16.5.
- It reuses what already works here: the msm-shaped `SweetAdreno630` ABI, the stand-in and the Mesa 25.0.7 cross-build.
- It keeps the GPU in one process, so the kernel needs no multi-client tables and memory demand stays small.
- Its unknowns (insertion; the 20H392 offsets are already in `docs/gles-route-20H392.md`) are answered on the host before any phone time is spent.

The Metal routes measured about 45 fps home swipe with backboardd at 89 % of a core (Gallium bgmtl, Bergamota, iOS 18.7.8, A630) and 20-26 fps (Turnip + metal2vulkan, ios-flame, A640, 16.7.16) (PORTING-ENCHILADA.md §10.1). hackios measured its software renderer at 28-35 fps on its own phone; this unit's CPU baseline is not measured yet (I2), so whether either Metal route beats it here is open.

Switch conditions:
- (a) S-G kill;
- (b) G2 kill;
- (c) G4 below 1.3× the I2 baseline, or backboardd above 90 % of a core after K6.

Within Stage 2, route A is kept unless one of these holds:
- P2 measures route A above 50 µs per draw while `tu_smoke` is under 10 µs;
- P3's kill fires.

If route B is chosen, B' is preferred over metal2vulkan until the licence question below is settled.

### 3.10 Borrowed code and licences

- MIT:
  - hackios userland (`inject.c`, `eagl.c`, `mkeagl.py`, Mesa patches);
  - Chlorophyll (bgmtl, plugin gates, probes, `turnip-ios.patch`; keep `NOTICE.md`);
  - hakios-metal;
  - Mesa;
  - ios-flame and the UniXNU front ends.
- APSL-2.0: hackios kernel code. This matters if its flip-wait code is borrowed for K6.
- GPL-2.0+/LGPL-3.0+: metal2vulkan. It is fetched by script, never committed, and linked as its own dylib.
- Licence unverified: Bergamota `gpu/freedreno-sweet/sweet_drm.c` (also carried by the Mi MIX 2S tree), Bergamota's `gpu-eagl`/`ca_server_hook.m`, the Mi MIX 2S tree, and Bergamota's user client (our 0158). Verify each licence file before anything derived is published.
- Linux msm/a6xx: facts only, no code taken.

### 3.11 Board-specific inputs and open unknowns

Board inputs:
- This unit's a630 firmware; the zap is OEM-signed, and only K0 shows whether TrustZone accepts it.
- ABL's `fastboot boot` size limit (K1).
- An enchilada recovery image (I1).
- The 0079 panel-off quirk (I2).
- The command-mode sofef00 refresh path (K6).
- The 1080×2280 geometry: one BGRA surface is 9.8 MB. Scan-out and layer surfaces go through `SURFACE_BO`, not the arena.

Everything else is SoC-level and is merged from `fajita/main`.

Unknowns:
- Whether CA instantiates `AppleCLCDDisplay` for our IOMFB (the classes and slots exist in 20H392).
- Whether dyld honours insertion under this AMFI.
- Whether 0172 boots.
- Whether `SURFACE_BO` works on CoreAnimation's surfaces.
- Arena demand under real CoreAnimation churn.
- Why the VM hands out pages below `gPhysBase`.
- How completely the 16.7.16 AIR corpus translates (Stage 2).

## 4. Time of day (the 1969 clock)

**Goal.** Every boot, including the first after a `userdata` flash, shows today's date on the
first lock-screen frame and the time within a minute. Time = the PM8998 RTC counter, read once
through the read-only SPMI observer, plus an epoch offset. The RTC is never written. Later steps
make a time set in Settings survive a reboot and remove the 30 s `IORTC` wait.

**Where it stands (verified).** 0001-0173 have no RTC reader (no `TimeOfDay` or `IORTC` in the
series; 1969-12-31 in NOTES-FAJITA.md:30, :593). `sweet_spmi.c` (0062) whitelists peripherals
0x10-0x13 and 0x48 on SID 0, poisons a lane that times out, and has an unlocked
`sweet_spmi_init()` called only by `SweetBattery`; `sp_find_apid` prefers EE 0 owners but accepts
any. RTC: `ctrl` 0x6046 bit 7 = enabled, counter 0x6048..0x604b little-endian, read twice for the
carry (`rtc-pm8xxx.c`, PORTING-ENCHILADA.md §10.6). `/private/var` is on the read-write root, and
0029 hooks `bsd_init` after the root mount. `sweetfb_noconsole=1` (default) can hide `bsd_init`
lines. Not checked against xnu-8796 source: the 30 s `IORTC` wait before `vfs_mountroot`, and
`settimeofday` needing `com.apple.private.settime`.

**Steps.**

0. **Observation, no code (0.5 day).** After the touch/keys boot, change the time in Settings. If
   the lock screen follows, `settimeofday` works under the built-in entitlement provider
   (0025/0035, XML only); if not, steps 4-5 wait for `timed`'s entitlement path.
1. **RTC read and calendar, board-agnostic and offered to fajita (2 days with one CI build).**
   Whitelist 0x60 on SID 0; make `sweet_spmi_init()` idempotent under a static lock (or call it
   only from the platform expert before `SweetBattery`). `SweetPlatformExpert::start()` behind
   `sweetrtc=1`: require `ctrl` bit 7, read 0x6048-0x604b, re-read the LSB up to 3 times, cache
   `(rtc, mach_absolute_time)`, log `SWEET RTC: PM8998 <N> s ctrl 0x.. off .. floor .. src ..`.
   Getters (GMT and UTC) return `max(rtc + elapsed + offset, floor)` and never touch SPMI (it
   takes an IOLock and calls `delay()`); the setter only updates the in-memory offset. Acceptance,
   five boots: (1) `sweetrtc=1`: the line is visible (without `sweetfb_noconsole` if needed), N
   plausible, no `SPMI timeout`, keys and touch unchanged; (2) plus `sweetrtcfloor`: the build
   date; (3) plus `sweetrtcoff`: the right date, time within ±1 min; (4) `sweetrtc=0`: 1969 again;
   (5) after step 0: compare with a seconds-showing reference in the Clock app.
2. **Drop the wait, `sweetrtcpub=1` (0.5 day).** `publishResource("IORTC", this)` only after a
   good read. Acceptance: on video, `fastboot boot` to lock screen drops by about 30 s;
   `BSD root: ufsroot0`, SMP, touch, keys and AppleCLCD unchanged. Default only after the full
   configuration passes **twice**.
3. **Host tooling (1 day).** `build-fajita.sh` appends `sweetrtcfloor=$(date +%s)` and, if a
   local (git-excluded) offset file exists, `sweetrtcoff=`. `tools/rtc-offset.py` takes N from
   the `SWEET RTC` line in the boot video against a reference that shows seconds. A recovery
   reading `/sys/class/rtc/rtc0/since_epoch` is an optional second source. Acceptance: one command
   gives the offset, the next boot shows the right date, the build refuses an over-long boot line
   (§6 step 6).
4. **Offset persistence (2 days, after step 0).** In `bsd_init` after `vfs_mountroot`, read
   `/private/var/db/.sweet-clock-offset` (`v1 <offset> <rtc_at_write> <unix_at_write>`); reject it
   if the RTC went backwards, the age is absurd or the result is below the floor; apply it
   in memory only, forward-only, flagged so the writer does not fire. The setter schedules a
   `thread_call` that writes the file (0600) and `VNOP_FSYNC`s it (no clean shutdown exists).
   Precedence: `sweetrtcoff` or `sweetrtcfile=0` > file > floor. The file is read after the root
   mount because the root is not mounted at the first `IORTC` read. Acceptance: a time set in
   Settings is right after a reboot without `sweetrtcoff`; a corrupted file gives the floor date;
   `time set` / `file written` appear in the pulled log.
5. **Observation boot (0.5 day, after step 0).** With no file and no offset: does `timed` restore
   a saved time, what is the date-picker range, what is the default time zone. One answer each.
6. **Documentation (0.5 day).** PORTING-ENCHILADA.md §10.6, README, PORTING.md, a journal entry on
   drift.

About 7 days. **Risks:** PPID 0x060 has no readable APID → the floor applies and the lane is
poisoned for that boot only; removing the wait exposes ordering bugs → flag off until clean twice;
drift of about 20 ppm (typical, not measured), about 1 min per month; a PMIC power loss is caught
by `rtc_at_write`; each `userdata` flash loses the file, so the boot-arg covers the first boot. No
RTC writes (TZ protection of the write registers is general knowledge, not measured).

## 5. Display geometry, touch and keys

**Goal.** One kernel with the default `CMDLINE` of `tools/build-fajita.sh` under
`BOARD_ENV=tools/enchilada.env`, no `sweetts_*` override, and the right raw range as a kernel
default: taps under the finger across 1080×2280, a bottom-edge swipe goes home and opens the app
switcher, power turns the display off and on, volume reaches iOS. The 6T keeps offset 22,48 and
clamps 1079/2339. The status-bar/dock crop split is chosen and recorded.

**Where it stands (verified).** 0046/0061 and 0173 read `PE_current_console()`, filled by the shim
from `boot_args.Video` (`v_height = FB_H`); the ADT `sweet-fbcon` node feeds only the 0003 console.
0061 centres the panel in the 1125×2436 plane: fOffY 48 on the 6T, 78 here. 0173 derives offsets,
size, raw-range defaults, `rmi_frame` clamps and SurfaceHeight from the panel but leaves
`SweetHIDTouch::touch()` alone, so the 0058 clamp (2399) and the 0071 edge threshold (y > 2351)
remain; its comments wrongly name "ADT sweet-fbcon" and compute 144 mm while saying 145
(`PANEL_MM_H=145` and the FDT say 145). Images `shim-boot-op6-touch-0173.img` (SHA-256
`676f6eb9…d4f3`) and `shim-boot-op6-diag-0173.img` (`5ebf6989…b39e`), 18 706 432 bytes each. Keys:
0091 (PON 0x008, GPIO5 0x0c4, GPIO6 0x0c5) works; 0089 `sweetkeysprobe=1` is the read-only
fallback; 0079 is the display off/on path. Raw range unknown: the FDT says 1080×2160
(`oem,support_1080x2160_tp`), mainline clips y at 2279, the 6T sensor reached 1063/2326.

**Two hypotheses for the missed gestures.** H1: the edge flag is never set because 0071's
threshold is unreachable (ios-sweet NOTES.md line 23: home and the switcher started working once
0071 set `kIOHIDDigitizerEventFromEdgeTip`; against it, the 6T unlocks with the same threshold).
H2: the lowest reachable logical row (2279+78 = 2357 here, 2387 on the 6T, 2417 on sweet) is too
far from the bottom. Step 2 tests H1, step 4 tests H2.

**Steps** (each a `fastboot boot` agreed at its step; never Android for the touch range):

1. **Boot 0173 as built (0.5 day).** Diagnostic image:
   `SWEET TS: fajita RMI4, starting in N s (panel 1080x2280, raw 1080x2280)`; after four edge
   swipes, `SWEET TS: raw max x=.. y=..` with y 2200-2279 (panel-native) or 2100-2160; keys log
   `SWEET KEYS: fajita layout…`, `SWEET HID: key 0x30 down`, `SWEET FB: display off`/`display on`.
   GUI image: the keyboard's bottom row and the buttons under the status bar hit under the finger.
   If unclear: a read-only log of the S3320 F12 max-coordinate register, or `getevent -lp` under a
   recovery with approval.
2. **Edge and clamps (1 day plus a likely CI retry; 08xx).** `touch()` clamps to panel-1 and flags
   edges 48 px from them; logs `SWEET HID: panel 1080x2280 logical 1125x2436 offset 22,78`, echoed
   in `SWEET FB`'s start line. If step 1 found 2160, the raw default becomes kernel-side (F12
   maximum, else panel height). Fix the 0173 comments; SurfaceHeight 145 mm. This **changes the
   6T on purpose** (its edge flag starts firing: 2326 > 2339-48); 6T acceptance is arithmetic
   (22,48, 1079/2339) plus a 6T owner's review if available. OP6 acceptance: ` edge` on a bottom
   swipe; swipe-up leaves Settings and the switcher opens. On failure go to step 4.
3. **Stay-on (0.5 day; = §3.3 I2).** `sweetfb_stayon` in 0079's `kSweetFBRequestPowerChange` case,
   default off. Acceptance besides I2's: with `sweetkeys=0 sweetfb_stayon=1` the lock screen stays
   lit past the timeout and the console logs `display off ignored (sweetfb_stayon)`; without it
   power toggles. Stop if the panel stays black, as in the parallel attempt's boot.
4. **Crop split (1 day).** `sweetfb_offy=N` read by `SweetFramebuffer.cpp` and `SweetHID.cpp`
   through one helper, which the GPU path also uses. 156 rows are always lost: 0 = bottom, 78 =
   split, 156 = top. Boot 156: home gesture works, dock and home indicator visible, status bar
   lost (tests H2). Boot 0: status bar legible, dock cut. The owner picks; photograph the notch and
   corners. Safe-area insets, the structural fix, belong in `fajita/main`.
5. **Tooling (0.5 day).** Fix the `1080x2340` comment in `mkadt.py`; use or delete `PANEL_MM_W/H`.
   Acceptance: `AppleCLCD 1080x2280` on the console; the ADT shows 2280 under `sweet-fbcon` and
   1125×2436 under `disp0`.
6. **Optional (0.5 day):** `EARLY_HEIGHT 2280` and band row 2248 (0010) for both boards.
7. **Only if 2 and 4 fail (0.5 day):** `sweetswipetest=N`, comparing injected and real coordinates.
8. **Display-off fade (0.5 day).** Raise the refresh rate only during 0079's fade, or skip the fade
   at `sweetfb_hz=10`. Acceptance: one off/on cycle on video without visible steps.

About 5-6 days; C++ patches may need a CI retry (`tools/xnu-cc.py` is unverified on C++).
`CMDLINE` replaces the whole default, so copy line 52 and change one argument. **Risks:** an empty
`PE_Video` falls back to 1080×2340 (visible in the start line); stay-on only makes backboardd think
the display is off; a firmware edge-rejection zone (`tpedge_limitfunc limit_enable=1` in the vendor
log) might suppress border contacts (inference; step 1 shows it).

## 6. Engineering infrastructure: fast iteration, logs, CI, upstream tracking

**Goal.** A userspace iteration (build, `fastboot boot`, read the log) under 10 minutes; a kernel
iteration (CI ~7 min, fetch, image, 3-4 min boot, exit, recovery, pull) about 15 minutes; neither
flashes a partition. Logs come from the ring through a RAM-booted recovery. Kernels come from
origin's CI with a recorded commit. This section owns the recovery, the payload archive and the
loader; §3.3 I1 and I3 are the same work seen from the GPU side.

**Where it stands (verified).** `main` = `origin/main` = 6a6ae3b. `xnu.yml` fails on skipped
patches, but its upload runs `if: always()`, so a failed run still publishes a kernel.
`build-fajita.sh` defaults `ARENA_MIB` to 64 and `enchilada.env` does not pin it. The default
`CMDLINE` is about 355 characters, each `sweetfwN=` adds about 28, and `mkpayload.py` cuts the
line at 607 bytes without warning. The SweetAdreno user client is published only after a
successful GPU ladder (0158). NOTES-FAJITA.md (~3290-3302) plans the same payload archive, chardev
and `/usr/local/bin/sweet-install` upstream. launchd here ignores `/System/Library/LaunchDaemons`,
so tools run by replacing a binary launchd execs (DumpPanic). Three build scripts
(`build-bgair-ios.sh`, `mk-bgmtl-adddev.sh`, `mk-metal-probe.sh`) default to another developer's
home paths, and two of them copy a prebuilt `libdrm.2.dylib` that is not in the tree;
`mk-root-with-gpu.sh` also searches such a path for the SDK. No recovery has been booted. The
divergence from `fajita/main` is 14 files (`git diff --name-only fajita/main HEAD`): four of them
are new board files and three are the GLES-route docs/tools, which cannot conflict.

**Steps.**

1. **Recovery log pull (0.15 day; = I1).** Record the image's URL, version and SHA-256; prefer a
   recovery-only TWRP or OrangeFox build over crDroid's. On the iOS boot first swipe every edge and
   the bottom-right corner. `fastboot boot` the recovery; power off at once on an Android
   animation; check `adb shell id` (uid 0) and by-name `userdata` → sda17; never format, wipe or
   mount data; `tools/sweet-log-pull.sh`, then `adb reboot bootloader`. Acceptance: a `SWEETLOG`
   header, the last `SWEET TS: raw max` line, and the next iOS boot mounts without migration. Pull
   before any further iOS boot: the next boot reuses the ring.
2. **Scripts from Git Bash and WSL (0.05 day).** `${ADB:-adb}`, `${FASTBOOT:-fastboot}`, a
   `cygpath` fallback; offered upstream. Acceptance: the pull works from both shells.
3. **Kernel fetch (0.2 day).** `tools/ci-kernel.sh [-R repo]`: `gh run list -w xnu --status
   success`, record `headSha`, download `xnu-kernel`, check SHA256SUMS (transport only), keep the
   `kernel.development.sweet.<sha>-<tree>` naming. Propose `success()`-gated uploads upstream.
   fajita's artifacts lack 0173 and are not used here.
4. **Pre-push checklist (0.05 day):** `git status`, diff, grep for user paths, e-mails, serials.
   Acceptance: a planted user path is caught.
5. **iOS cross toolchain (0.5 day, consent first).** clang/lld, meson/ninja/mako/pyyaml, the
   iPhoneOS 16.5 SDK, `aarch64-linux-gnu-gcc`, `llvm-nm`, apfs-fuse, mkbootimg, and the libdrm
   stand-in from `sweet_drm.c` (NOTES-FAJITA.md 2026-10-27 recipe); scripts made
   environment-driven (shared with §11 step 3). Acceptance: `file` reports arm64 Mach-O for
   libbgair, libdrm and bgmtl-adddev.
6. **Payload archive (1 day).** Agree one TOC format and loader name with upstream first.
   `mkpayload.py --files DIR` writes a TOC (path, mode, size, offset, sha256) and **fails** when
   the boot line plus `sweetfwN` announcements would exceed 607 bytes (this guard also protects
   the clock, Bluetooth and modem blobs). Exposure: try `--ramdisk` → `/dev/rmd0` in its own boot,
   else a board-neutral chardev (`/dev/sweetpayload`) registered unconditionally, not behind
   `sweet_gpu_ready()`. Acceptance: `SWEET INSTALL: payload <n> files … sha <8 hex>` matches the
   host.
7. **Loader and the last planned root flash (1.2 days; = I3).** A small loader linked against
   libSystem; settle the launch order (DumpPanic vs backboardd) before relying on it for GL
   libraries, else install from the kernel before launchd. `sweetinstall=0` skips it,
   `sweetinstall=restore` restores the `.orig` files. Bundles go to named bundle directories
   (`Chlorophyll.bundle` under `/System/Library/Extensions`). BASE copy, then one confirmed
   flash, shared with §7 step 3. Acceptance (with I3's): one "updated" line per changed file; ten
   boots need no flash and show no `mount[7]` failure; the loop measures under 10 min.
8. **Variant files (0.3 day).** Pin `ARENA_MIB=1` in `enchilada.env` (K3 raises it in its own
   boot); commit per-boot command lines as `tools/enchilada/variants/*.cmdline`;
   `tools/build-variant.sh NAME` writes `shim-boot-<kernel sha8>-<name>.img` and a sidecar of
   basenames and hashes in `shim/out`; restore fajita's banner text. Acceptance: two variant builds
   give two image names and two sidecars.
9. **Merge procedure (0.2 day, then 15 min a day).** Merge `fajita/main` daily and before each
   kernel build; never edit upstream patches or journals; offer board-neutral patches once they
   boot (0173 first); on a number clash renumber in the merge commit and re-run
   `check-hunk-counts.py` and a sequence check. Acceptance: a dry run conflicts only in files of
   that list.
10. **QEMU smoke job (0.6 day).** A separate workflow: payload, `mkadt.py --qemu`,
    `qemu-sweet.py --kernel … --fail-on-panic` on a small HFS ramdisk root (`rd=md0`). The CI
    payload carries no phone DTB and no a630 firmware; it uses `mkadt.py --qemu` and empty blobs.
    Acceptance: a deliberate panic turns it red, a good kernel reaches a named milestone, under
    5 min added.
11. **Image hygiene (0.15 day).** One BASE per flashed image; the `.simg` is the restore (a failed
    mount means a full flash); `fallocate -d` and compact the WSL disk; one IPSW copy. Sparse
    timing and DONT_CARE tests are separate confirmed writes, only when a flash is due anyway.
    Acceptance: free space recorded before and after.

Critical path 1 → 3 → 5 → 6 → 7, about one part-time week, with one planned flash; about 4.4 days
in all. I1 (1 day) and I3 (3 days) in §3.3 are the same work as steps 1 and 6-7 here, including
retries; count them once. Deferred: USB live log (§7 step 6), EDL pulls, images above 64 MiB.
**Fallbacks:** a recovery that boots Android or offers a wipe → stop rule; AMFI refuses fresh
binaries or the loader runs after backboardd → kernel-side install before launchd; upstream ships
its own loader → adopt it; macos-14 retired → pin the toolchain; the ring lags a panic → keep
photographing panics.

## 7. UI completeness: crash-looping daemons, logs, wallpaper

**Goal.** Lock and home screens with the right date, the panel lit while working, no daemon
crash-looping, the default wallpaper drawn once a Metal device exists, a decoded log on the PC
after every boot. The ring pull (§6 step 1), stay-on (§3.3 I2, §5 step 3), the clock (§4) and the
loader (§6 steps 6-7) are owned elsewhere.

**Where it stands (verified).** `sweet-root-tweaks.py` renames `_PanicOnCrash`, removes CommCenter,
skips Setup, and seeds the activation ark only if the container exists. Edits to existing jobs in
`/System/Library/xpc/launchd.plist` work with `launchd_unsecure_cache=1`; new jobs are unproven.
0048 tees `/dev/null` writes of the `sweetnull` processes into the ring as `|name| text`;
`StandardOutPath=/dev/console` stopped backboardd from launching (NOTES.md v8). The 0042 `exec` and
0043 `CRASH` lines have no timestamps and miss clean exits and kills (jetsam included). On sweet the
pulled root had no `.ips` files and an empty `uuidtext`.

**Steps.**

1. **sweetnull boot (0.5 day).** `sweetnull=PosterBoard,mobileactivationd,fairplayd.H2,bluetoothd`,
   a short boot, then a pull. Acceptance: `|name|` lines for at least one listed daemon.
2. **Timestamped census (1-1.5 days with CI).** Seconds since boot on the 0042/0043 lines;
   `tools/sweet-log-stats.py` counts exec and CRASH per process and minute (per fixed-length boot
   until the patch lands); state the blind spot; record whether an activation sheet appears.
3. **Root tweaks v2, in the I3 flash (2-3 days).** (a) Disable or throttle `bluetoothd`,
   `fairplayd.H2`, `PosterBoard` (until §7 step 5) and other loopers (`bluetoothd` returns with
   §8). (b) Try `ThrottleInterval` on one daemon (`KeepAlive=false` does not stop MachServices
   launches). (c) `OS_ACTIVITY_DT_MODE=YES` and `CFLOG_FORCE_STDERR=1` for the sweetnull set,
   without StandardOutPath. (d) A test job `org.sweet.hello`. (e) Activation only if step 2 saw a
   sheet; seeding needs a post-migration root pulled from the phone (16 GiB; check free space) or a
   boot-time writer. Validate by loop-mount and plistlib round-trip. Acceptance: loopers absent or
   at most 1 exec per boot-minute; Settings opens.
4. **Unified log and crash reports (1-2 days).** A 15 s power-key reset leaves HFS+ dirty, so shut
   down cleanly or accept stale data. A static aarch64 `hfsdump` needs consent; else copy the root.
   Pull `/private/var/db/diagnostics`, `uuidtext`, `CrashReporter` and `/private/var/log`. A
   format-string source for an empty uuidtext is open; step 3(c) is the fallback.
5. **Wallpaper on Metal (1.5 days after P4).** Kill file, allow/deny lists, nil `+alloc`
   fallback, a watchdog from the first commit, `CI_USE_MTL_DAG_FOR_CIKL_SRC=0` and
   `CA_USE_CGTEXTUREDATA=0`; a poster process first, SpringBoard last. Acceptance: with the kill
   file the UI matches the CPU-rendered one; with Metal on the wallpaper shows and there is no
   PosterBoard or SBRendererService CRASH for 10 min.
6. **Live USB log (10+ days, unmeasured).** Read-only USB30 GDSC/CBCR probe, then one variable per
   boot, GPU off; `usbipd-win` needs consent. Acceptance: `1209:0001` enumerates and udp/5140
   streams.

About 16-18.5 days. **Risks:** a recovery that repairs `userdata` damages the root; a malformed
`launchd.plist` starts nothing (keep the `.orig`); removing `bluetoothd` may break Settings panes;
probe GDSCs before writing them. Bergamota's launchd notes are unverified and target iOS 18/26.

## 8. Bluetooth (WCN3990 over UART)

**Goal.** The kernel powers the WCN3990, downloads its rampatch and NVM over QUP GENI UART6
(`serial@898000`) and gives the iOS stack a transport it accepts: the Settings switch turns on, a
scan lists devices, a headset or phone pairs. A kernel test mode that counts found devices is an
earlier milestone of its own. No modem, remoteproc, QRTR or rmtfs is needed.

**Where it stands.** Verified: no Bluetooth code exists in any of the trees; `bluetoothd`
crash-loops on the 6T with no recorded reason; `mkadt.py` sets `/product` `bluetooth-le = 1` but
has no uart node. Mainline: `qcom,wcn3990-bt`, `max-speed 3200000`, NVM
`OnePlus/enchilada/crnv21.bin` plus the generic `crbtfw21.tlv`, no BD address, vddio
`vreg_s4a_1p8`. The root contains `No valid serial port found (tried cu.bluetooth and
uart.bluetooth)`, `transport-encoding`, `transport-speed`, `BT_BAUDRATE`, `local-mac-address`,
`/etc/bluetool/%s.boot.script` and `com.apple.IOUserBluetoothSerialDriver`; there is no
`/etc/bluetool`.

**Verified elsewhere, untested here:** the hackios research cites `docs/LEMONADE-BLUETOOTH.md`
(b1ackm4x/hackios-xnu-kernel, OnePlus 9): H4 with QCA IBS, TLV download, a kernel-control socket
`com.apple.uart.bluetooth` that stock `bluetoothd` connects to, nanoregistryd services, compat
patches for the Broadcom assumption; inquiry and LE scan reported working, pairing not. WCN3990
uses the same TLV and IBS, so the transport carries over; UART and rails are new. The document
itself has not been read; PORTING-ENCHILADA.md §10.3 ("No neighbour has Bluetooth yet") is
corrected to say a hackios fork reports inquiry and LE scan on a OnePlus 9, unverified.

**Inferred, to check before coding:** wrap0_s6 RCG 0x17754 / CBCR 0x17750, vote bit 16, AHB bits
6/7, M/N, GIC SPI 607, gpio45-48 function 1 (EAST), rails L7A 1.8 V / L17A 1.304 V / L25A 3.3 V,
the 0xC0/0xFC pulse delays, the NVM deep-sleep tag polarity.

**Steps** (each boot agreed; a root change is a confirmed flash or rides the loader; patches
against `fajita/main`, since the 6T has the same wiring):

1. **Inputs (0.5 day plus consent).** Read LEMONADE with consent. List `/vendor/bt_firmware`
   (mount, names, sizes, SHA-256) under a recovery and copy it outside git (pmOS firmware as
   fallback); extend `enchilada-facts.py` with it, `/dev/ttyHS*` and the uart6/BT nodes. Decode
   the D22 ADT (`lzfse` or `ipsw`, an install needing consent; never in public CI). Acceptance:
   the D22 bluetooth node and BlueTool's integer for plain H4 recorded.
2. **Userland go/no-go (4 days), no chip, parallel with 3.** Record why `bluetoothd` and BlueTool
   exit. A fake controller (`/dev/uart.bluetooth`, or the `com.apple.uart.bluetooth` socket if
   step 1 confirms it) answers Reset, Read_Local_Version, Read_BD_ADDR and the Broadcom VSCs from a
   table and hex-dumps what it receives; try a minimal `/etc/bluetool/<chip>.boot.script`.
   Acceptance: which binary opens the transport and what it sends. **Gate:** if nothing opens it,
   re-plan before steps 4-7.
3. **Read-only probe (`sweetbt=probe`, 2 days).** FW_REVISION, HW_PARAM, IOS, FIFO-disable, QUPV3
   version, 0x5200c bits, CBCR/RCG/DFS, gpio45-48, PM8998 GPIO3, RF_CLK2 if readable. Acceptance:
   FIFO mode available, no fault, DFS vs M/N decided, oversampling known.
4. **UART loopback (4 days).** Clock votes, the RCG through a helper shared with touch, SE init as
   `qcom_geni_serial`, LOOPBACK_CFG = 0x3, 32 bytes at 115200 and 3.2 Mbaud. Acceptance:
   `loopback ok` at both rates; other CBCRs unchanged.
5. **Rails, pins, pulses (4 days).** `ldoa7`/`ldoa17`/`ldoa25` in `sweet_rpmh.c` with its
   2856-3400 mV window widened; pin bias per the board override; pulses per `hci_qca.c`.
   Acceptance: three AMC votes complete, CTS asserted.
6. **Chip version and firmware (6 days).** EDL 0x19 expecting rom_ver 0x21; both blobs as payload
   indices sweetfw4/5 or by magic (under the §6 step 6 guard); TLV download, NVM baud and address
   patched, IBS kept unless step 2 rules it out (deep sleep off is a labelled deviation).
   Acceptance: every segment acknowledged, Reset status 0, Read_Local_Version reports Qualcomm.
7. **Radio checkpoint (`sweetbt=test`, 3 days).** Inquiry and LE scan. Acceptance: a count, RSSI
   and hashed addresses on the console.
8. **Real transport plus proxy (15 days budgeted, open-ended).** The step 2 transport on the chip;
   OGF 1-6/8 passed through, Broadcom OGF 0x3F answered, QCA 0xFF events filtered, baud requests
   mapped onto the GENI clock; LEMONADE's socket and nanoregistryd services are the first design to
   try. Acceptance: Settings switch on, scan, pairing.
9. **Hardening (5 days).** RFR watermark and IRQ, screen off/on and `bluetoothd` restarts, power
   cycling, a BD-address policy. Acceptance: 30 min of scanning across 5 screen off/on cycles and 3
   `bluetoothd` restarts without a UART overrun or fault line.

About 44 days, with step 8 budgeted at 15 and open-ended. Needs a GUI-boot log path (§6 step 1)
for steps 2 and 8, the RPMh ACTIVE-TCS proof from the touch boot, and coordination with Wi-Fi on
the rails (Bluetooth only votes them on). **Risks:** step 3 only reads, and later steps write only
the s6 RCG and 0x5200c; no rail is voted off; if BlueTool's Broadcom path cannot be satisfied,
report the radio as working without Settings; if step 6 fails, check RF_CLK2 before the UART.
Firmware, the D22 tree and the BD address never reach git or logs; scanned addresses are never
shown in full.

## 9. Wi-Fi (WCN3990 over SNOC)

**Goal.** Settings → Wi-Fi shows nearby networks, a WPA2-PSK network joined from Settings stays
joined, configd's DHCP gives `en0` a lease, Safari loads an `http://` page (`https://` after §4).
All behind `sweetmodem=0/1/2` and `sweetwlan=0/1/2`; at 0 a boot equals the baseline.

**Where it stands.** Verified: `wlanmdsp.mbn` runs on the modem DSP and is fetched by it over TFTP
(PORTING-ENCHILADA.md §10.2), so **no modem, no Wi-Fi**: §10 is the prerequisite and its S7
hand-off is where this section starts. `wifi@18800000` uses `RPMH_RF_CLK2`, GIC SPI 414-425,
`apps_smmu` stream 0x40, supplies S4A, L7A, L17A, L25A, L23A, L5A, the 8-bit host-cap quirk and
variant `oneplus_sdm845`; `firmware-5.bin` and `board-2.bin` are in linux-firmware. Nothing in the
tree covers `apps_smmu`, SMEM, SMP2P, GLINK, QRTR, QMP or IO80211.

**Reusable recipes (verified in those trees, untested here).** ios-flame (SM8150, iOS 16.7.16):
userland `wland` with scan, WPA2-PSK and wifid on en0; `phone/wifi/*`; patches 0094 (`/dev/pmem`,
SCM for userland), 0123 (en0, Apple80211, station over `/dev/wlan`), 0089/0090 (apps SMMU: own
context bank, translation off); it powers WLAN before booting the modem. hackios (SD778G, 16.5):
Linux ath11k compiled into the kernel against FreeBSD LinuxKPI headers, its own station/WPA
(`lx_80211`, `lx_wpa`), a BSD `en0`, `hakios.apple80211.c` for SIOCGA80211/SIOCSA80211 and IOKit
objects so configd creates "Wi-Fi", 55-90 Mbit/s there. For SDM845 the station, WPA, Apple80211
and IOKit glue carry over; the radio is ath10k SNOC.

**Steps.** Modem, host services and WLFW in the kernel (seconds per iteration with
`fastboot boot`); radio and station in the kernel with ios-flame's `/dev/wlan` split so they can
move to userland. Console-only boots until step 7.

1. **Measure (1 day).** Through a recovery mounting `modem_b`/`vendor_b` read-only, or from
   `firmware-oneplus-sdm845`: `mba.mbn`, `modem.mdt/.bNN`, `wlanmdsp.mbn`, `bdwlan*`, `*.jsn`,
   `ipa_fws*`; FDT smem, smp2p-mpss, mss_pil, wifi, ipa, tcsr-mutex; cmd-db rail names. No EFS.
   Acceptance: `summary.txt` names every file, base and rail.
2. **Probe (`sweetmodem=1`, 3 days).** §10 S1 plus `apps_smmu` sCR0 and SMR/S2CR for streams
   0x40/0x41 (a new MMU-500 reader) and PM8998 GPIO3 as an input. Acceptance: a lock-screen boot
   and one `SWEET MSS:` block; item 435 present or absent is recorded.
3. **Modem to S7 (§10).** `assign_mem` (3 days), firmware into the root (1 day, a confirmed flash,
   blobs never committed), UFS LUN 5 read-only (2 days, approval, no write path compiled, sizes
   only), modem boot (10 days) and services (8 days) are §10 S2-S7. Wi-Fi adds, before the modem
   boot, the WCN3990 rail and RF_CLK2 votes and the QDSS QMP message, and the acceptance "WLFW
   published, `wlanmdsp.mbn` fully served, no FATAL for 2 min".
4. **WLFW (`sweetwlan=1`, 4 days).** Stream 0x40 on its own context bank, translation off, unless
   step 2 shows bypass. `ath10k/qmi.c` handshake: 8-bit `host_cap`, MSA 0x8df00000 assigned to
   MSS_MSA/WLAN/WLAN_CE, BDF in 6144-byte chunks (board-2.bin fallback), `wlan_cfg`, mission mode;
   nothing in the WLAN window before that. Acceptance: the CAP reply and "mission mode".
5. **Radio and scan (`sweetwlan=2`, 7-10 days).** CE rings, HTC, WMI-TLV, HTT (versions from
   `firmware-5.bin`), polled first, SPI 414-425 later; weigh ath10k-on-LinuxKPI here (§14).
   Acceptance: the home BSS listed, masked.
6. **Station and `en0` (7-10 days).** Auth, assoc, 4-way handshake, CCMP/GTK, an 802.11↔Ethernet
   bridge; `en0` from 0075/0081 with `IFNET_SUBFAMILY_WIFI`; MAC from WLFW or a fixed locally
   administered one; first join with a static IP and SSID/PSK from a boot-arg-named file (a
   confirmed flash; no real credentials in any sample). Acceptance: a LAN host pings the phone.
7. **iOS integration (7-10 days).** IONetworkStack, `IO80211Controller` and IONetworkInterface
   stand-ins, the Apple80211 ioctl table, topaz 0128 / ios-flame 0123-style busy-hold removal.
   Acceptance: join from Settings, DHCP lease, Safari over http.

Steps 4-7 are 25-34 days on top of §10; steps 1-2 overlap §10 S0-S1. Steps 5-7 can each slip.
Needs the USB live log or a ring reader (hard for step 7), the RTC, root tooling and stay-on.
**Risks:** a wrong or repeated `assign_mem` wedges a CPU (once per region per boot, never reclaim
the MSA while the modem runs, cold power-cycle after a failure); unclocked blocks hang the bus
(gate every read); prints mask MAC, BSSIDs, SSIDs, IPs, the PSK and EFS bytes; a stalled MBA/RMB
parks the workstream, since no route avoids the modem. Open: CE ring address limits (ath10k's
WCN3990 mask is reportedly 35-bit), a QDSS vote or extra AOP `load_state`, the unsourced 20 ms MSA
pause.

## 10. Modem subsystem (remoteproc, SMEM, GLINK, QRTR, QMI), scoped

**Goal.** XNU boots the MPSS with the phone's own firmware; it stays up 30 minutes without
err-fatal and announces services over QRTR; our TFTP server answers and logs every path. That is
the hand-off to §9. Out of scope: telephony, SIM, IPA, GNSS, CommCenter. Also deliverable: fix
PORTING-ENCHILADA.md §10.4, which says "PAS loader": SDM845 MSS (`qcom,sdm845-mss-pil`) uses MBA
self-auth, the MBA/RMB path of `qcom_q6v5_mss.c`, which no neighbour has under XNU.

**Where it stands (verified).** Memory regions as in §1; mainline chooses rmtfs at
0xf5b00000+0x202000 (guard pages, client-id 1, VMID MSS_MSA), plain RAM on the phone and free under
XNU only if the shim, ADT and payload avoid it. 0146 implements only SCM PAS for the zap, carries
x0-x6, and re-issues INTERRUPTED calls without restoring x1-x5; `assign_mem` needs the
extended-argument buffer in x5. `ml_io_map` is one `kmem_alloc`: 40 MiB panicked, 1 MiB is the
largest that worked. The kernel parses only `sweetfw0..3`, all used by the GPU; a firmware payload
works only tethered (`boot_a` is 64 MiB). UFS reads LUN 0 only. **To confirm** (sdm845.dtsi or
Linux, not the phone): `qcom,pil-self-auth`; SMEM at 0x86000000; IRQs SMP2P 451, GLINK 449, MSS
watchdog 266, QMP 389; GLINK doorbell bit 12 at `apss_shared`+0xc; QMP at 0x0c300000; SMEM items
421/428/435/478-480; the `sdm845_mss` proxy (xo, prng) and reset (iface, snoc_axi, mnoc_axi)
clocks.

**Decisions.** **D1:** (a) GLINK and QRTR in the kernel (CI build plus `fastboot boot` per
iteration; ios-flame's stack rewritten), or (b) a minimal `/dev/sweetmss` (whitelisted mmap, an
assign ioctl, the doorbell) with ios-flame's `link.c`/`glink.c` nearly unchanged, at a flash per
iteration unless a recovery with adb or the §6 loader works. Choose (b) only once that is proven;
the MBA ladder stays in the kernel either way. **D2:** S1-S5 console-only, with one
`sweetfb_noconsole=1` boot per level for the lock screen; S6+ need a log path; logging whitelisted
by message type (no DMS, no EFS, nothing that can show the IMEI or serials).

**Steps** (`sweetmss=N` on a `fastboot boot` image with `adreno=0`; every failure path halts the AXI
ports, returns memory to HLOS and drops its votes; about 30 days in all, rough, as given per step;
the 6T GPU ladder took about 4 calendar days):

1. **S-1 Groundwork (1.5 days).** A windowed physical-access primitive (1 MiB windows, as
   0170-0172) for SMEM, rmtfs, the MBA and the 120 MiB MPSS copy; a table of every fixed low-bank
   address, each pattern-tested once; TZ-read buffers uncached or cleaned before every SMC.
   Acceptance: every table address pattern-tested, logged once.
2. **S0 Firmware and DT, without Android (3 days).** `firmware-oneplus-sdm845` first, the
   `modem_b` tree later (recovery or a read-only LUN 4/5 reader); compare the image version with
   what the EFS expects; mss/smp2p/glink/smem/qmp nodes from the phone's DTB. No EFS dump to the PC
   unless the owner decides so; preferred is an on-phone read-only read into a RAM overlay.
   Acceptance: the mba/modem version strings and whether they match the EFS expectation recorded
   in `summary.txt` (no EFS bytes).
3. **S1 SMEM read-only (2 days),** gated on GCC CBCR/GDSC and the RPMh MSS/CX/MX state.
   Acceptance: `SWEET MSS: smem v…, ptable N, apps-mpss free 0x…`.
4. **S2 Shared SCM helper (3 days):** extended arguments, Linux-style resume (restore x1-x5, keep
   x6, x7=0), an availability check; one assign of rmtfs {HLOS} → {HLOS, MSS_MSA} with a pattern
   test. `sweet_gpu.c` moves over only after K0. Acceptance: `assign rmtfs status 0`, pattern
   intact, no hang.
5. **S3 Allocation and doorbell (2 days):** `smem_alloc` under hwspinlock 3; SMP2P 428 (version
   last), GLINK 478/479; a poll thread on 435/480. Acceptance: `smem_alloc` returns items
   428/478/479; the SMP2P version handshake completes.
6. **S4 MBA boot (5 days):** QMP `load_state modem on`; proxy and active votes, proxy released on
   handover; GCC branches and resets; the MBA as a tethered `sweetfw4`, copied then assigned; the
   QDSP6SS FSM. Acceptance: `pbl status 1` and the `mba status` word; failures print theirs.
7. **S5 MPSS load (5 days):** metadata assigned, `META_DATA_READY`, assigned back (the only second
   assign); segments into 0x8e000000, `PMI_CODE_START/LENGTH`, `AUTH_COMPLETE`, SMP2P ready within
   30 s, item 421 printed on a fatal; one attempt per cold boot; stop path in the same patch.
   Acceptance: `modem ready`, no FATAL for 60 s.
8. **S6 GLINK and QRTR (4 days)** per D1; poll interval set by its CPU cost under `cpus=1`.
   Acceptance: the NEW_SERVER list, no stall after 8 packets.
9. **S7 rmtfs, pd-mapper, TFTP (4 days):** rmtfs serves the RAM overlay with a session-only write
   shadow and never opens live partitions; pd-mapper answers `wlan/fw` and the `modemr.jsn`
   domains; TFTP RRQ/WRQ with a RAM `/readwrite` and blksize/tsize (rsize/seek/wsize inferred),
   logging every path. Acceptance: rmtfs sessions, the TFTP log, 30 minutes up.
10. **S8 Time (optional, 0.5 day, not counted):** drop it if the modem only mirrors the RTC; §4
    stays the clock.
11. **S9 Stop and panic (1 day):** force-stop, stop-ack, QMP off, un-assign; stop from the panic
    path; detect a modem left running. Acceptance: a clean boot after a crashed session; `boot_b`,
    `vendor_b` and `modem_b` never written.

**Risks.** A root image with EFS data is never uploaded or shared, not even privately. Private EFS
copies (ios-flame's fallback) mean IMEI-bearing data and need explicit approval. TZ/hyp faults can
wedge the phone: Linux ownership order, one change per boot. An EFS/firmware mismatch can loop:
compare versions first, print item 421. Without an IPA QMI server the modem may stall; fallback a
minimal responder.

## 11. Apple security stand-ins (AMFI, sandbox, code signing)

**Goal.** (1) Today's permissive model, with one page listing every stand-in and why. (2)
`build-fajita.sh` refuses a command line that would kill launchd. (3) Offline answers to the two
questions blocking GPU userland: does this kernel run unsigned Mach-Os, and why does dyld refuse
`@rpath`? (4) The README says iOS cannot be made secure here without Apple-signed artefacts. Step
0 shares the dyld work with §3.5 S-G and runs in the same week.

**Where it stands (verified).** No trust caches (0015). AMFI interface 0025, XML entitlements
0035; the `SWEET AMFI` policy (0035/0036) hooks only `mpo_vnode_check_signature`, setting
`CS_SIGNED` and, on the root, `CS_PLATFORM_BINARY`; binaries without `LC_CODE_SIGNATURE` never reach
it; no `CS_ENFORCEMENT`/`CS_KILL`/`CS_HARD`. Sandbox (0050, 0064) allows everything except ops 4,
5, 6, 0x43. Root unsealed and read-write (0029, 0031); `lp-sip0=0x6f`, `lp-sip1=1`
(`mkadt.py:213-217`); AppleKeyStore stand-in (0038) without passcode. Required, unchecked
boot-args: `unentitled_ios_sim_launch=1` (a DEVELOPMENT tunable, NOTES.md:175),
`launchd_unsecure_cache=1`, `ignition_level=1`, `rd=ufsroot0`. dyld refused `@rpath` ("security
policy does not allow @ path expansion") while `/usr/local/lib` copies loaded (NOTES-FAJITA.md
~3268); probes link with lld without `-adhoc_codesign`. **Inferred:** dyld asks
`__mac_syscall("AMFI", ...)`, so our name `SWEET AMFI` yields `ENOPOLICY`, as 0050 fixed for
`Sandbox`; dyld may keep separate flags for `@`-paths and fallback paths (unconfirmed).

**Steps.**

0. **Offline (1-2 days).** (a) `llvm-objdump --macho --private-headers` on the built products; no
   `LC_CODE_SIGNATURE` in `bgmtl-adddev` proves unsigned execution. (b) Disassemble 20H392 dyld and
   libsystem: policy name, call number, struct and flag bits for `@`-paths, and the
   `DYLD_INSERT_LIBRARIES` decision for S-G. (c) Search for `AppleMobileFileIntegrity`. (d) Decode
   the IPSW trust-cache headers. (e) Read `unentitled_ios_sim_launch` in the CI xnu-8796 tree.
1. **Inventory page (1 day).** `docs/security-standins.md`, a README Security paragraph and
   boot-arg table, PORTING-ENCHILADA.md §3.7 (with the OnePlus 6 strings) and §10.7. Acceptance:
   every row names a patch, boot-arg, ADT property or tool.
2. **Command-line guard (0.5 day).** Without `FORCE_CMDLINE=1`, refuse a `CMDLINE` missing any of
   the four arguments; list DEVELOPMENT dependencies in `xnu.yml`. Acceptance: a removed argument
   stops the build by name; the recorded OnePlus 6 strings pass.
3. **Signing convention (1 day).** `-Wl,-adhoc_codesign` in the three build scripts, a
   `LC_CODE_SIGNATURE` check unless `ALLOW_UNSIGNED=1`, host paths as `IOS_SDK`, `CHLOROPHYLL`,
   `BERGAMOTA`, `LIBDRM`, `OUT`. Only if 0(a) is inconclusive: one boot with an unsigned DumpPanic
   hand-over binary.
4. **dyld `@`-path policy (2 days).** Patch A (only if 0(b) is inconclusive) logs each
   (policy, call) on `ENOPOLICY` in a console-only boot. Patch B: a second policy named `AMFI`
   behind `sweetdyldat=1`, answering only the dyld call found offline; everything else
   `ENOPOLICY`; first use of each call logged; the test binary signed and recorded. Acceptance:
   `bgmtl-adddev` loads from `@executable_path` without the `/usr/local/lib` copies, and the lock
   screen is unchanged with `sweetdyldat=0`; otherwise document absolute install names (G1 already
   uses them). Test binaries ride the §6 loader.
5. **Optional cdhash allow-list (no estimate until 0(d)).** `tools/trustcache-dump.py` from the IPSW
   plus the port's manifest, sized against the arena first; `sweetcs=strict` also refuses execs
   without `CS_SIGNED`. Acceptance: a permissive boot logs no `unlisted`; a strict boot reaches the
   lock screen and refuses an unsigned and an unlisted signed binary.
6. **Optional housekeeping.** Compile-time exec permission under SWEET; narrow `lp-sip0` one bit
   per boot; never remove `launchd_unsecure_cache` or `asmb`.

About 5.5-6.5 days for steps 0-4; steps 5-6 are optional and unestimated. **Risks:** a policy named
`AMFI` sees every process's `AMFI` calls, so unknown calls return `ENOPOLICY`, never 0 with
unwritten outputs; entitlement checks may appear once the Metal device is non-nil, and lld cannot
embed entitlements (ldid-style signing needed). 0158's `AGXDeviceUserClient` alias only mirrors
real iOS profiles: our sandbox allows every check.

## 12. Battery, charger, slider, audio, haptics, camera, sensors

**Goal.** Real battery percentage; a charging bolt that follows the cable within about 3 s; the
alert slider switching ring and silent; felt keyboard taps; a CoreAudio plug-in showing whether
16.7.16 builds a route; speaker audio later; camera, NFC, fingerprint and sensors parked with the
real reasons.

**Where it stands (verified).** `SweetBattery` reports a static 100 %; `sweetbattery=1` polls
sweet's PM6150 addresses, wrong here. Gauge bq27541 at 0x55 on SE10, design 3240 mAh, FCC 3057;
under Android its SOC was 31 while PMI8998 `bms` said 51, so the PMIC FG percentage is not usable.
SMB2 charger on SID 2 (`qcom_smbx.c`, `pmi8998.dtsi`): 0x1006 status (0 trickle … 4 taper, 5
terminate, 6 inhibit, 7 disable), 0x1310 bit 4 = USB plugged, 0x160b power path, 0x1651/0x1653
watchdog (Linux disables it; XNU does not), RRADC 0x4500. bq27541 map TEMP 0x06, VOLT 0x08,
AvgCurrent 0x14, SOC 0x2c, FCC 0x12, DCAP 0x3c; bq27411 0x02, 0x04, 0x10, 0x1c, 0x0e, 0x3c. TLMM
tiles as in 0096, pin register at base + 0x1000 × pin; gpio55/56 (NORTH, qup10) and 89/90 (SOUTH,
qup4) are I2C; slider gpio126 silent (EAST), gpio52 vibrate (NORTH, a spare SE12 pin), gpio24 ring
(SOUTH). Audio: `VirtualAudio.plugin` is disabled; mediaserverd crashes on the missing `vdef`
device (NOTES.md). Camera: `camss@acb3000` in mainline, sensors only as comments in the OnePlus
dtsi.

**Steps.** Steps 1-4 are board-common and offered to fajita. Probe boots:
`cpus=1 sweetsmp=0 sweetfb_console=1 sweetkeys=0 sweettouch=0`, GPU off, plus the probe flag,
read from photos or the ring.

1. **PMI8998 probe, `sweetbattprobe=1` (1.5 days).** Allow SID 2 peripherals 0x10, 0x13, 0x16,
   0x45; every 15 s dump 0x1006/0x1007, 0x1310, 0x160b, 0x1651/0x1653, RRADC, and the TLMM cfg of
   gpio55/56/24/52/126; two dumps with the cable, two without. Acceptance: 0x1310 bit 4 follows the
   cable; 0x1006 reads 0-4 only while plugged.
2. **Gauge on SE10 (3-4 days).** Per-SE GENI constants; the stride-derived SE10 GCC values (CBCR
   0x18274, RCG 0x18278) checked against `gcc-sdm845.c`; address only 0x55; keep the map whose VOLT
   reads 3000-4500 mV and DCAP about 3240; publish after 5 in-range reads; clamp SOC 1-100 and
   temperature 0-45 °C (inferred powerd/thermal risk). Acceptance: VOLT within 50 mV of a meter;
   SOC falls monotonically over 30 min on battery; no SE10 timeouts.
3. **Charger state (1 day).** 0x1310/0x1006 every 1-2 s, the gauge every 30 s; bit 4 →
   ExternalConnected, 0-4 → IsCharging, 5 → FullyCharged, 6/7 → connected, not charging.
   Acceptance: the bolt follows the cable within 3 s.
4. **Alert slider (2-4 days).** Find how 16.7.16 receives the ringer state; one log-only boot of
   the three levels after the keys boot; no pin writes; silent and vibrate → mute, ring → ring.
   Acceptance: the mute banner follows the switch and is right after a reboot.
5. **Audio contract test (4-6 days after the loader).** A null-sink build of the hackios
   AudioServerPlugIn skeleton, the VirtualAudio move made optional, a D22AP `/product/audio` node,
   a test binary printing the route and MobileGestalt's haptics answer, delivered by the loader.
   Acceptance: mediaserverd stays up with VirtualAudio enabled, Settings > Sounds opens, the test
   prints a route.
6. **Haptics (7-10 days, after 5).** The first PMIC write path: owner-EE channel via 0091's lookup,
   limited to SID 3 peripheral 0xc0, behind `sweethaptic=1`, every write read back, parameters from
   sdm845-mainline `qcom-spmi-haptics` and the DT (none verified), a 1 s motor watchdog; the first
   writes need the owner's explicit agreement for that boot. Acceptance: one 20 ms pulse felt per
   keyboard tap, every write read back equal, the watchdog stops a stuck motor within 1 s.
7. **Speaker ladder, `sweetsound=1..5` (20-40 days, after GPU and Wi-Fi).** Firmware (pmOS package
   or `modem_b` read-only); PAS ADSP with the APCS IPC mailbox (inferred); SMEM/GLINK/QRTR and
   pd-mapper shared with §10; AFE QUAT_MI2S_RX and MAX98927 (SE4 0x3a, reset tlmm 69) playing 1 kHz
   at -20 dBFS; iOS audio through a limiter. Firmware travels only in the payload.
8. **Document what is parked (0.5 day).** Camera: hackios shows a route (RAW10 kernel device,
   FigCaptureDevice injection into mediaserverd, software ISP), so the blockers are the missing
   CAMSS/CCI driver under XNU and IMX519 support only from 6.18+ downstream. Sensors: behind the
   SLPI (PAS, FastRPC, SSC). NFC and fingerprint: no iOS stack to plug into (inferred). Platform:
   CPU frequency scaling, thermal mitigation and system sleep (ABL's clocks are kept). Acceptance:
   PORTING-ENCHILADA.md §10.5 and the README list each parked item with its blocker.

**Risks.** On SE10 never address 0x26 (Dash MCU) or 0x08/0x0c (smb1355) and never send bq Control
subcommands; test with a plain charger first. If gpio55/56 are not on qup10, step 2 needs an agreed
mux write (fallback: SMB2 state plus a voltage-derived SOC). An armed charger watchdog may stop
charging; step 1 shows it. If 16.7.16 rejects the plug-in, steps 5-7 park and 1-4 stand. Long GPU
sessions at `cpus=8` run without thermal mitigation: watch the gauge temperature from step 2.

## 13. Milestones

Roadmap milestones are M1-M6; the Stage 2 milestones in §3.6 are P1-P5. Calendars are working days
for one engineer from the start of this plan, with the GPU retry allowance. Every milestone's
acceptance includes updating README's "What does not work (yet)" list and PORTING-ENCHILADA.md.

| Milestone | Contents | Demo on the phone | Calendar |
| --- | --- | --- | --- |
| **M1 Correct basics** | §3.7 first week (I1, K0, K1, K2a-b, I2); §4 steps 0-3; §5 steps 1-5; §6 steps 1-4 | today's date within a minute on the lock screen; taps under the finger; swipe-up goes home; panel lit 10 min; a decoded log on the PC; the K0 ladder lines followed by the lock screen; README "What does not work (yet)" and PORTING-ENCHILADA.md updated | week 3 (day ~15) |
| **M2 Fast loop and first GPU frame** | I3 flash with the §7 step 3 tweaks; K2c-d, K3, G1, S-G, G2; §11 step 0 | two boots without a flash print different payload build strings; `sweet-tri` matches softpipe with `WAIT_FENCE -> 0` and no fault line; README "What does not work (yet)" and PORTING-ENCHILADA.md updated | week 6 (day ~30) |
| **M3 GPU-composited UI** | K4, G3, K6, G4 | lock screen and unlock drawn with `sweetgl: frame N via GPU` counting; Settings scroll ≥1.3× the CPU baseline; forced failure recovers in one relaunch; README "What does not work (yet)" and PORTING-ENCHILADA.md updated | weeks 10-12 (day ~50-60) |
| **M4 Daily image** | G5; §4 steps 4-6; §5 step 8; §7 steps 1-4; §11 steps 1-4; §12 steps 1-3 | `sweetgl=1` in the daily image after a week without a dead-man trip; no daemon above 1 exec per boot-minute; a time set in Settings survives a reboot; real battery % and a bolt that follows the cable; README "What does not work (yet)" and PORTING-ENCHILADA.md updated | week 16 (day ~80) |
| **M5 Metal for apps and wallpaper** | Stage 2 S-B, P1-P5; §7 step 5; §12 step 4 | the default wallpaper drawn with no PosterBoard/SBRendererService CRASH for 10 min; one Metal app 10 min without GPU loss; the slider toggles mute; README "What does not work (yet)" and PORTING-ENCHILADA.md updated | week 25 (day ~125) |
| **M6 First radio** | §8 steps 1-7, step 8 as far as it goes; §12 step 5 | `sweetbt=test` shows an inquiry count; if step 8 lands, the Settings switch turns on and a scan lists devices; Settings > Sounds opens; README "What does not work (yet)" and PORTING-ENCHILADA.md updated | week 35 (day ~175) |

After M6 the modem (§10, ~30 days) and Wi-Fi (§9, 25-34 more) bring a joined network and Safari
over http near days 230-240, followed by haptics and the speaker. These are rough; every kill
criterion can move them, and the weekly review (§3.7 item 5) re-plans against them.

## 14. Decision log

| Decision | Choice | Reason | Revisit when |
| --- | --- | --- | --- |
| Compositor route | GLES render server (Stage 1), Metal second | the only measured GPU-composited UI on iOS 16; reuses the ABI and Mesa 25.0.7; one GPU client (§3.9) | S-G, G2 or G4 kill (§3.8) |
| Metal route A vs B | A (Gallium bgmtl) kept; B = Turnip, with B' (Chlorophyll's MIT `chl`) before metal2vulkan | A already loads on 16.7.16 through 0167; B is faster per draw elsewhere | P2: A above 50 µs/draw while `tu_smoke` is under 10 µs, or the P3 kill |
| Display on auto-lock | `sweetfb_stayon` (default off) for working sessions; the power key keeps 0079's off/on for daily use; fallback auto-lock "Never" | stay-on only fakes the off state to backboardd, acceptable for test sessions | stay-on leaves the panel black, or touch fails to wake backboardd |
| Clock source | RTC read once plus a host-calibrated offset; file after the root mounts | cheap, read-only; the modem would only mirror the RTC | §4 step 0 fails |
| Wi-Fi kernel vs userland | kernel first for modem, services, WLFW and radio, with the `/dev/wlan` split for a later move | kernel boots iterate in seconds; userland iterations cost flashes until loader and recovery work; hackios shows an in-kernel LinuxKPI driver works (ath11k) | D1 (b) becomes cheap, or ath10k-on-LinuxKPI wins at §9 step 5 |
| Bluetooth before the modem | yes | no modem, remoteproc, QRTR or rmtfs needed | — |
| Patch numbering | 08xx pending-upstream (0173 included), 09xx board-only | no collisions with fajita's next numbers | fajita assigns numbers |
| Out of scope | telephony (SIM, calls, data, CommCenter, IPA, GNSS); camera (blockers recorded, §12 step 8); Apple security (AMFI, sandbox, code signing stay permissive; an allow-list is not security); CPU frequency scaling, thermal mitigation, system sleep (parked; ABL's clocks are kept) | security needs Apple-signed artefacts; the camera needs a CAMSS/CCI driver; telephony is its own project on top of §10; power management waits until the GPU and radios work | security never; camera if a CAMSS/CCI driver appears; thermal if long GPU sessions at `cpus=8` overheat |

## Appendix A: borrowed sources

| Project | What | Licence | How used |
| --- | --- | --- | --- |
| `edi194/ios-fajita` (base) | the kernel series, shim, tools, loader design | no LICENSE file | merged; generic patches offered back |
| `dipa-studio/ios-sweet` | the original port, boot-arg table format | MIT | through fajita |
| `awa-xaga/ios-enchilada` | 0084 stay-on, 0085 swipe test, 0087 clamps, `validate-repo.py`, WDT pet (only if a ~150 s reset appears) | no LICENSE file | ideas, re-implemented |
| oosexgang/hackios-xnu-kernel | `inject.c`, `eagl.c`, `mkeagl.py`, the 20F66 macro-context table, `mk-mesa.sh` and patches, `hakios.drm.c`, audio plug-in, `hakios.apple80211.c`, `lx_80211`/`lx_wpa` | userland MIT, kernel APSL-2.0 | userland ported; kernel code only with its notice |
| b1ackm4x/hackios-xnu-kernel `LEMONADE-BLUETOOTH.md` | QCA UART transport design | to be checked | design reference |
| oosexgang/hakios-metal | Metal command model, PM4 writer, probe | MIT | Stage 2 probe |
| ry-diffusion/Chlorophyll | bgmtl, gates, probes, `turnip-ios.patch`, `chl`, `docs/FIXES.md` | MIT (keep `NOTICE.md`); `test/` unverified | Stage 2 |
| ry-diffusion/Bergamota | `gpu/freedreno-sweet/sweet_drm.c`, `ca_server_hook.m`, user client behind 0158 | unverified | verify before publishing derived work |
| WuuuWeiii/ios-sweet-ci (Mi MIX 2S) | `eagl-bergamota` + `sweet_drm.c` for SweetAdreno630 | unverified | reference only |
| NWylynko/ios-flame | `0099-flame-rtc.patch`, `flame-rtc.py` arithmetic, `phone/wifi/*`, 0089/0090/0094/0123 | MIT | RTC copied with attribution; Wi-Fi/modem port base |
| UniXNU/UniXNU | Turnip + metal2vulkan front ends | MIT front ends | route B reference |
| lin72h/metal2vulkan | Metal on Vulkan | GPL-2.0+/LGPL-3.0+ | last fallback, fetched by script, own dylib |
| MakrSas/ios-topaz | 0085 stay-on, 0091 gauge pattern, modem layout, 0128 busy-hold removal | none seen | specification only |
| Mesa 25.0.7 / 26.2.5 | OSMesa, freedreno, ir3, Turnip | MIT | cross-built, pinned |
| Linux (msm/a6xx, rtc-pm8xxx, hci_qca/btqca, geni serial, gcc/pinctrl-sdm845, q6v5_mss, scm, smem/smp2p/glink, ath10k, qcom_smbx, bq27xxx, sdm845 DTS, qrtr) | register maps, sequences, ids | GPL-2.0 (ath10k ISC) | facts only |
| andersson rmtfs, pd-mapper, tqftpserv | server behaviour | BSD-3, to be confirmed | reference |
| postmarketOS, sdm845-mainline (`firmware-oneplus-sdm845`, `qcom-spmi-haptics`) | package facts, swclock-offset idea, firmware, haptics parameters | per package; firmware proprietary | facts; firmware local only |
| linux-firmware (`qca/`, `ath10k/WCN3990`) | fallback rampatch, `board-2.bin`, `firmware-5.bin` | WHENCE | local fallback inputs |

This repository has no LICENSE file yet. Settle that, and every "unverified" row, before anything
derived from those sources is published.

## Appendix B: facts still to measure on the phone

All read-only. Boots are agreed at their step; Android in slot b is not booted.

| Fact | Section | Command or log line |
| --- | --- | --- |
| Raw touch range (2280 or 2160) | §5 step 1 | `SWEET TS: raw max x=.. y=..` after four edge swipes; F12 register log or `getevent -lp` under a recovery |
| H1 vs H2 for edge gestures | §5 steps 2, 4 | ` edge` on a bottom swipe; home gesture at `sweetfb_offy=156` |
| Notch, corners, home-indicator rows | §5 step 4 | photos at offy 0/78/156 |
| Stepped display-off fade | §5 step 8 | video of one off/on cycle |
| Recovery with root adb that leaves `userdata` alone | §6 step 1 | `adb shell id`; `adb shell readlink /dev/block/by-name/userdata` |
| Does `fastboot boot` consume retry counters | any boot | `fastboot getvar slot-retry-count:a` before and after |
| ABL size limit for `fastboot boot` | §3 K1 | the padded boot's outcome |
| TrustZone accepts this unit's zap | §3 K0 | `zap authenticated and started (PAS 13` |
| 0172 with a large arena; pages below `gPhysBase` | §3 K3 | `1024 KiB with a kernel alias`; the VM diagnostics line |
| `SURFACE_BO` on CoreAnimation surfaces | §3 K4 | the pattern and printed physical addresses |
| CA instantiates `AppleCLCDDisplay` for our IOMFB | §3.5 S-G (2), G4 | the first G4 boot: the hooked display slots are reached |
| CPU baseline fps; arena demand under CA | §3 I2, G4 | the present counter; the per-second high-water line |
| PPID 0x060 has an APID | §4 step 1 | `SWEET RTC: PM8998 <N> s ctrl 0x..`, no `SPMI timeout` |
| `sweetfb_noconsole=1` hides `bsd_init` lines | §4 step 1 | the `SWEET RTC` line with and without it |
| `timed`/`settimeofday`; saved-time restore; picker range; time zone | §4 steps 0, 5 | observation in Settings and on the lock screen |
| The real `IORTC` wait | §4 step 2 | video from `fastboot boot` to the lock screen |
| DumpPanic runs every boot, before backboardd | §6 step 7 | order of `exec` lines (0042) |
| Crash-looping daemons and reasons; jetsam visibility; activation sheet | §7 steps 1-2 | `CRASH`, `|name|` lines, per-minute counts, observation |
| launchd loads a new job | §7 step 3 | `org.sweet.hello` output |
| Stay-on: touch wakes backboardd, swaps continue | §5 step 3 | `display off ignored (sweetfb_stayon)` and touch response |
| `/vendor/bt_firmware` contents, TLV `download_mode` | §8 step 1 | listing and SHA-256 under a recovery |
| Which binary opens the BT transport; exit reason | §8 step 2 | the fake controller's dump |
| QUPV3 version, DFS on wrap0_s6, FIFO mode; PM8998 GPIO3 | §8 step 3, §9 step 2 | `sweetbt=probe` output |
| Sequential RPMh votes; 1304 mV on L17A | §8 step 5 | three completed AMC votes |
| Firmware files, `.jsn` domains, BDF name | §9 step 1, §10 S0 | `modem_b` listing under a recovery |
| apps_smmu stream 0x40; SMEM item 435 across warm boots | §9 step 2, §10 S1 | the `SWEET MSS:` block |
| Hypervisor accepts `assign_mem` | §10 S2 | `assign rmtfs status 0` |
| Baseband version vs the phone's EFS | §10 S0 | version string compared on the phone, no EFS bytes leave it |
| Modem without an IPA QMI server | §10 S5-S6 | item 421 crash reason |
| Cable detect, charger watchdog, slider pulls, gpio55/56 mux | §12 step 1 | `sweetbattprobe=1` dumps |
| Gauge type | §12 step 2 | which map gives VOLT 3000-4500 mV and DCAP ~3240 |
| Ringer-state delivery; HAL plug-in loading; `vdef` | §12 steps 4-5 | slider log boot; the test's route line |

Logs, photos and dumps from these measurements stay out of git; only aggregated, scrubbed values
go into PORTING-ENCHILADA.md.
