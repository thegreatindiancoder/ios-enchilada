/*
 * The OpenGL ES library behind hackios' userland/src/eagl.c on this port: Mesa's OSMesa as
 * tools/build-osmesa-ios.sh builds it (Bergamota's Mesa patch: Gallium freedreno over the libdrm
 * stand-in and SweetAdreno630, softpipe otherwise).
 *
 * eagl.c asks for the functions declared in hackios' userland/src/hakios.gl.h; this file is the
 * port's implementation of them, after hackios' gl_osmesa.c (MIT, the HakiOS authors). Two things
 * differ from theirs:
 *  - the OpenGL ES profile of OSMesa is Bergamota's (attribute value 0x36), not hackios' (0x38);
 *  - an IOSurface becomes a texture through Bergamota's OSMesaSweetWrapTexture() instead of
 *    glEGLImageTargetTexture2DOES with the surface's ID.
 * Boot-arg glzc=0 turns the zero-copy textures off (eagl.c then fills textures from the surfaces
 * and reads them back with OpenGL ES calls).
 */
#include <dlfcn.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/sysctl.h>
#include <CoreFoundation/CoreFoundation.h>
#include <IOSurface/IOSurfaceRef.h>

#include "hakios.gl.h"

/* GL/osmesa.h of Mesa, and the profile value of Bergamota's patch */
#define OSMESA_RGBA                     0x1908
#define OSMESA_FORMAT                   0x22
#define OSMESA_DEPTH_BITS               0x30
#define OSMESA_STENCIL_BITS             0x31
#define OSMESA_PROFILE                  0x33
#define OSMESA_CONTEXT_MAJOR_VERSION    0x36
#define OSMESA_CONTEXT_MINOR_VERSION    0x37
#define OSMESA_ES_PROFILE_BERGAMOTA     0x36
#define GL_UNSIGNED_BYTE                0x1401
#define GL_RENDERER                     0x1f01
#define GL_TEXTURE_BINDING_2D           0x8069

typedef struct osmesa_context *OSMesaContext;
extern OSMesaContext OSMesaCreateContextAttribs(const int *attributes, OSMesaContext share);
extern unsigned char OSMesaMakeCurrent(OSMesaContext context, void *buffer, unsigned type, int width, int height);
extern void OSMesaDestroyContext(OSMesaContext context);
extern const unsigned char *glGetString(unsigned name);
extern void glGetIntegerv(unsigned name, int *values);

#define WINDOW  16                      /* nothing is drawn into OSMesa's own "window" */

struct hakios_gl {
	OSMesaContext context;
	unsigned char window[WINDOW * WINDOW * 4];
};

struct hakios_gl *
hakios_gl_create(int version)
{
	const int attributes[] = {
		OSMESA_FORMAT, OSMESA_RGBA, OSMESA_DEPTH_BITS, 24, OSMESA_STENCIL_BITS, 8,
		OSMESA_PROFILE, OSMESA_ES_PROFILE_BERGAMOTA, OSMESA_CONTEXT_MAJOR_VERSION, version,
		OSMESA_CONTEXT_MINOR_VERSION, 0, 0
	};
	struct hakios_gl *gl = calloc(1, sizeof(*gl));

	if (gl != NULL && (gl->context = OSMesaCreateContextAttribs(attributes, NULL)) == NULL) {
		free(gl);
		gl = NULL;
	}
	return gl;
}

int
hakios_gl_make_current(struct hakios_gl *gl)
{
	if (gl == NULL) {
		return OSMesaMakeCurrent(NULL, NULL, 0, 0, 0);
	}
	return OSMesaMakeCurrent(gl->context, gl->window, GL_UNSIGNED_BYTE, WINDOW, WINDOW);
}

void
hakios_gl_destroy(struct hakios_gl *gl)
{
	OSMesaDestroyContext(gl->context);
	free(gl);
}

const char *
hakios_gl_library(void)
{
	static char name[128];
	const char *renderer;

	if (name[0] == 0) {
		renderer = (const char *)glGetString(GL_RENDERER);
		snprintf(name, sizeof(name), "Mesa OSMesa (%s)", renderer != NULL ? renderer : "no context yet");
	}
	return name;
}

static int
zero_copy_allowed(void)
{
	char arguments[1024] = "";
	size_t size = sizeof(arguments) - 1;

	if (sysctlbyname("kern.bootargs", arguments, &size, NULL, 0) != 0) {
		return 1;
	}
	return strstr(arguments, "glzc=0") == NULL;
}

int
hakios_gl_surface_texture(struct hakios_gl *gl, uint32_t surface)
{
	static int (*active)(void);
	static int (*wrap)(unsigned name, uint32_t surface, int kind, unsigned w, unsigned h);
	static int asked, usable;
	IOSurfaceRef ref;
	int kind = 0, name = 0, done;

	(void)gl;
	if (!asked) {
		asked = 1;
		active = (int (*)(void))dlsym(RTLD_DEFAULT, "OSMesaSweetActive");
		wrap = (int (*)(unsigned, uint32_t, int, unsigned, unsigned))dlsym(RTLD_DEFAULT, "OSMesaSweetWrapTexture");
		usable = active != NULL && wrap != NULL && active() && zero_copy_allowed();
	}
	if (!usable || (ref = IOSurfaceLookup(surface)) == NULL) {
		return 0;
	}
	switch (IOSurfaceGetPixelFormat(ref)) {
	case 0x42475241: kind = 5; break;       /* 'BGRA' */
	case 0x52474241: kind = 4; break;       /* 'RGBA' */
	default: break;
	}
	glGetIntegerv(GL_TEXTURE_BINDING_2D, &name);
	done = kind != 0 && name != 0 &&
	    wrap((unsigned)name, surface, kind, (unsigned)IOSurfaceGetWidth(ref), (unsigned)IOSurfaceGetHeight(ref));
	CFRelease(ref);
	return done;
}
