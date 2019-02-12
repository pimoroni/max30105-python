import sys
import mock


def test_setup():
    sys.modules['smbus'] = mock.Mock()
    sys.modules['RPi'] = mock.Mock()
    sys.modules['RPi.GPIO'] = mock.Mock()

    from max30105 import MAX30105
    max30105 = MAX30105()
    del max30105
