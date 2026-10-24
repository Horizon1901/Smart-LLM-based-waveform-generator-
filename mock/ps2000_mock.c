/*******************************************************************************
 * MOCK ps2000 driver implementation  --  PicoWave Assistant
 *
 * Implements the subset of the ps2000 API declared in mock/libps2000/ps2000.h,
 * returning plausible synthetic data so that generated programs can be compiled
 * AND executed offline with no PicoScope attached.
 *
 * Synthetic model:
 *   - open_unit() reports a virtual PicoScope 2205A (variant "2205A"), so the
 *     generated code exercises the dual-channel + siggen + AWG paths.
 *   - Channel A returns a 1 kHz-ish sine, Channel B a slower cosine, both in
 *     ADC counts (full scale +/-32767), so adc_to_mv() produces sensible mV.
 *   - siggen / AWG calls just validate arguments and print what a real device
 *     would have been asked to output.
 *
 * NONE of this ships to the real target: the --real build links the genuine
 * libps2000 instead of this file.
 ******************************************************************************/
#include "libps2000/ps2000.h"
#include <stdio.h>
#include <math.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* Total block-mode sample buffer, shared across enabled channels -- models the
 * real 2204A/2205A so over-sized captures are rejected OFFLINE, not just on
 * hardware. Adjust if your unit differs. */
#define MOCK_DEVICE_BUFFER 8064

static int   g_open        = 0;
static int   g_block_calls = 0;
static int   g_ready_polls = 0;
static int   g_enabled[PS2000_MAX_CHANNELS] = {0, 0, 0, 0};

/* Enabled channels, floored at 1 so we never divide by zero. */
static int enabled_count(void)
{
    int c = 0, k;
    for (k = 0; k < PS2000_MAX_CHANNELS; k++)
        c += g_enabled[k] ? 1 : 0;
    return c < 1 ? 1 : c;
}

/* Per-channel block limit for the current channel configuration. */
static int32_t max_block_samples(void)
{
    return (int32_t)(MOCK_DEVICE_BUFFER / enabled_count());
}

int16_t ps2000_open_unit(void)
{
    g_open = 1;
    fprintf(stderr, "[mock] ps2000_open_unit -> handle 1 (virtual PicoScope 2205A)\n");
    return 1; /* non-zero handle == success */
}

int16_t ps2000_close_unit(int16_t handle)
{
    (void)handle; g_open = 0;
    fprintf(stderr, "[mock] ps2000_close_unit\n");
    return 1;
}

int16_t ps2000_flash_led(int16_t handle) { (void)handle; return 1; }

int16_t ps2000_get_unit_info(int16_t handle, int8_t *string, int16_t len, int16_t line)
{
    const char *v;
    (void)handle;
    switch (line)
    {
        case 0: v = "MOCK 1.0";  break; /* driver version   */
        case 1: v = "2.0";       break; /* usb version      */
        case 2: v = "1";         break; /* hardware version */
        case 3: v = "2205A";     break; /* variant info     */
        case 4: v = "MOCK-0001"; break; /* serial           */
        case 5: v = "01Jan24";   break; /* cal date         */
        case 6: v = "0";         break; /* error code       */
        case 7: v = "mock";      break; /* kernel driver    */
        default: v = "";         break;
    }
    strncpy((char *)string, v, (size_t)len - 1);
    string[len - 1] = '\0';
    return (int16_t)strlen((char *)string);
}

int16_t ps2000_set_channel(int16_t handle, int16_t ch, int16_t en, int16_t dc, int16_t range)
{
    (void)handle;
    if (ch >= 0 && ch < PS2000_MAX_CHANNELS)
        g_enabled[ch] = en ? 1 : 0;
    fprintf(stderr, "[mock] set_channel ch=%d enabled=%d dc=%d range=%d\n", ch, en, dc, range);
    return 1;
}

int16_t ps2000_set_ets(int16_t handle, PS2000_ETS_MODE m, int16_t c, int16_t i)
{ (void)handle; (void)m; (void)c; (void)i; return 0; }

int16_t ps2000_set_trigger(int16_t handle, int16_t src, int16_t thr,
                           int16_t dir, int16_t delay, int16_t autotrig)
{
    (void)handle;
    fprintf(stderr, "[mock] set_trigger src=%d threshold_adc=%d dir=%d delay=%d auto_ms=%d\n",
            src, thr, dir, delay, autotrig);
    return 1;
}

