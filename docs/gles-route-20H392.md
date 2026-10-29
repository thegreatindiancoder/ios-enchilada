# GPU-composited UI through CoreAnimation's GLES render server: iOS 16.7.16 (20H392) facts

The quickest demonstrated route to a GPU-drawn UI on iOS 16 does not need a Metal device:
hackios (`oosexgang/hackios-xnu-kernel`, iOS 16.5 20F66, Adreno 642L) injects a library into
`backboardd` that turns on CoreAnimation's own OpenGL ES render server
(`CA::WindowServer::EAGLServer` + `CA::OGL::GLESContext`) and backs `EAGLContext` with Mesa
(OSMesa, Gallium freedreno) over a libdrm stand-in that speaks the msm request numbers to an IOKit
user client, the same ABI shape as `SweetAdreno630` (patch 0158). Their measurement: Settings
scrolls at 56-58 fps against 28-35 fps with the software renderer. Bergamota repeated it on
iOS 18.7.8 with an Adreno 630 (branch `gpu-eagl`).

The injector patches C++ vtable slots at addresses of one iOS build and refuses to run on any
other. This file records what those addresses are in the build this port runs.

## The classes exist in 20H392

The RTTI names are present in the iPhone X 20H392 shared cache
(`/System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64*`):
`N2CA12WindowServer10EAGLServerE`, `N2CA3OGL11GLESContextE`,
`N2CA12WindowServer16AppleCLCDDisplayE`, and the EAGLContext selectors
`getMacroContextPrivate`, `texImageIOSurface…`, `attachImage:toCoreSurface:invertedRender:`.

## Vtables and slots (unslid addresses, slot = vtable + 0x10 + offset)

Found with `tools/dsc-vtables.py` from the cache's local symbols (`.symbols` file), every slot
checked by the mangled name of the function in it.

| Class | vtable 20H392 | Slot | Function | Target 20H392 | Slot in 20F66 |
| --- | --- | --- | --- | --- | --- |
| `CA::WindowServer::AppleCLCDDisplay` | `0x1d5b38788` | `0x0b0` | `IOMFBDisplay::is_ready` | `0x1882f9318` | same |
| | | `0x138` | `IOMFBDisplay::ignore_update_p` | `0x1882e9684` | same |
| | | `0x178` | `IOMFBDisplay::begin_update` | `0x1882e6798` | `0x170` |
| | | `0x180` | `IOMFBDisplay::finish_update` | `0x1882d0f88` | `0x178` |
| `CA::WindowServer::EAGLServer` | `0x1d5b39ed0` | `0x1a0` | `EAGLServer::renderer` | `0x1882eaf3c` | same |
| | | `0x178` | `EAGLServer::render_update` | `0x1883601dc` | same |
| `CA::OGL::GLESContext` | `0x1d5b2f6e8` | `0x378` | `GLContext::function_supported` | `0x1884b2164` | same |
| | | `0x388` | `GLContext::function_uniform` | `0x1884b21ac` | same |
| | | `0x060` | `Context::compile_shader` | `0x1884053fc` | same |

The display class gained a slot, `IOMFBDisplay::work_interval` at `0x170`, between 16.5 and
16.7.16, which moves `begin_update` and `finish_update` down by one entry. Every other hooked
slot is where 20F66 has it.

Not carried over: hackios also fills one entry of CoreAnimation's shader-source table
(20F66 `0x1d5b54790`, the single-pass blur "sb3"); their own notes record no visible effect, so a
first version leaves it out.

## The EAGL macro-context table is unchanged

Every exported `gl*` function of OpenGLES does
`mrs x8, tpidrro_el0; ldr x8, [x8, #240]; …; ldr xF, [x8, #N]; ldr x0, [x8, #32]; br/blr xF`:
the context comes from thread-local storage, the function from field `N`, and the first argument
from field `0x20`. hackios' `userland/src/eagl_slots.txt` (20F66) counts entries from that
`+0x20`. `tools/dsc-gles-slots.py` reads the same thing off the 20H392 cache and compares:
**all 457 names, same offsets, nothing moved or missing.** The hackios table can be used as is.

## Still to do for 20H392

- The libdrm stand-in for `SweetAdreno630` (Bergamota `gpu/freedreno-sweet/sweet_drm.c`, already
  built for this port by the 6T tree) and the IOSurface-to-BO import (`0x71 SURFACE_BO` here,
  `0x7e` in hackios).
- Mesa 25.0.7 OSMesa with hackios' `osmesa-es-profile` and `freedreno-darwin` changes, adapted to
  the libdrm stand-in.
