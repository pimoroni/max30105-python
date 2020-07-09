import smbus2
import time

bus = smbus2.SMBus(1)

while True:
    bus.write_byte_data(0x57, 0x03, 0x02)
    bus.write_byte_data(0x57, 0x21, 0x01)
    while bus.read_byte_data(0x57, 0x01) == 0:
        print("Waiting...")
        time.sleep(0.5)
    print("read")

