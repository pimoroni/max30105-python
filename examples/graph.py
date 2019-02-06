#!/usr/bin/env python
import time
from max30105 import MAX30105, HeartRate

max30105 = MAX30105()
max30105.setup(leds_enable=2)

max30105.set_led_pulse_amplitude(1, 0.2)
max30105.set_led_pulse_amplitude(2, 12.5)
max30105.set_led_pulse_amplitude(3, 0)

max30105.set_slot_mode(1, 'red')
max30105.set_slot_mode(2, 'ir')
max30105.set_slot_mode(3, 'off')
max30105.set_slot_mode(4, 'off')

hr = HeartRate(max30105)

try:
    while True:
        samples = max30105.get_samples()
        if samples is not None:
            for i in range(0, len(samples), 2):
                # Process the least significant byte, where most wiggling happens
                ir = samples[i + 1] & 0xff
                d = hr.low_pass_fir(ir)

            print("#" * int(d / 2))
            time.sleep(1.0 / 100)  # 400sps 4 sample averaging = 100sps

except KeyboardInterrupt:
    pass
