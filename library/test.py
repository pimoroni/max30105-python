import max30105
import time

m = max30105.MAX30105()

print(m.get_temperature())

m._max30105.MODE_CONFIG.set_mode('green_red_ir')

m._max30105.SPO2_CONFIG.set_adc_range_nA(2048)
m._max30105.SPO2_CONFIG.set_sample_rate_sps(1000)
m._max30105.LED_MODE_CONTROL.set_slot1('red')
m._max30105.LED_MODE_CONTROL.set_slot2('ir')
m._max30105.LED_MODE_CONTROL.set_slot3('green')

while True:
    for x in range(32):
        with m._max30105.FIFO as fifo:
            data = fifo.get_channel0(), fifo.get_channel1(), fifo.get_channel2()
            print('{:02d}: {:05d} {:05d} {:05d}'.format(x, *data))
    time.sleep(0.5)