int16_t ps2000_get_timebase(int16_t handle, int16_t timebase, int32_t n,
                            int32_t *interval, int16_t *units,
                            int16_t oversample, int32_t *max_samples)
{
    (void)handle; (void)n; (void)oversample;
    /* Reject out-of-range timebases like the real driver (return 0 == invalid). */
    if (timebase < 0 || timebase > PS2200_MAX_TIMEBASE)
        return 0;
    /* interval in ns roughly doubles per timebase index; units=3 == ns */
    if (interval)    *interval    = (int32_t)(1 << timebase);
    if (units)       *units       = 3;
    /* Max samples depends on how many channels are enabled (shared buffer). */
    if (max_samples) *max_samples = max_block_samples();
    return 1; /* valid timebase */
}

int32_t ps2000_run_block(int16_t handle, int32_t n, int16_t tb, int16_t ovs, int32_t *ind_ms)
{
    (void)handle; (void)ovs;
    /* Real driver refuses a block bigger than the per-config buffer (returns 0). */
    if (n > max_block_samples())
    {
        fprintf(stderr, "[mock] run_block REJECTED: %d samples > %d max for %d channel(s)\n",
                n, max_block_samples(), enabled_count());
        return 0;
    }
    g_block_calls++; g_ready_polls = 0;
    if (ind_ms) *ind_ms = 1;
    fprintf(stderr, "[mock] run_block samples=%d timebase=%d\n", n, tb);
    return 1;
}

int16_t ps2000_ready(int16_t handle)
{
    (void)handle;
    /* pretend the device needs a couple of polls before data is ready */
    return (++g_ready_polls >= 2) ? 1 : 0;
}

int16_t ps2000_stop(int16_t handle) { (void)handle; return 1; }

static void fill_synthetic(int16_t *buf, int32_t n, double freq_hz, double phase)
{
    int32_t i;
    if (!buf) return;
    for (i = 0; i < n; i++)
    {
        double t = (double)i / (double)n;           /* 0..1 over the block */
        double s = sin(2.0 * M_PI * freq_hz * t + phase);
        buf[i] = (int16_t)(s * 30000.0);            /* ADC counts, ~+/-full scale */
    }
}

int32_t ps2000_get_times_and_values(int16_t handle, int32_t *times,
                                    int16_t *a, int16_t *b, int16_t *c, int16_t *d,
                                    int16_t *overflow, int16_t units, int32_t n)
{
    int32_t i;
    (void)handle; (void)units;
    for (i = 0; i < n && times; i++) times[i] = i;   /* monotonically increasing */
    fill_synthetic(a, n, 3.0, 0.0);                  /* Channel A: 3 cycles */
    fill_synthetic(b, n, 1.0, M_PI / 2.0);           /* Channel B: 1 cycle, 90 deg */
    (void)c; (void)d;
    if (overflow) *overflow = 0;
    return n;
}

int32_t ps2000_get_values(int16_t handle, int16_t *a, int16_t *b, int16_t *c, int16_t *d,
                          int16_t *overflow, int32_t n)
{
    (void)handle;
    fill_synthetic(a, n, 3.0, 0.0);
    fill_synthetic(b, n, 1.0, M_PI / 2.0);
    (void)c; (void)d;
    if (overflow) *overflow = 0;
    return n;
}

int16_t ps2000_set_sig_gen_built_in(int16_t handle, int32_t offset, uint32_t pkToPk,
                                    PS2000_WAVE_TYPE wave, float f0, float f1,
                                    float inc, float dwell, PS2000_SWEEP_TYPE sw, uint32_t sweeps)
{
    (void)handle; (void)inc; (void)dwell; (void)sw; (void)sweeps;
    fprintf(stderr, "[mock] siggen built-in wave=%d f0=%.1fHz f1=%.1fHz pkToPk=%uuV offset=%duV\n",
            (int)wave, f0, f1, pkToPk, offset);
    return 1;
}

int16_t ps2000_set_sig_gen_arbitrary(int16_t handle, int32_t offset, uint32_t pkToPk,
                                     uint32_t d0, uint32_t d1, uint32_t dinc, uint32_t dwell,
                                     uint8_t *wf, int32_t wfSize, PS2000_SWEEP_TYPE sw, uint32_t sweeps)
{
    (void)handle; (void)d0; (void)d1; (void)dinc; (void)dwell; (void)sw; (void)sweeps;
    fprintf(stderr, "[mock] siggen ARB size=%d pkToPk=%uuV offset=%duV first=%d last=%d\n",
            wfSize, pkToPk, offset, wf ? wf[0] : -1, (wf && wfSize > 0) ? wf[wfSize - 1] : -1);
    return 1;
}
