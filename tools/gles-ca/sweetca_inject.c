/*
 * libsweetca.dylib: CoreAnimation's OpenGL ES render server on the GPU, inside backboardd.
 *
 * backboardd loads this library (a weak LC_LOAD_WEAK_DYLIB added by tools/macho-add-dylib.py).
 * When the kernel has SweetAdreno630 up and the boot-args do not say gl=0, it loads
 * /usr/local/lib/libsweetca.gl.dylib -- hackios' eagl.c over Mesa OSMesa (freedreno), whose
 * constructor gives EAGLContext an implementation -- before CoreAnimation makes its renderer.
 * The window server then gets an OpenGL ES renderer instead of falling back to its software one.
 *
 * After hackios' userland/src/inject.c (MIT, the HakiOS authors), cut down to the render server
 * and moved to iOS 16.7.16 (20H392): the vtable addresses and slots are in
 * docs/gles-route-20H392.md. Every slot is checked against the function expected there before it
 * is replaced; on a mismatch the slot is left alone and the line says so.
 *
 * Log lines go to stderr, which launchd points at /dev/null; the kernel's sweetnull hook (patch
 * 0048) prints them as "|backboardd| ...".
 */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <dlfcn.h>
#include <mach/mach.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/sysctl.h>
#include <sys/ucontext.h>
#include <unistd.h>

#include "hakios.gl.h"

extern const void *_dyld_get_shared_cache_range(size_t *length);

#define CACHE_BASE      0x180000000UL
#define SWEETCA_GL      "/usr/local/lib/libsweetca.gl.dylib"
#define GPU_SERVICE     "SweetAdreno630"

/* iOS 16.7.16 (20H392), iPhone10,3: unslid; slot = vtable + 0x10 + offset */
#define VT_APPLE_CLCD_DISPLAY   0x1d5b38788UL
#define VT_EAGL_SERVER          0x1d5b39ed0UL
#define VT_GLES_CONTEXT         0x1d5b2f6e8UL
#define VSLOT(vtable, offset)   ((vtable) + 0x10 + (offset))

static uintptr_t slide;
static char boot_args[1024];

static void
say(const char *format, ...)
{
	char line[256];
	va_list ap;
	int n;

	va_start(ap, format);
	n = vsnprintf(line, sizeof(line), format, ap);
	va_end(ap);
	if (n > (int)sizeof(line) - 1) {
		n = sizeof(line) - 1;
	}
	write(2, line, (size_t)n);
}

static int
boot_arg(const char *what)
{
	const char *at = boot_args;
	size_t n = strlen(what);

	while ((at = strstr(at, what)) != NULL) {
		if ((at == boot_args || at[-1] == ' ') && (at[n] == ' ' || at[n] == 0)) {
			return 1;
		}
		at += n;
	}
	return 0;
}

static void *
replace_virtual(const char *what, uintptr_t slot, uintptr_t expected, void *replacement)
{
	uintptr_t *entry = (uintptr_t *)(slot + slide);
	vm_address_t page = (vm_address_t)entry & ~(vm_address_t)(vm_page_size - 1);
	void *original;

	if (*entry != expected + slide) {
		say("sweetca: %s: found %#lx, expected %#lx; left alone\n", what, *entry - slide, expected);
		return NULL;
	}
	if (vm_protect(mach_task_self(), page, vm_page_size, FALSE, VM_PROT_READ | VM_PROT_WRITE | VM_PROT_COPY) !=
	    KERN_SUCCESS) {
		say("sweetca: %s: the table cannot be made writable\n", what);
		return NULL;
	}
	original = (void *)*entry;
	*entry = (uintptr_t)replacement;
	vm_protect(mach_task_self(), page, vm_page_size, FALSE, VM_PROT_READ);
	return original;
}

/* ---- the window server: what it does with its display and renderer (log only) ---- */

static int (*orig_is_ready)(void *display);
static uintptr_t (*orig_begin_update)(void *display, void *update);
static uintptr_t (*orig_finish_update)(void *display, void *update, unsigned flags);
static void *(*orig_renderer)(void *server);
static uintptr_t (*orig_render_update)(void *server, void *update, unsigned *flags);
static unsigned calls_begin, calls_finish, calls_render;

