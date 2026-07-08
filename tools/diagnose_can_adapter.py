"""Diagnose Windows/Linux USB-CAN adapter visibility for python-can."""

from __future__ import annotations

import argparse
import sys
import time


def _print_serial_ports() -> None:
    print("\nSerial/COM ports")
    try:
        from serial.tools import list_ports
    except ImportError as exc:
        print(f"  pyserial unavailable: {exc}")
        return
    ports = list(list_ports.comports())
    if not ports:
        print("  none")
        return
    for port in ports:
        vid = f"{port.vid:04X}" if port.vid is not None else "----"
        pid = f"{port.pid:04X}" if port.pid is not None else "----"
        print(f"  {port.device:<8} VID:PID {vid}:{pid}  {port.description}")
        if port.hwid:
            print(f"           {port.hwid}")


def _iter_usb_devices(backend=None):
    import usb.core

    return list(usb.core.find(find_all=True, backend=backend))


def _usb_label(device) -> str:
    parts = [f"{device.idVendor:04X}:{device.idProduct:04X}"]
    for attr in ("manufacturer", "product", "serial_number"):
        try:
            value = getattr(device, attr)
        except Exception:
            value = None
        if value:
            parts.append(str(value))
    return "  ".join(parts)


def _print_pyusb_devices() -> None:
    print("\nPyUSB default backend")
    try:
        devices = _iter_usb_devices()
    except ImportError as exc:
        print(f"  pyusb unavailable: {exc}")
        return
    except Exception as exc:
        print(f"  unable to enumerate USB devices: {exc}")
        return
    if not devices:
        print("  no USB devices visible through default PyUSB backend")
    for device in devices:
        print(f"  {_usb_label(device)}")

    print("\nPyUSB libusb-package backend")
    try:
        import libusb_package
        import usb.backend.libusb1

        backend = usb.backend.libusb1.get_backend(find_library=libusb_package.find_library)
        print(f"  backend: {backend!r}")
        devices = _iter_usb_devices(backend=backend)
    except ImportError as exc:
        print(f"  libusb-package unavailable: {exc}")
        return
    except Exception as exc:
        print(f"  unable to enumerate USB devices through libusb-package: {exc}")
        return
    if not devices:
        print("  no USB devices visible through libusb-package")
    for device in devices:
        print(f"  {_usb_label(device)}")


def _print_python_can_configs() -> None:
    print("\npython-can detection")
    try:
        import can
    except ImportError as exc:
        print(f"  python-can unavailable: {exc}")
        return
    print(f"  python-can {getattr(can, '__version__', 'unknown')}")
    try:
        configs = can.detect_available_configs(interfaces=["gs_usb"])
    except Exception as exc:
        print(f"  gs_usb detection failed: {exc}")
        return
    if not configs:
        print("  no gs_usb adapters detected")
        return
    for config in configs:
        print(f"  {config}")


def _open_gs_usb_bus(channel: int, bitrate: int, *, receive_own_messages: bool = False):
    import can

    kwargs = {
        "interface": "gs_usb",
        "channel": channel,
        "bitrate": bitrate,
    }
    if receive_own_messages:
        kwargs["receive_own_messages"] = True
    try:
        return can.Bus(**kwargs)
    except TypeError:
        kwargs["bustype"] = kwargs.pop("interface")
        return can.Bus(**kwargs)


def _try_open_gs_usb(channel: int, bitrate: int) -> None:
    print(f"\nOpening gs_usb channel {channel} at {bitrate}")
    try:
        bus = _open_gs_usb_bus(channel, bitrate)
    except Exception as exc:
        print(f"  open failed: {exc}")
        return
    try:
        print("  open OK")
    finally:
        bus.shutdown()


def _tx_test_gs_usb(channel: int, bitrate: int, count: int, interval_s: float) -> None:
    print(f"\nTX test on gs_usb channel {channel} at {bitrate}")
    try:
        import can

        bus = _open_gs_usb_bus(channel, bitrate, receive_own_messages=True)
    except Exception as exc:
        print(f"  open failed: {exc}")
        return
    try:
        message = can.Message(arbitration_id=0x100, data=bytes.fromhex("07D0"), is_extended_id=False)
        for index in range(max(1, count)):
            try:
                bus.send(message, timeout=0.5)
                print(f"  TX {index + 1}/{count}: 0x100 07 D0")
            except Exception as exc:
                print(f"  TX failed on frame {index + 1}: {exc}")
                break
            try:
                echo = bus.recv(timeout=0.1)
            except Exception as exc:
                print(f"  RX/echo check failed: {exc}")
                echo = None
            if echo is not None:
                print(f"    echo/RX 0x{echo.arbitration_id:03X} {bytes(echo.data).hex(' ').upper()}")
            time.sleep(max(0.0, interval_s))
    finally:
        bus.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose USB-CAN adapter visibility")
    parser.add_argument("--open-gs-usb", action="store_true", help="try opening gs_usb channel 0")
    parser.add_argument("--tx-test-gs-usb", action="store_true", help="transmit 0x100#07D0 frames over gs_usb")
    parser.add_argument("--channel", type=int, default=0)
    parser.add_argument("--bitrate", type=int, default=500_000)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--interval", type=float, default=0.1)
    args = parser.parse_args()

    print(f"Python: {sys.version.split()[0]}  {sys.executable}")
    _print_serial_ports()
    _print_pyusb_devices()
    _print_python_can_configs()
    if args.open_gs_usb:
        _try_open_gs_usb(args.channel, args.bitrate)
    if args.tx_test_gs_usb:
        _tx_test_gs_usb(args.channel, args.bitrate, args.count, args.interval)


if __name__ == "__main__":
    main()
