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

ir_min = 50000
ir_max = 0

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

while True:
    samples = m.get_samples()
    if samples is not None:
        #print(samples)
        ir = samples[1] & 0xff 
        d = low_pass_fir(ir)
        #d = ir
        #print(d)
        # print(samples)
        #ir = samples[5]
        if d < ir_min:
            ir_min = d
        if ir > ir_max:
            ir_max = d
        #if ir_max != ir_min: 
        #    d = float(d - ir_min) / (ir_max - ir_min)
        #    print("#" * int(d * 60))
        print("#" * int(d / 2))
    time.sleep(1.0 / 100)  # 400sps 4 sample averaging = 100sps
    