static int
my_is_ready(void *display)
{
	static int last = -1;
	int ready = orig_is_ready(display);

	if (ready != last) {
		say("sweetca: display is_ready -> %d\n", ready);
		last = ready;
	}
	return ready;
}

static uintptr_t
my_begin_update(void *display, void *update)
{
	uintptr_t r = orig_begin_update(display, update);

	if (calls_begin++ < 4) {
		say("sweetca: begin_update -> %#lx\n", r);
	}
	return r;
}

static uintptr_t
my_finish_update(void *display, void *update, unsigned flags)
{
	uintptr_t r = orig_finish_update(display, update, flags);

	if (calls_finish++ < 4) {
		say("sweetca: finish_update(%#x) -> %#lx\n", flags, r);
	}
	return r;
}

/* While there is no renderer the server tries to make one every frame; once is enough. */
static void *
my_renderer(void *server)
{
	static int failed, said;
	void *renderer;

	if (failed) {
		return NULL;
	}
	renderer = orig_renderer(server);
	if (renderer == NULL) {
		failed = 1;
		say("sweetca: no accelerated renderer; the software one draws\n");
	} else if (!said) {
		said = 1;
		say("sweetca: the window server has an OpenGL ES renderer (%p)\n", renderer);
	}
	return renderer;
}

static uintptr_t
my_render_update(void *server, void *update, unsigned *flags)
{
	uintptr_t r = orig_render_update(server, update, flags);

	if (calls_render++ < 4) {
		say("sweetca: render_update -> %#lx (flags %#x)\n", r, flags ? *flags : 0);
	}
	return r;
}

/* ---- CoreAnimation's OpenGL ES context: which of its ninety functions it lacks ---- */

static void (*gl_function_refused)(unsigned function);
static void (*gl_function_values)(void *context, unsigned function, unsigned index, size_t components, size_t count,
    const float *values);
static int (*orig_function_supported)(void *context);
static void (*orig_function_uniform)(void *context, unsigned index, size_t components, size_t count,
    const float *values);

static int
my_function_supported(void *context)
{
	static const char names[] = HAKIOS_CA_FUNCTIONS;
	static uint8_t said[256];
	int supported = orig_function_supported(context);
	uint8_t function = *(*(uint8_t **)((char *)context + 0x10) + 0x10);

	if (!supported && gl_function_refused != NULL) {
		gl_function_refused(function);
	}
	if (!supported && !said[function]) {
		said[function] = 1;
		say("sweetca: CoreAnimation's GLES renderer has no function %u (\"%.3s\")\n", function,
		    function < 90 ? names + 4 * function : "?");
	}
	return supported;
}

/* eagl.c draws some of the functions CoreAnimation has no shader for with programs of its own,
   and needs their numbers for that */
static void
my_function_uniform(void *context, unsigned index, size_t components, size_t count, const float *values)
{
	uint8_t function = *(*(uint8_t **)((char *)context + 0x10) + 0x10);

	if (gl_function_values != NULL) {
		gl_function_values(context, function, index, components, count, values);
	}
	orig_function_uniform(context, index, components, count, values);
}

/* ---- a crash of the window server becomes one line instead of a silent restart ---- */

static void
say_the_fault(int number, siginfo_t *info, void *context_in)
{
	ucontext_t *context = context_in;
	uintptr_t pc = 0, lr = 0, fp = 0;
	char frames[8 * 20 + 1] = "";
	size_t used = 0;

	if (context != NULL && context->uc_mcontext != NULL) {
		pc = (uintptr_t)context->uc_mcontext->__ss.__pc;
		lr = (uintptr_t)context->uc_mcontext->__ss.__lr;
		fp = (uintptr_t)context->uc_mcontext->__ss.__fp;
	}
	for (unsigned i = 0; i < 8 && fp != 0 && (fp & 7) == 0; i++) {
		uintptr_t next = ((uintptr_t *)fp)[0], ret = ((uintptr_t *)fp)[1];

		if (ret == 0) {
			break;
		}
		used += (size_t)snprintf(frames + used, sizeof(frames) - used, " %#lx", ret - slide);
		fp = next > fp ? next : 0;
	}
	say("sweetca: signal %d at %p, pc %#lx, lr %#lx, from%s (unslid)\n", number, info ? info->si_addr : NULL,
	    pc - slide, lr - slide, frames);
	signal(number, SIG_DFL);
	raise(number);
}

