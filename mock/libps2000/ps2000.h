/*******************************************************************************
 * MOCK ps2000.h  --  PicoWave Assistant
 *
 * This is NOT the real Pico Technology header. It is a faithful *subset* of the
 * official <libps2000/ps2000.h> that declares exactly the enums, constants,
 * structs and function prototypes used by the manufacturer example and by the
 * code the assistant generates.
 *
 * Purpose: let the whole generate -> compile -> run pipeline work OFFLINE, on a
 * developer machine with no PicoScope attached (home development), then move
 * unchanged to a machine with the real PicoSDK installed (demo). Anything that
 * compiles against this mock also compiles against the real SDK, because the
 * signatures below match the manufacturer's usage 1:1.
 *
 * On a real target this file is NOT used: the compiler is pointed at
 * /opt/picoscope/include instead (see compiler/builder.py, --real mode).
 ******************************************************************************/
#ifndef PS2000_MOCK_H
#define PS2000_MOCK_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ---- limits -------------------------------------------------------------- */
#define PS2000_MAX_CHANNELS     4
#define PS2000_MAX_RANGES       12
#define PS2000_MAX_SIGGEN_FREQ  100000.f
#define PS2000_MIN_SIGGEN_FREQ  0.f

#define PS2104_MAX_TIMEBASE     19
#define PS2105_MAX_TIMEBASE     20
#define PS2200_MAX_TIMEBASE     23

/* ---- channels ------------------------------------------------------------ */
typedef enum enPS2000Channel
{
    PS2000_CHANNEL_A,
    PS2000_CHANNEL_B,
    PS2000_CHANNEL_C,
    PS2000_CHANNEL_D,
    PS2000_EXTERNAL,
    PS2000_MAX_CHANNELS_ENUM,
    PS2000_NONE = PS2000_MAX_CHANNELS_ENUM
} PS2000_CHANNEL;

/* ---- input ranges (index -> mV: 10,20,50,100,200,500,1k,2k,5k,10k,20k,50k) */
typedef enum enPS2000Range
{
    PS2000_10MV,
    PS2000_20MV,
    PS2000_50MV,
    PS2000_100MV,
    PS2000_200MV,
    PS2000_500MV,
    PS2000_1V,
    PS2000_2V,
    PS2000_5V,
    PS2000_10V,
    PS2000_20V,
    PS2000_50V
} PS2000_RANGE;

/* ---- trigger directions -------------------------------------------------- */
typedef enum enPS2000TriggerDirection
{
    PS2000_RISING,
    PS2000_FALLING,
    PS2000_MAX_DIRS
} PS2000_TDIR;

/* ---- ETS ----------------------------------------------------------------- */
typedef enum enPS2000EtsMode
{
    PS2000_ETS_OFF,
    PS2000_ETS_FAST,
    PS2000_ETS_SLOW,
    PS2000_ETS_MAX
} PS2000_ETS_MODE;

/* ---- signal generator ---------------------------------------------------- */
typedef enum enPS2000WaveType
{
    PS2000_SINE,
    PS2000_SQUARE,
    PS2000_TRIANGLE,
    PS2000_RAMPUP,
    PS2000_RAMPDOWN,
    PS2000_SINC,
    PS2000_GAUSSIAN,
    PS2000_HALF_SINE,
    PS2000_DC_VOLTAGE,
    PS2000_MAX_WAVE_TYPES
} PS2000_WAVE_TYPE;

typedef enum enPS2000SweepType
{
    PS2000_UP,
    PS2000_DOWN,
    PS2000_UPDOWN,
    PS2000_DOWNUP,
    PS2000_MAX_SWEEP_TYPES
} PS2000_SWEEP_TYPE;

/* ---- advanced-trigger types (declared so the manufacturer file parses) --- */
typedef enum enThresholdDirection
{
    PS2000_ABOVE,
    PS2000_BELOW,
    PS2000_ADV_RISING,
    PS2000_ADV_FALLING,
    PS2000_RISING_OR_FALLING,
    PS2000_INSIDE = PS2000_ABOVE,
    PS2000_OUTSIDE = PS2000_BELOW,
    PS2000_ENTER = PS2000_ADV_RISING,
    PS2000_EXIT = PS2000_ADV_FALLING,
    PS2000_ENTER_OR_EXIT = PS2000_RISING_OR_FALLING,
    PS2000_NONE_DIR
} PS2000_THRESHOLD_DIRECTION;

