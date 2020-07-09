from i2cdevice import MockSMBus
import pytest


class MockSMBusNoTimeout(MockSMBus):
    def write_i2c_block_data(self, i2c_address, register, values):
        # Prevent the reset bit from being written
        # simulating an immediate soft reset success
        if register == 0x09:
            values[0] &= ~0b01000000
        MockSMBus.write_i2c_block_data(self, i2c_address, register, values)


def test_get_chip_id():
    from max30105 import MAX30105
    max30105 = MAX30105(i2c_dev=MockSMBusNoTimeout(1, default_registers={0x09: 0b00000111}))
    assert max30105.get_chip_id() == (0, 0)


def test_get_temperature():
    from max30105 import MAX30105
    max30105 = MAX30105(i2c_dev=MockSMBusNoTimeout(1, default_registers={
        0x01: 0b00000010,  # Die temp ready
        0x09: 0b00000111   # Hard default value to avoid error
    }))
    assert max30105.get_temperature() == 0


def test_get_temperature_timeout():
    from max30105 import MAX30105
    max30105 = MAX30105(i2c_dev=MockSMBusNoTimeout(1, default_registers={
        0x01: 0b00000000,  # Die temp NOT ready
        0x09: 0b00000111   # Hard default value to avoid error
    }))

    with pytest.raises(RuntimeError):
        max30105.get_temperature()


def test_get_status():
    from max30105 import MAX30105
    max30105 = MAX30105(i2c_dev=MockSMBusNoTimeout(1, default_registers={
        0x01: 0b00000010,  # Die temp ready
        0x09: 0b00000111   # Hard default value to avoid error
    }))

    # We don't really care about the values,
    # just that these don't fail due to some typo
    max30105.get_data_ready_status()
    max30105.get_die_temp_ready_status()
    max30105.get_fifo_almost_full_status()
    max30105.get_ambient_light_compensation_overflow_status()
    max30105.get_power_ready_status()
    max30105.get_proximity_triggered_threshold_status()


def test_set_slot_mode():
    from max30105 import MAX30105
    max30105 = MAX30105(i2c_dev=MockSMBusNoTimeout(1, default_registers={
        0x01: 0b00000010,  # Die temp ready
        0x09: 0b00000111   # Hard default value to avoid error
    }))

    max30105.set_slot_mode(1, 'green')
    max30105.set_slot_mode(1, 'red')

    with pytest.raises(ValueError):
        max30105.set_slot_mode(1, 'puce')
