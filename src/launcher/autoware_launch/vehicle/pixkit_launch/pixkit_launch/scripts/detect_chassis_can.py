#!/usr/bin/env python3
"""Work out which SocketCAN interface the Pixkit chassis is on.

The two PCAN-USB FD adapters report the same vendor, product and ID_SERIAL and expose no
unique serial, so the kernel hands out can0 and can1 in USB enumeration order. That order is
a race and comes out either way across reboots. Guessing wrong is quiet and expensive: the
pix_hooke_driver chain reads /from_can_bus, sees nothing, every /vehicle/status/* topic stays
silent, and pose_initializer then refuses to initialize with "The vehicle is not stopped",
which leaves no map->base_link and an empty RViz.

So listen instead of guessing. The chassis bus is the one carrying the VCU feedback frames.

Prints one interface name, with no trailing newline because launch feeds the result straight
into an interface argument. Always prints something and always exits 0 - this runs inside a
$(command ...) substitution during launch, and failing there would take down the whole stack
for what is only a better-than-default guess.
"""

import argparse
import socket
import sys
import time

# V2A feedback frames the Pixkit VCU broadcasts continuously: drive, brake, steer, vehicle
# state, vehicle work state, power state and the wheel reports.
CHASSIS_IDS = frozenset(
    [0x530, 0x531, 0x532, 0x534, 0x535, 0x536, 0x537, 0x539, 0x542]
)

FALLBACK = {"chassis": "can0", "aux": "can1"}


def candidates():
    """SocketCAN interfaces that are administratively up, in kernel order."""
    found = []
    try:
        for _index, name in socket.if_nameindex():
            if name.startswith("can") and name[3:].isdigit():
                found.append(name)
    except OSError:
        return []
    return sorted(found, key=lambda n: int(n[3:]))


def chassis_frames(interface, budget_s):
    """Count chassis feedback frames seen on one interface within the time budget."""
    try:
        sock = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    except (AttributeError, OSError):
        return 0
    try:
        sock.bind((interface,))
    except OSError:
        # Interface is down or gone. Not an error, just not the one we want.
        sock.close()
        return 0

    hits = 0
    deadline = time.monotonic() + budget_s
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sock.settimeout(remaining)
            try:
                frame = sock.recv(16)
            except (socket.timeout, OSError):
                break
            if len(frame) < 4:
                continue
            # struct can_frame: can_id is a little endian u32, low 11 bits are the standard id.
            can_id = int.from_bytes(frame[:4], "little") & 0x7FF
            if can_id in CHASSIS_IDS:
                hits += 1
                # A handful is already conclusive; the other bus carries none at all.
                if hits >= 5:
                    break
    finally:
        sock.close()
    return hits


def emit(name):
    """Write the answer with no trailing newline - launch does not strip it."""
    sys.stdout.write(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--role", choices=("chassis", "aux"), default="chassis",
        help="which interface to name: the one with the chassis on it, or the other one")
    parser.add_argument(
        "--timeout", type=float, default=0.4,
        help="seconds to listen per interface (the VCU sends at 50 Hz, so this is generous)")
    args = parser.parse_args()

    interfaces = candidates()
    if len(interfaces) < 2:
        # Nothing to disambiguate. Say so on stderr, where launch surfaces it as a warning.
        print("detect_chassis_can: fewer than two can interfaces up, using defaults",
              file=sys.stderr)
        emit(FALLBACK[args.role])
        return

    scored = [(iface, chassis_frames(iface, args.timeout)) for iface in interfaces]
    chassis, best = max(scored, key=lambda pair: pair[1])

    if best == 0:
        # Every bus quiet: vehicle powered down, or the adapters are not on the chassis at
        # all. Defaults are as good a guess as any, and this is worth saying out loud.
        print("detect_chassis_can: no chassis frames on any of {}, using defaults".format(
            ", ".join(iface for iface, _ in scored)), file=sys.stderr)
        emit(FALLBACK[args.role])
        return

    if args.role == "chassis":
        emit(chassis)
        return

    others = [iface for iface, _ in scored if iface != chassis]
    emit(others[0])


if __name__ == "__main__":
    main()
