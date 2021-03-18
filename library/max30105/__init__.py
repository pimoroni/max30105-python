"""MAX30105 Driver."""
from i2cdevice import Device, Register, BitField, _int_to_bytes
from i2cdevice.adapter import LookupAdapter, Adapter
import struct
import time


__version__ = '0.0.5'

CHIP_ID = 0x15
I2C_ADDRESS = 0x57


def bit(n):
    return 1 << n


class LEDModeAdapter(Adapter):
    LOOKUP = [
        'off',
        'red',
        'ir',
        'green',
        'off',
        'pilot_red',
        'pilot_ir',
        'pilot_green'
    ]

    def _decode(self, value):
        try:
            return self.LOOPUP[value]
        except IndexError:
            return 'off'

    def _encode(self, value):
        try:
            return self.LOOKUP.index(value)
        except ValueError:
            raise ValueError('Invalid slot mode {}'.format(value))


class PulseAmplitudeAdapter(Adapter):
    """Convert LED current control values approximately between LSBs and mA"""

    def _decode(self, value):
        return value * 0.2

    def _encode(self, value):
        return int(value / 0.2)


class TemperatureAdapter(Adapter):
    """Convert fractional and integer temp readings to degrees C."""

    def _decode(self, value):
        integer, fractional = struct.unpack('<bB', _int_to_bytes(value, 2))
        fractional *= 0.0625
        return integer + fractional


class S16Adapter(Adapter):
    """Convert unsigned 16bit integer to signed."""

    def _decode(self, value):
        return struct.unpack('<h', _int_to_bytes(value, 2))[0]


class U16Adapter(Adapter):
    """Convert from bytes to an unsigned 16bit integer."""

    def _decode(self, value):
        return struct.unpack('<H', _int_to_bytes(value, 2))[0]


class SampleAdapter(Adapter):
    def _decode(self, value):
        b = _int_to_bytes(value, 9)
        b = list(b)
        b.insert(0, 0)
        b.insert(4, 0)
        b.insert(8, 0)
        b = bytes("".join([chr(x) for x in b]))
        return struct.unpack('<LLL', b)


# HeartRate processing adapted from:
# https://github.com/sparkfun/SparkFun_MAX3010x_Sensor_Library/blob/master/examples/Example5_HeartRate/
class HeartRate:
    def __init__(self, max30105):
        """Initialise HeartRate detector.

        :param max30105: Instance of a max30105 sensor to read from.

        """
        self.max30105 = max30105
        self.ir_current = 0
        self.ir_min = -20
        self.ir_max = 20
        self.ir_avg = 0

        self.ir_signal_min = 0
        self.ir_signal_max = 0

        self.pos_edge = 0
        self.neg_edge = 0

        self.buf = [0 for x in range(32)]
        self.offset = 0

        self.fir_coeffs = [172, 321, 579, 927, 1360, 1858, 2390, 2916, 3391, 3768, 4012, 4096]

    def low_pass_fir(self, sample):
        """Filter a sample using a low-pass FIR filter with a 32 sample buffer."""
        self.buf[self.offset] = sample
        z = self.fir_coeffs[11] * self.buf[(self.offset - 11) & 0x1f]

        for i in range(11):
            z += self.fir_coeffs[i] * (self.buf[(self.offset - i) & 0x1f] + self.buf[(self.offset - 22 + i) & 0x1f])

        self.offset += 1
        self.offset %= 32
        return z >> 15

    def average_dc_estimator(self, sample):
        """Estimate the average DC."""
        self.ir_avg += (((sample << 15) - self.ir_avg) >> 4)
        return self.ir_avg >> 15

    def check_for_beat(self, sample):
        """Check for a single beat."""
        beat_detected = False
        ir_previous = self.ir_current
        ir_avg_est = self.average_dc_estimator(sample)
        self.ir_current = self.low_pass_fir(sample - ir_avg_est)

        if ir_previous < 0 and self.ir_current >= 0:
            self.ir_max = self.ir_signal_max
            self.ir_min = self.ir_signal_min
            self.pos_edge = 1
            self.neg_edge = 0
            self.ir_signal_max = 0

            if (self.ir_max - self.ir_min) > 20 and (self.ir_max - self.ir_min) < 1000:
                beat_detected = True

        if ir_previous > 0 and self.ir_current <= 0:
            self.pos_edge = 0
            self.neg_edge = 1
            self.ir_signal_min = 0

        if self.pos_edge and self.ir_current > ir_previous:
            self.ir_signal_max = self.ir_current

        if self.neg_edge and self.ir_current > ir_previous:
            self.ir_signal_min = self.ir_current

        return beat_detected

    def on_beat(self, handler, average_over=4, delay=0.5):
        """Watch for heartbeat and call a function on every beat.

        :param handler: Function to call, should accept beat_detected, bpm and bpm_avg arguments
        :param average_over: Number of samples to average over

        """
        bpm_vals = [0 for x in range(average_over)]
        last_beat = time.time()
        last_update = time.time()
        bpm = 0
        bpm_avg = 0
        beat_detected = False

        while True:
            t = time.time()

            samples = self.max30105.get_samples()
            if samples is None:
                continue

            for sample_index in range(0, len(samples), 2):
                sample = samples[sample_index + 1]
                if self.check_for_beat(sample):
                    beat_detected = True
                    delta = t - last_beat
                    last_beat = t
                    bpm = 60 / delta
                    bpm_vals = bpm_vals[1:] + [bpm]
                    bpm_avg = sum(bpm_vals) / average_over

            if t - last_update >= delay:
                if handler(beat_detected, bpm, bpm_avg):
                    return
                beat_detected = False
                last_update = t


