import max30105
import time

m = max30105.MAX30105()
m.setup()

print(m.get_temperature())

m._max30105.LED_PULSE_AMPLITUDE.set_led3_mA(0)
m._max30105.LED_PULSE_AMPLITUDE.set_led1_mA(0.2)
m._max30105.FIFO_CONFIG.set_fifo_almost_full(1)
m._max30105.INT_ENABLE_1.set_a_full_en(True)
m._max30105.INT_STATUS_1.set_a_full(False)

ir_min = 500
ir_max = 0

while True:
    samples = m.get_samples()
    if samples is not None:
        # print(samples)
        ir = samples[5]
        if ir < ir_min:
            ir_min = ir
        if ir > ir_max:
            ir_max = ir
        if ir_max != ir_min: 
            val = float(ir - ir_min) / (ir_max - ir_min)
            print("#" * int(val * 60))
    time.sleep(1.0 / 100)  # 400sps 4 sample averaging = 100sps
    
