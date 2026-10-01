/* fovefx — minimal LADSPA pedalboard for the FoveAI input chain.
 * Self-contained: no ladspa.h needed. gcc -O2 -shared -fPIC -o fovefx.so fovefx.c -lm
 * Plugins: fove_gate (noise gate), fove_comp (compressor), fove_drive (soft saturator).
 */
#include <math.h>
#include <stdlib.h>

typedef float LADSPA_Data;
typedef unsigned long LADSPA_UniqueID;
typedef unsigned long LADSPA_PortCount;
typedef int LADSPA_PortDescriptor;
typedef int LADSPA_PortRangeHintDescriptor;
typedef int LADSPA_Properties;
typedef void *LADSPA_Handle;

#define PORT_INPUT   0x1
#define PORT_OUTPUT  0x2
#define PORT_CONTROL 0x4
#define PORT_AUDIO   0x8
#define PROP_REALTIME    0x4
#define PROP_HARD_RT     0x10
#define HINT_BOUNDED_BELOW 0x1
#define HINT_BOUNDED_ABOVE 0x2

typedef struct {
    LADSPA_PortRangeHintDescriptor HintDescriptor;
    LADSPA_Data LowerBound, UpperBound;
} LADSPA_PortRangeHint;

typedef struct {
    LADSPA_UniqueID UniqueID;
    const char *Label;
    LADSPA_Properties Properties;
    const char *Name;
    const char *Maker;
    const char *Copyright;
    LADSPA_PortCount PortCount;
    const LADSPA_PortDescriptor *PortDescriptors;
    const char *const *PortNames;
    const LADSPA_PortRangeHint *PortRangeHints;
    void *ImplementationData;
    LADSPA_Handle (*instantiate)(const void *, unsigned long);
    void (*connect_port)(LADSPA_Handle, unsigned long, LADSPA_Data *);
    void (*activate)(LADSPA_Handle);
    void (*run)(LADSPA_Handle, unsigned long);
    void (*run_adding)(LADSPA_Handle, unsigned long);
    void (*set_run_adding_gain)(LADSPA_Handle, LADSPA_Data);
    void (*deactivate)(LADSPA_Handle);
    void (*cleanup)(LADSPA_Handle);
} LADSPA_Descriptor;

static void *dsp_new(size_t sz, unsigned long rate) {
    void *p = calloc(1, sz);
    *(unsigned long *)p = rate;
    return p;
}
static void dsp_cleanup(LADSPA_Handle i) { free(i); }

/* ------------------------------------------------ gate ---- */
typedef struct { unsigned long rate; float env, g;
    LADSPA_Data *in, *out, *thr, *att, *rel, *range; } Gate;

static LADSPA_Handle gate_i(const LADSPA_Descriptor *d, unsigned long r) {
    return dsp_new(sizeof(Gate), r);
}
static void gate_c(LADSPA_Handle i, unsigned long p, LADSPA_Data *b) {
    Gate *s = i;
    LADSPA_Data **pp[] = { &s->in, &s->out, &s->thr, &s->att, &s->rel, &s->range };
    *pp[p] = b;
}
static void gate_r(LADSPA_Handle i, unsigned long n) {
    Gate *s = i;
    float thr = *s->thr, range = *s->range;
    float ac = 1.0f - expf(-1.0f / (s->rate * (*s->att * 0.001f + 0.0001f)));
    float rc = 1.0f - expf(-1.0f / (s->rate * (*s->rel * 0.001f + 0.0001f)));
    for (unsigned long k = 0; k < n; k++) {
        float x = fabsf(s->in[k]);
        s->env += (x > s->env ? ac : rc) * (x - s->env);
        float target = s->env >= thr ? 1.0f : range;
        s->g += rc * (target - s->g);
        s->out[k] = s->in[k] * s->g;
    }
}

/* -------------------------------------------- compressor ---- */
typedef struct { unsigned long rate; float env, g;
    LADSPA_Data *in, *out, *thr, *ratio, *att, *rel, *makeup; } Comp;

