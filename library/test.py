#!/usr/bin/env python

import time
from max30105 import MAX30105, HeartRate

max30105 = MAX30105()
max30105.setup(leds_enable=3)

max30105.set_led_pulse_amplitude(1, 0)
max30105.set_led_pulse_amplitude(2, 0)
max30105.set_led_pulse_amplitude(3, 0)

max30105.set_slot_mode(1, 'red')
max30105.set_slot_mode(2, 'ir')
max30105.set_slot_mode(3, 'green')
max30105.set_slot_mode(4, 'off')

colours = {"red": 1, "ir": 2, "green": 3}

hr = HeartRate(max30105)

try:
    print("Temperature: {:.2f}C".format(max30105.get_temperature()))

    for c in colours:
        print("\nLighting {} LED".format(c.upper()))
        max30105.set_led_pulse_amplitude(colours[c], 12.5)
        time.sleep(0.5)
        print("Reading {} LED".format(c.upper()))
        i = 0

        while i < 10:
            samples = max30105.get_samples()
            if samples is not None:
                ir = samples[colours[c] - 1] & 0xff
                d = hr.low_pass_fir(ir)
                print(d)
                time.sleep(0.1)
                i += 1

        max30105.set_led_pulse_amplitude(colours[c], 0.0)

    print("\nTEST COMPLETE!!!")

except KeyboardInterrupt:
    pass