class MAX30105:
    def __init__(self, i2c_addr=I2C_ADDRESS, i2c_dev=None):
        self._is_setup = False
        self._i2c_addr = i2c_addr
        self._i2c_dev = i2c_dev
        self._active_leds = 0
        self._max30105 = Device(I2C_ADDRESS, i2c_dev=self._i2c_dev, bit_width=8, registers=(
            Register('INT_STATUS_1', 0x00, fields=(
                BitField('a_full', bit(7)),
                BitField('data_ready', bit(6)),
                BitField('alc_overflow', bit(5)),
                BitField('prox_int', bit(4)),
                BitField('pwr_ready', bit(0))
            )),
            Register('INT_STATUS_2', 0x01, fields=(
                BitField('die_temp_ready', bit(1)),
            )),
            Register('INT_ENABLE_1', 0x02, fields=(
                BitField('a_full_en', bit(7)),
                BitField('data_ready_en', bit(6)),
                BitField('alc_overflow_en', bit(5)),
                BitField('prox_int_en', bit(4)),
            )),
            Register('INT_ENABLE_2', 0x03, fields=(
                BitField('die_temp_ready_en', bit(1)),
            )),
            # Points to MAX30105 write location in FIFO
            Register('FIFO_WRITE', 0x04, fields=(
                BitField('pointer', 0b00011111),
            )),
            # Counts the number of samples lost up to 0xf
            Register('FIFO_OVERFLOW', 0x05, fields=(
                BitField('counter', 0b00011111),
            )),
            # Points to read location in FIFO
            Register('FIFO_READ', 0x06, fields=(
                BitField('pointer', 0b00011111),
            )),
            Register('FIFO_CONFIG', 0x08, fields=(
                BitField('sample_average', 0b11100000, adapter=LookupAdapter({
                    1: 0b000,
                    2: 0b001,
                    4: 0b010,
                    8: 0b011,
                    16: 0b100,
                    32: 0b101
                })),
                BitField('fifo_rollover_en', 0b00010000),
                BitField('fifo_almost_full', 0b00001111)
            )),
            Register('MODE_CONFIG', 0x09, fields=(
                BitField('shutdown', 0b10000000),
                BitField('reset', 0b01000000),
                BitField('mode', 0b00000111, adapter=LookupAdapter({
                    'none': 0b00,
                    'red_only': 0b010,
                    'red_ir': 0b011,
                    'green_red_ir': 0b111
                }))
            )),
            Register('SPO2_CONFIG', 0x0A, fields=(
                BitField('adc_range_nA', 0b01100000, adapter=LookupAdapter({
                    2048: 0b00,
                    4096: 0b01,
                    8192: 0b10,
                    16384: 0b11
                })),
                BitField('sample_rate_sps', 0b00011100, adapter=LookupAdapter({
                    50: 0b000,
                    100: 0b001,
                    200: 0b010,
                    400: 0b011,
                    800: 0b100,
                    1000: 0b101,
                    1600: 0b110,
                    3200: 0b111
                })),
                BitField('led_pw_us', 0b00000011, adapter=LookupAdapter({
                    69: 0b00,   # 68.95us
                    118: 0b01,  # 117.78us
                    215: 0b10,  # 215.44us
                    411: 0b11   # 410.75us
                }))
            )),
            Register('LED_PULSE_AMPLITUDE', 0x0C, fields=(
                BitField('led1_mA', 0xff0000, adapter=PulseAmplitudeAdapter()),
                BitField('led2_mA', 0x00ff00, adapter=PulseAmplitudeAdapter()),
                BitField('led3_mA', 0x0000ff, adapter=PulseAmplitudeAdapter())
            ), bit_width=24),
            Register('LED_PROX_PULSE_AMPLITUDE', 0x10, fields=(
                BitField('pilot_mA', 0xff, adapter=PulseAmplitudeAdapter()),
            )),
            # The below represent 4 timeslots
            Register('LED_MODE_CONTROL', 0x11, fields=(
                BitField('slot2', 0x7000, adapter=LEDModeAdapter()),
                BitField('slot1', 0x0700, adapter=LEDModeAdapter()),
                BitField('slot4', 0x0070, adapter=LEDModeAdapter()),
                BitField('slot3', 0x0007, adapter=LEDModeAdapter())
            ), bit_width=16),
            Register('DIE_TEMP', 0x1f, fields=(
                BitField('temperature', 0xffff, adapter=TemperatureAdapter()),
            ), bit_width=16),
            Register('DIE_TEMP_CONFIG', 0x21, fields=(
                BitField('temp_en', bit(0)),
            )),
            Register('PROX_INT_THRESHOLD', 0x30, fields=(
                BitField('threshold', 0xff),
            )),
            Register('PART_ID', 0xfe, fields=(
                BitField('revision', 0xff00),
                BitField('part', 0x00ff)
            ), bit_width=16)
        ))

    def setup(self, led_power=6.4, sample_average=4, leds_enable=3, sample_rate=400, pulse_width=215, adc_range=16384, timeout=5.0):
        """Set up the sensor."""
        if self._is_setup:
            return
        self._is_setup = True

        self._active_leds = leds_enable

        self._max30105.select_address(self._i2c_addr)

        self.soft_reset(timeout=timeout)

        self._max30105.set('FIFO_CONFIG',
                           sample_average=sample_average,
                           fifo_rollover_en=True)

        self._max30105.set('SPO2_CONFIG',
                           sample_rate_sps=sample_rate,
                           adc_range_nA=adc_range,
                           led_pw_us=pulse_width)

        self._max30105.set('LED_PULSE_AMPLITUDE',
                           led1_mA=led_power,
                           led2_mA=led_power,
                           led3_mA=led_power)

        self._max30105.set('LED_PROX_PULSE_AMPLITUDE', pilot_mA=led_power)

        # Set the LED mode based on the number of LEDs we want enabled
        self._max30105.set('MODE_CONFIG',
                           mode=['red_only', 'red_ir', 'green_red_ir'][leds_enable - 1])

        # Set up the LEDs requested in sequential slots
        self._max30105.set('LED_MODE_CONTROL',
                           slot1='red',
                           slot2='ir' if leds_enable >= 2 else 'off',
                           slot3='green' if leds_enable >= 3 else 'off')

        self.clear_fifo()

    def soft_reset(self, timeout=5.0):
        """Reset device."""
        self._max30105.set('MODE_CONFIG', reset=True)
        t_start = time.time()
        while self._max30105.get('MODE_CONFIG').reset and time.time() - t_start < timeout:
            time.sleep(0.001)
        if self._max30105.get('MODE_CONFIG').reset:
            raise RuntimeError("Timeout: Failed to soft reset MAX30105.")

    def clear_fifo(self):
        """Clear samples FIFO."""
        self._max30105.set('FIFO_READ', pointer=0)
        self._max30105.set('FIFO_WRITE', pointer=0)
        self._max30105.set('FIFO_OVERFLOW', counter=0)

    def get_samples(self):
        """Return contents of sample FIFO."""
        ptr_r = self._max30105.get('FIFO_READ').pointer
        ptr_w = self._max30105.get('FIFO_WRITE').pointer

        if ptr_r == ptr_w:
            return None

        sample_count = ptr_w - ptr_r
        if sample_count < 0:
            sample_count = 32

        byte_count = sample_count * 3 * self._active_leds

        data = []

        while byte_count > 0:
            data += self._max30105._i2c.read_i2c_block_data(self._i2c_addr, 0x07, min(byte_count, 32))
            byte_count -= 32

        self.clear_fifo()

        result = []
        for x in range(0, len(data), 3):
            result.append((data[x] << 16) | (data[x + 1] << 8) | data[x + 2])

        return result

    def get_chip_id(self):
        """Return the revision and part IDs."""
        self.setup()

        part_id = self._max30105.get('PART_ID')

        return part_id.revision, part_id.part

    def get_temperature(self, timeout=5.0):
        """Return the die temperature."""
        self.setup()

        self._max30105.set('INT_ENABLE_2', die_temp_ready_en=True)
        self._max30105.set('DIE_TEMP_CONFIG', temp_en=True)
        t_start = time.time()

        while not self._max30105.get('INT_STATUS_2').die_temp_ready:
            time.sleep(0.01)
            if time.time() - t_start > timeout:
                raise RuntimeError('Timeout: Waiting for INT_STATUS_2, die_temp_ready.')

        return self._max30105.get('DIE_TEMP').temperature

    def set_mode(self, mode):
        """Set the sensor mode.

        :param mode: Mode, either red_only, red_ir or green_red_ir

        """
        self._max30105.set('MODE_CONFIG', mode=mode)

    def set_slot_mode(self, slot, mode):
        """Set the mode of a single slot.

        :param slot: Slot to set, either 1, 2, 3 or 4
        :param mode: Mode, either off, red, ir, green, pilot_red, pilot_ir or pilot_green

        """
        if slot == 1:
            self._max30105.set('LED_MODE_CONTROL', slot1=mode)
        elif slot == 2:
            self._max30105.set('LED_MODE_CONTROL', slot2=mode)
        elif slot == 3:
            self._max30105.set('LED_MODE_CONTROL', slot3=mode)
        elif slot == 4:
            self._max30105.set('LED_MODE_CONTROL', slot4=mode)
        else:
            raise ValueError("Invalid LED slot: {}".format(slot))

    def set_led_pulse_amplitude(self, led, amplitude):
        """Set the LED pulse amplitude in milliamps.

        :param led: LED to set, either 1, 2 or 3
        :param amplitude: LED amplitude in milliamps

        """
        if led == 1:
            self._max30105.set('LED_PULSE_AMPLITUDE', led1_mA=amplitude)
        elif led == 2:
            self._max30105.set('LED_PULSE_AMPLITUDE', led2_mA=amplitude)
        elif led == 3:
            self._max30105.set('LED_PULSE_AMPLITUDE', led3_mA=amplitude)
        else:
            raise ValueError("Invalid LED: {}".format(led))

    def set_fifo_almost_full_count(self, count):
        """Set number of FIFO slots remaining for Almost Full trigger.

        :param count: Count of remaining samples, from 0 to 15

        """
        self._max30105.set('FIFO_CONFIG', fifo_almost_full=count)

    def set_fifo_almost_full_enable(self, value):
        """Enable the FIFO-almost-full flag."""
        self._max30105.set('INT_ENABLE_1', a_full_en=value)

    def set_data_ready_enable(self, value):
        """Enable the data-ready flag."""
        self._max30105.set('INT_ENABLE_1', data_ready_en=value)

    def set_ambient_light_compensation_overflow_enable(self, value):
        """Enable the ambient light compensation overflow flag."""
        self._max30105.set('INT_ENABLE_1', alc_overflow_en=value)

    def set_proximity_enable(self, value):
        """Enable the proximity interrupt flag."""
        self._max30105.set('INT_ENABLE_1', prox_int_en=value)

    def set_proximity_threshold(self, value):
        """Set the threshold of the proximity sensor.

        Sets the infra-red ADC count that will trigger the start of particle-sensing mode.

        :param value: threshold value from 0 to 255

        """
        self._max30105.set('PROX_INT_THRESHOLD', threshold=value)

    def get_fifo_almost_full_status(self):
        """Get the FIFO-almost-full flag.

        This interrupt is set when the FIFO write pointer has N free spaces remaining, as defined in `set_fifo_almost_full_count`.

        The flag is cleared upon read.

        """
        return self._max30105.get('INT_STATUS_1').a_full

    def get_data_ready_status(self):
        """Get the data-ready flag.

        In particle-sensing mode this interrupt triggeres when a new sample has been placed into the FIFO.

        This flag is cleared upon read, or upon `get_samples()`

        """
        return self._max30105.get('INT_STATUS_1').data_ready

    def get_ambient_light_compensation_overflow_status(self):
        """Get the ambient light compensation overflow status flag.

        Returns True if the ALC has reached its limit, and ambient light is affecting the output of the ADC.

        This flag is cleared upon read.

        """
        return self._max30105.get('INT_STATUS_1').alc_overflow

    def get_proximity_triggered_threshold_status(self):
        """Get the proximity triggered threshold status flag.

        Returns True if the proximity threshold has been reached and particle-sensing mode has begun.

        This flag is cleared upon read.

        """
        return self._max30105.get('INT_STATUS_1').prox_int

    def get_power_ready_status(self):
        """Get the power ready status flag.

        Returns True if the sensor has successfully powered up and is ready to collect data.

        """
        return self._max30105.get('INT_STATUS_1').pwr_ready

    def get_die_temp_ready_status(self):
        """Get the die temperature ready flag.

        Returns True if the die temperature value is ready to be read.

        This flag is cleared upon read, or upon `get_temperature`.

        """
        return self._max30105.get('INT_STATUS_2').die_temp_ready
