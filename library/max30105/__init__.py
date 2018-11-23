"""MAX30105 Driver."""
from i2cdevice import Device, Register, BitField, _int_to_bytes
from i2cdevice.adapter import LookupAdapter, Adapter
import struct
import time

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
            return 0


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
            # FIFO data, 3 bytes per channel
            #Register('FIFO', 0x07, fields=(
            #    BitField('channel0', 0x3fffff << 0),
            #    BitField('channel1', 0x3fffff << (8 * 9 * 1)),
            #    BitField('channel2', 0x3fffff << (8 * 9 * 2)),
            #), bit_width=8 * 9 * 3),
            Register('FIFO_CONFIG', 0x08, fields=(
                BitField('sample_average', 0b111000000, adapter=LookupAdapter({
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
                BitField('temp_en', 0b00000001),
            )),
            Register('PROX_INT_THRESHOLD', 0x30, fields=(
                BitField('threshold', 0xff),
            )),
            Register('PART_ID', 0xfe, fields=(
                BitField('revision', 0xff00),
                BitField('part', 0x00ff)
            ), bit_width=16)
        ))

    def setup(self, led_power=6.4, sample_average=4, leds_enable=3, sample_rate=400, pulse_width=215, adc_range=16384):
        if self._is_setup:
            return
        self._is_setup = True

        self._active_leds = leds_enable

        self._max30105.select_address(self._i2c_addr)

        self.soft_reset()

        with self._max30105.FIFO_CONFIG as FIFO_CONFIG:
            # Average over 4 samples (the default value)
            FIFO_CONFIG.set_sample_average(sample_average)
            # Enable sample rollover
            FIFO_CONFIG.set_fifo_rollover_en(True)
            FIFO_CONFIG.write()

        with self._max30105.SPO2_CONFIG as SPO2_CONFIG:
            # Set the sample rate to 50 samples per second
            SPO2_CONFIG.set_sample_rate_sps(sample_rate)
            # And the ADC range to 16384
            SPO2_CONFIG.set_adc_range_nA(adc_range)
            # And the pulse width to 411us
            SPO2_CONFIG.set_led_pw_us(pulse_width)
            SPO2_CONFIG.write()

        with self._max30105.LED_PULSE_AMPLITUDE as LPA:
            LPA.set_led1_mA(led_power)
            LPA.set_led2_mA(led_power)
            LPA.set_led3_mA(led_power)
            LPA.write()

        self._max30105.LED_PROX_PULSE_AMPLITUDE.set_pilot_mA(led_power)

        # Set the LED mode based on the number of LEDs we want enabled
        self._max30105.MODE_CONFIG.set_mode(['red_only', 'red_ir', 'green_red_ir'][leds_enable - 1])

        # Set up the LEDs requested in sequential slots
        with self._max30105.LED_MODE_CONTROL as LMC:
            LMC.set_slot1('red')
            if leds_enable >= 2:
                LMC.set_slot2('ir')
            if leds_enable >= 3:
                LMC.set_slot3('green')
            LMC.write()

        self.clear_fifo()

    def soft_reset(self):
        self._max30105.MODE_CONFIG.set_reset(True)
        while self._max30105.MODE_CONFIG.get_reset():
            time.sleep(0.001)

    def clear_fifo(self):
        self._max30105.FIFO_READ.set_pointer(0)
        self._max30105.FIFO_WRITE.set_pointer(0)
        self._max30105.FIFO_OVERFLOW.set_counter(0)

    def get_samples(self):
        ptr_r = self._max30105.FIFO_READ.get_pointer()
        ptr_w = self._max30105.FIFO_WRITE.get_pointer()

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

        return data

    def get_chip_id(self):
        self.setup()

        revision = self._max30105.PART_ID.get_revision()
        part = self._max30105.PART_ID.get_part()

        return revision, part

    def get_temperature(self):
        self.setup()

        self._max30105.DIE_TEMP_CONFIG.set_temp_en(True)
        self._max30105.INT_ENABLE_2.set_die_temp_ready_en(True)
        while self._max30105.INT_STATUS_2.get_die_temp_ready() == False:
            time.sleep(0.01)
        return self._max30105.DIE_TEMP.get_temperature()
