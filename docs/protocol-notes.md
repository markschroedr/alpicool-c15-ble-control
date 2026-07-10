# Protocol notes

This implementation builds on several existing reverse-engineering projects:

- [`klightspeed/BrassMonkeyFridgeMonitor`](https://github.com/klightspeed/BrassMonkeyFridgeMonitor) documents the command types, service and characteristics and supports status reads and temperature changes.
- [`Hazelmeow/AlpicoolFridgeMonitor`](https://github.com/Hazelmeow/AlpicoolFridgeMonitor) independently confirms the service, characteristics and status decoding.
- [`johnelliott/alpicoold`](https://github.com/johnelliott/alpicoold) implements a Go HomeKit bridge and confirms the set-temperature command.
- [`jakub-hajek/alpicool-esp32-mqtt`](https://github.com/jakub-hajek/alpicool-esp32-mqtt) implements the protocol on an ESP32 and is a useful always-on alternative to macOS.

## BLE surface

- Service: `00001234-0000-1000-8000-00805f9b34fb`
- Command characteristic: `00001235-0000-1000-8000-00805f9b34fb`
- Notification characteristic: `00001236-0000-1000-8000-00805f9b34fb`
- Query packet: `fefe03010200`

On macOS, the address reported by CoreBluetooth is a UUID-style identifier rather than the cooler's hardware MAC address.

Notifications can arrive fragmented. The client buffers incoming bytes, finds the `fe fe` header, reads the packet length and waits for the checksum byte before decoding the status.

The tested status packet includes power, lock state, cooling mode, battery protection, temperature range, start delay, temperature unit, battery state and one or two compartment records.

## Scheduling behavior

The reconciler evaluates the latest schedule entry at the current local time. Each run reads the cooler state, applies only the required change and records the result. This avoids relying on separate calendar jobs, which macOS may replay after waking from sleep.