static LADSPA_Handle comp_i(const LADSPA_Descriptor *d, unsigned long r) {
    return dsp_new(sizeof(Comp), r);
}
static void comp_c(LADSPA_Handle i, unsigned long p, LADSPA_Data *b) {
    Comp *s = i;
    LADSPA_Data **pp[] = { &s->in, &s->out, &s->thr, &s->ratio, &s->att, &s->rel, &s->makeup };
    *pp[p] = b;
}
static void comp_r(LADSPA_Handle i, unsigned long n) {
    Comp *s = i;
    float thr = *s->thr, inv = 1.0f / (*s->ratio > 1.f ? *s->ratio : 1.f);
    float mk = powf(10.f, *s->makeup / 20.f);
    float ac = 1.0f - expf(-1.0f / (s->rate * (*s->att * 0.001f + 0.0001f)));
    float rc = 1.0f - expf(-1.0f / (s->rate * (*s->rel * 0.001f + 0.0001f)));
    for (unsigned long k = 0; k < n; k++) {
        float x = fabsf(s->in[k]);
        s->env += (x > s->env ? ac : rc) * (x - s->env);
        float l = 20.f * log10f(s->env + 1e-9f);
        float over = l - thr;
        float gr = over > 0.f ? over * (1.f - inv) : 0.f;
        float target = powf(10.f, -gr / 20.f) * mk;
        s->g += (target < s->g ? ac : rc) * (target - s->g);
        s->out[k] = s->in[k] * s->g;
    }
}

/* --------------------------------------------- saturator ---- */
typedef struct { unsigned long rate;
    LADSPA_Data *in, *out, *drive, *mix; } Drive;

static LADSPA_Handle drive_i(const LADSPA_Descriptor *d, unsigned long r) {
    return dsp_new(sizeof(Drive), r);
}
static void drive_c(LADSPA_Handle i, unsigned long p, LADSPA_Data *b) {
    Drive *s = i;
    LADSPA_Data **pp[] = { &s->in, &s->out, &s->drive, &s->mix };
    *pp[p] = b;
}
static void drive_r(LADSPA_Handle i, unsigned long n) {
    Drive *s = i;
    float dr = *s->drive, mix = *s->mix;
    float comp = 1.0f / sqrtf(dr);
    for (unsigned long k = 0; k < n; k++) {
        float x = s->in[k];
        float wet = tanhf(x * dr) * comp;
        s->out[k] = x * (1.f - mix) + wet * mix;
    }
}

/* ---------------------------------------- descriptor glue ---- */
#define A_IN  (PORT_INPUT | PORT_AUDIO)
#define A_OUT (PORT_OUTPUT | PORT_AUDIO)
#define C_IN  (PORT_INPUT | PORT_CONTROL)
#define BND(lo, hi) { HINT_BOUNDED_BELOW | HINT_BOUNDED_ABOVE, lo, hi }
#define NORM { 0, 0.f, 0.f }

static const LADSPA_Descriptor descs[] = {
    { 9021, "fove_gate", PROP_REALTIME | PROP_HARD_RT, "Fove Noise Gate",
      "FoveAI", "MIT", 6,
      (const LADSPA_PortDescriptor[]){ A_IN, A_OUT, C_IN, C_IN, C_IN, C_IN },
      (const char *const[]){ "Input", "Output", "Threshold", "Attack", "Release", "Range" },
      (const LADSPA_PortRangeHint[]){ NORM, NORM, BND(0.0009f, 1.f), BND(1.f, 500.f), BND(10.f, 2000.f), BND(0.f, 1.f) },
      NULL, gate_i, gate_c, NULL, gate_r, NULL, NULL, NULL, dsp_cleanup },
    { 9022, "fove_comp", PROP_REALTIME | PROP_HARD_RT, "Fove Compressor",
      "FoveAI", "MIT", 7,
      (const LADSPA_PortDescriptor[]){ A_IN, A_OUT, C_IN, C_IN, C_IN, C_IN, C_IN },
      (const char *const[]){ "Input", "Output", "Threshold", "Ratio", "Attack", "Release", "Makeup" },
      (const LADSPA_PortRangeHint[]){ NORM, NORM, BND(-60.f, 0.f), BND(1.f, 20.f), BND(1.f, 500.f), BND(10.f, 2000.f), BND(0.f, 24.f) },
      NULL, comp_i, comp_c, NULL, comp_r, NULL, NULL, NULL, dsp_cleanup },
    { 9023, "fove_drive", PROP_REALTIME | PROP_HARD_RT, "Fove Drive",
      "FoveAI", "MIT", 4,
      (const LADSPA_PortDescriptor[]){ A_IN, A_OUT, C_IN, C_IN },
      (const char *const[]){ "Input", "Output", "Drive", "Mix" },
      (const LADSPA_PortRangeHint[]){ NORM, NORM, BND(1.f, 10.f), BND(0.f, 1.f) },
      NULL, drive_i, drive_c, NULL, drive_r, NULL, NULL, NULL, dsp_cleanup },
};

const LADSPA_Descriptor *ladspa_descriptor(unsigned long idx) {
    return idx < 3 ? &descs[idx] : NULL;
}