typedef enum enPulseWidthType
{
    PS2000_PW_TYPE_NONE,
    PS2000_PW_TYPE_LESS_THAN,
    PS2000_PW_TYPE_GREATER_THAN,
    PS2000_PW_TYPE_IN_RANGE,
    PS2000_PW_TYPE_OUT_OF_RANGE
} PS2000_PULSE_WIDTH_TYPE;

typedef enum enPS2000TriggerState
{
    PS2000_CONDITION_DONT_CARE,
    PS2000_CONDITION_TRUE,
    PS2000_CONDITION_FALSE,
    PS2000_CONDITION_MAX
} PS2000_TRIGGER_STATE;

typedef struct tPwqConditions
{
    PS2000_TRIGGER_STATE channelA, channelB, channelC, channelD, external;
} PS2000_PWQ_CONDITIONS;

typedef struct tTriggerConditions
{
    PS2000_TRIGGER_STATE channelA, channelB, channelC, channelD,
                         external, pulseWidthQualifier;
} PS2000_TRIGGER_CONDITIONS;

typedef enum enThresholdMode { PS2000_LEVEL, PS2000_WINDOW } PS2000_THRESHOLD_MODE;

typedef struct tTriggerChannelProperties
{
    int16_t thresholdMajor, thresholdMinor;
    uint16_t hysteresis;
    int16_t channel;
    PS2000_THRESHOLD_MODE thresholdMode;
} PS2000_TRIGGER_CHANNEL_PROPERTIES;

/* ---- streaming callback typedef ----------------------------------------- */
typedef void (*GetOverviewBuffersMaxMin)(int16_t **overviewBuffers,
                                         int16_t overflow, uint32_t triggeredAt,
                                         int16_t triggered, int16_t auto_stop,
                                         uint32_t nValues);

/* ---- core API used by manufacturer + generated code ---------------------- */
int16_t  ps2000_open_unit(void);
int16_t  ps2000_close_unit(int16_t handle);
int16_t  ps2000_get_unit_info(int16_t handle, int8_t *string, int16_t string_length, int16_t line);
int16_t  ps2000_flash_led(int16_t handle);

int16_t  ps2000_set_channel(int16_t handle, int16_t channel, int16_t enabled,
                            int16_t dc, int16_t range);
int16_t  ps2000_set_ets(int16_t handle, PS2000_ETS_MODE mode,
                        int16_t ets_cycles, int16_t ets_interleave);
int16_t  ps2000_set_trigger(int16_t handle, int16_t source, int16_t threshold,
                            int16_t direction, int16_t delay, int16_t auto_trigger_ms);

int16_t  ps2000_get_timebase(int16_t handle, int16_t timebase, int32_t no_of_samples,
                             int32_t *time_interval, int16_t *time_units,
                             int16_t oversample, int32_t *max_samples);

int32_t  ps2000_run_block(int16_t handle, int32_t no_of_samples, int16_t timebase,
                          int16_t oversample, int32_t *time_indisposed_ms);
int16_t  ps2000_ready(int16_t handle);
int16_t  ps2000_stop(int16_t handle);

int32_t  ps2000_get_times_and_values(int16_t handle, int32_t *times,
                                     int16_t *buffer_a, int16_t *buffer_b,
                                     int16_t *buffer_c, int16_t *buffer_d,
                                     int16_t *overflow, int16_t time_units,
                                     int32_t no_of_values);
int32_t  ps2000_get_values(int16_t handle, int16_t *buffer_a, int16_t *buffer_b,
                           int16_t *buffer_c, int16_t *buffer_d,
                           int16_t *overflow, int32_t no_of_values);

int16_t  ps2000_set_sig_gen_built_in(int16_t handle, int32_t offsetVoltage,
                                     uint32_t pkToPk, PS2000_WAVE_TYPE waveType,
                                     float startFrequency, float stopFrequency,
                                     float increment, float dwellTime,
                                     PS2000_SWEEP_TYPE sweepType, uint32_t sweeps);
int16_t  ps2000_set_sig_gen_arbitrary(int16_t handle, int32_t offsetVoltage,
                                      uint32_t pkToPk, uint32_t startDeltaPhase,
                                      uint32_t stopDeltaPhase, uint32_t deltaPhaseIncrement,
                                      uint32_t dwellCount, uint8_t *arbitraryWaveform,
                                      int32_t arbitraryWaveformSize,
                                      PS2000_SWEEP_TYPE sweepType, uint32_t sweeps);

#ifdef __cplusplus
}
#endif
#endif /* PS2000_MOCK_H */