static void
watch_for_faults(void)
{
	struct sigaction action;

	memset(&action, 0, sizeof(action));
	action.sa_sigaction = say_the_fault;
	action.sa_flags = SA_SIGINFO | SA_RESETHAND;
	sigaction(SIGSEGV, &action, NULL);
	sigaction(SIGBUS, &action, NULL);
	sigaction(SIGABRT, &action, NULL);
	sigaction(SIGILL, &action, NULL);
	sigaction(SIGTRAP, &action, NULL);
}

static int
load_gl(void)
{
	io_service_t gpu;
	void *library;

	if (boot_arg("gl=0")) {
		say("sweetca: gl=0: CoreAnimation keeps its software renderer\n");
		return 0;
	}
	if (access(SWEETCA_GL, R_OK) != 0) {
		say("sweetca: %s is not installed\n", SWEETCA_GL);
		return 0;
	}
	gpu = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching(GPU_SERVICE));
	if (gpu == 0 && !boot_arg("gl=1")) {
		say("sweetca: no %s: CoreAnimation keeps its software renderer (gl=1 forces softpipe)\n", GPU_SERVICE);
		return 0;
	}
	if (gpu != 0) {
		IOObjectRelease(gpu);
	}
	if ((library = dlopen(SWEETCA_GL, RTLD_NOW)) == NULL) {
		say("sweetca: %s\n", dlerror());
		return 0;
	}
	gl_function_values = (void (*)(void *, unsigned, unsigned, size_t, size_t, const float *))dlsym(library,
	    "hakios_gl_function_values");
	gl_function_refused = (void (*)(unsigned))dlsym(library, "hakios_gl_function_refused");
	say("sweetca: OpenGL ES library loaded (%s)\n", SWEETCA_GL);
	return 1;
}

__attribute__((constructor))
static void
sweetca_init(void)
{
	const char *name = getprogname();
	size_t length = 0, size = sizeof(boot_args) - 1;
	const void *cache = _dyld_get_shared_cache_range(&length);
	int gl;

	if (name == NULL || strcmp(name, "backboardd") != 0 || cache == NULL) {
		return;
	}
	slide = (uintptr_t)cache - CACHE_BASE;
	(void)sysctlbyname("kern.bootargs", boot_args, &size, NULL, 0);
	gl = load_gl();

	orig_is_ready = replace_virtual("is_ready", VSLOT(VT_APPLE_CLCD_DISPLAY, 0x0b0), 0x1882f9318UL, my_is_ready);
	orig_begin_update = replace_virtual("begin_update", VSLOT(VT_APPLE_CLCD_DISPLAY, 0x178), 0x1882e6798UL,
	    my_begin_update);
	orig_finish_update = replace_virtual("finish_update", VSLOT(VT_APPLE_CLCD_DISPLAY, 0x180), 0x1882d0f88UL,
	    my_finish_update);
	orig_renderer = replace_virtual("renderer", VSLOT(VT_EAGL_SERVER, 0x1a0), 0x1882eaf3cUL, my_renderer);
	orig_render_update = replace_virtual("render_update", VSLOT(VT_EAGL_SERVER, 0x178), 0x1883601dcUL,
	    my_render_update);
	if (gl) {
		orig_function_supported = replace_virtual("function_supported", VSLOT(VT_GLES_CONTEXT, 0x378),
		    0x1884b2164UL, my_function_supported);
		if (gl_function_values != NULL) {
			orig_function_uniform = replace_virtual("function_uniform", VSLOT(VT_GLES_CONTEXT, 0x388),
			    0x1884b21acUL, my_function_uniform);
		}
		watch_for_faults();
	}
	say("sweetca: window server hooks %s, OpenGL ES %s\n",
	    orig_is_ready && orig_begin_update && orig_finish_update && orig_renderer && orig_render_update ?
	    "installed" : "INCOMPLETE", gl ? "on" : "off");
}
