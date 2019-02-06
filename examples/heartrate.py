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

def display_heartrate(beat, bpm, avg_bpm):
    print("{} BPM: {:.2f}  AVG: {:.2f}".format("<3" if beat else "  ", bpm, avg_bpm))

hr = HeartRate(max30105)

print("Getting heartrate, please wait...")

try:
    hr.on_beat(display_heartrate, average_over=4)
except KeyboardInterrupt:
    pass
