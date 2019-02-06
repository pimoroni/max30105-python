import max30105
import time

m = max30105.MAX30105()
m.setup(leds_enable=2)

print(m.get_temperature())

m._max30105.LED_PULSE_AMPLITUDE.set_led3_mA(0)
m._max30105.LED_PULSE_AMPLITUDE.set_led1_mA(0.2)
m._max30105.LED_PULSE_AMPLITUDE.set_led2_mA(12.5)
m._max30105.FIFO_CONFIG.set_fifo_almost_full(1)
m._max30105.INT_ENABLE_1.set_a_full_en(True)
m._max30105.INT_STATUS_1.set_a_full(False)
m._max30105.LED_MODE_CONTROL.set_slot1('red')
m._max30105.LED_MODE_CONTROL.set_slot2('ir')
m._max30105.LED_MODE_CONTROL.set_slot3('off')
m._max30105.LED_MODE_CONTROL.set_slot4('off')

ir_current = 0
ir_min = -20
ir_max = 20
ir_avg = 0

ir_signal_min = 0
ir_signal_max = 0

pos_edge = 0
neg_edge = 0

buf = [0 for x in range(32)]
offset = 0

fir_coeffs = [172, 321, 579, 927, 1360, 1858, 2390, 2916, 3391, 3768, 4012, 4096]

def low_pass_fir(sample):
    global offset

    buf[offset] = sample
    z = fir_coeffs[11] * buf[(offset - 11) & 0x1f]

    for i in range(11):
        z += fir_coeffs[i] * ( buf[(offset - i) & 0x1f] + buf[(offset - 22 + i) & 0x1f] )

    offset += 1
    offset %= 32
    return z >> 15

def average_dc_estimator(sample):
    global ir_avg

    ir_avg += (((sample << 15) - ir_avg) >> 4)
    return ir_avg >> 15

def check_for_beat(sample):
    global ir_current, pos_edge, neg_edge, ir_signal_min, ir_signal_max

    beat_detected = False
    ir_previous = ir_current
    ir_avg_est = average_dc_estimator(sample)
    ir_current = low_pass_fir(sample - ir_avg_est)

    if ir_previous < 0 and ir_current >= 0:
        ir_max = ir_signal_max
        ir_min = ir_signal_min
        pos_edge = 1
        neg_edge = 0
        ir_signal_max = 0

        if (ir_max - ir_min) > 20 and (ir_max - ir_min) < 1000:
            beat_detected = True

    if ir_previous > 0 and ir_current <= 0:
        pos_edge = 0
        neg_edge = 1
        ir_signal_min = 0

    if pos_edge and ir_current > ir_previous:
        ir_signal_max = ir_current

    if neg_edge and ir_current > ir_previous:
        ir_signal_min = ir_current

    return beat_detected

bpm = 0
bpm_avg = 0
avg_size = 4
bpm_vals = [0] * avg_size
last_beat = time.time()

while True:
    samples = m.get_samples()

    if samples is not None:
        sample = samples[1]

        if check_for_beat(sample):
            t = time.time()
            delta = t - last_beat
            last_beat = t
            bpm = 60 / delta
            bpm_vals = bpm_vals[1:] + [bpm]
            bpm_avg = sum(bpm_vals) / avg_size

    print("BPM: {:.2f}".format(bpm_avg))
