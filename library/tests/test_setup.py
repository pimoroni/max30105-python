from i2cdevice import MockSMBus
import pytest


class MockSMBusNoTimeout(MockSMBus):
    def write_i2c_block_data(self, i2c_address, register, values):
        # Prevent the reset bit from being written
        # simulating an immediate soft reset success
        if register == 0x09:
            values[0] &= ~0b01000000
        MockSMBus.write_i2c_block_data(self, i2c_address, register, values)


def test_setup():
    from max30105 import MAX30105
    max30105 = MAX30105(i2c_dev=MockSMBusNoTimeout(1, default_registers={0x09: 0b00000111}))
    max30105.setup()


def test_setup_timeout():
    from max30105 import MAX30105
    max30105 = MAX30105(i2c_dev=MockSMBus(1, default_registers={0x09: 0b00000111}))

    with pytest.raises(RuntimeError):
        max30105.setup(timeout=0.5)
