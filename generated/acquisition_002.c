/*******************************************************************************
 * GENERATED FILE -- DO NOT EDIT BY HAND
 * PicoWave Assistant :: built-in signal generator
 *
 * Generation id : 002
 * Generated at  : 2026-08-13T22:54:10
 * Voice command : "now generate a eight kilo hertz square wave at two one zero two five hertz"
 * Resolved intent (JSON):
 *  * {
 *   "action": "siggen",
 *   "params": {
 *     "siggen_wave": "square"
 *   },
 *   "raw_text": "now generate a eight kilo hertz square wave at two one zero two five hertz",
 *   "confidence": 0.9,
 *   "notes": "mock-rule-based"
 * }
 *
 * Assembled from the Pico Technology ps2000Con.c example (set_sig_gen), using
 * ps2000_set_sig_gen_built_in exactly as the manufacturer does.
 ******************************************************************************/
#include <stdio.h>

#ifdef WIN32
#include "windows.h"
#include "ps2000.h"
#define PREF4 _stdcall
#else
#include <unistd.h>
#include "libps2000/ps2000.h"
#define PREF4
#define Sleep(a) usleep(1000 * (a))
#endif

/* Open resilience (covers the first-open firmware re-enumeration window). */
#define OPEN_MAX_TRIES  20
#define OPEN_RETRY_MS   250

int main(void)
{
    int16_t handle = 0;
    int8_t  info[80];
    int     open_try;

    printf("== PicoWave signal generator 002 ==\n");

    /* Open, retrying across the firmware-load USB re-enumeration on first open. */
    for (open_try = 1; open_try <= OPEN_MAX_TRIES; open_try++)
    {
        handle = ps2000_open_unit();
        if (handle > 0)
            break;
        printf("Device not ready (attempt %d/%d), waiting for enumeration...\n",
               open_try, OPEN_MAX_TRIES);
        Sleep(OPEN_RETRY_MS);
    }
    if (handle <= 0)
    {
        printf("ERROR: unable to open PicoScope device\n");
        return 99;
    }
    ps2000_get_unit_info(handle, info, sizeof(info), 3);
    printf("Device variant: %s\n", (char *)info);

    /* Built-in generator (manufacturer: ps2000_set_sig_gen_built_in).
     *   offsetVoltage : microvolts
     *   pkToPk        : microvolts (peak-to-peak amplitude)
     *   waveType      : square
     *   start/stop f  : 1000 Hz (no sweep)
     */
    ps2000_set_sig_gen_built_in(handle,
                                0,          /* offset (uV) */
                                2000000,          /* pk-to-pk (uV) */
                                PS2000_SQUARE,          /* wave type */
                                (float)1000,   /* start frequency (Hz) */
                                (float)1000,   /* stop frequency (Hz)  */
                                0,                      /* increment */
                                0,                      /* dwell time */
                                PS2000_UPDOWN, 0);      /* sweep type, sweeps */

    printf("RESULT: generating square at 1000 Hz, "
           "2000000 uVpp, offset 0 uV\n");

    /* Hold the output on for the demo window, then release. */
    printf("Output active for 8000 ms...\n");
    Sleep(8000);

    ps2000_close_unit(handle);
    return 0;
}
