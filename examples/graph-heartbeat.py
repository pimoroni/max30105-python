#!/usr/bin/env python

# NOTE! This code should not be used for medical diagnosis. It's
# for fun/novelty use only, so bear that in mind while using it.

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

print("""
NOTE! This code should not be used for medical diagnosis. It's
for fun/novelty use only, so bear that in mind while using it.

This example shows your pulse (using photoplethysmography) as a
histogram.

It's best to hold the sensor against your fingertip (the fleshy side)
using a piece of wire or a rubber band looped through the mounting
holes on the breakout, as the sensor is very sensitive to small
movements and it's hard to hold your finger against the sensor with
even pressure.

If you're using your MAX30105 Breakout with Breakout Garden, then
we'd recommend using one of our Breakout Garden Extender Kits with
some female to female jumper jerky.

https://shop.pimoroni.com/products/breakout-garden-extender-kit
""")

delay = 10

print("Starting readings in {} seconds...\n".format(delay))
time.sleep(delay)

try:
    while True:
        samples = max30105.get_samples()
        if samples is not None:
            for i in range(0, len(samples), 2):
                # Process the least significant byte, where most wiggling is
                ir = samples[i + 1] & 0xff
                d = hr.low_pass_fir(ir)

            print("#" * int(d / 2))
            time.sleep(1.0 / 100)  # 400sps 4 sample averaging = 100sps

except KeyboardInterrupt:
    pass
