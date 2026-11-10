# wifi_check.py: M1 piece 1. Can the watch join Wi-Fi and reach the server?
# Run from Thonny with F5 (Ctrl+C first so main.py stops). Prints each step.
# Needs config.py saved on the watch.
import time
import network
import config

try:
    import requests             # UIFlow2 firmware
except ImportError:
    import urequests as requests

WIFI_TIMEOUT_MS = 15000


def join_wifi():
    # Returns (wlan, ms taken, connected?).
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)                       # main.py turns the radio off at boot
    start = time.ticks_ms()
    if not wlan.isconnected():
        print("Joining %s ..." % config.WIFI_SSID)
        wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
        while not wlan.isconnected():
            if time.ticks_diff(time.ticks_ms(), start) > WIFI_TIMEOUT_MS:
                return wlan, WIFI_TIMEOUT_MS, False
            time.sleep_ms(100)
    return wlan, time.ticks_diff(time.ticks_ms(), start), True


def rssi(wlan):
    # Signal strength in dBm: about -50 is great, below about -80 is unreliable.
    try:
        return wlan.status("rssi")
    except Exception:
        return None


def check_health():
    url = config.SERVER + "/health"
    print("GET %s" % url)
    start = time.ticks_ms()
    try:
        r = requests.get(url)
    except OSError as e:
        print("FAIL request error: %s (wrong IP or port, server not on 0.0.0.0, or firewall?)" % e)
        return False
    ms = time.ticks_diff(time.ticks_ms(), start)
    try:
        status, body = r.status_code, r.text
    finally:
        r.close()                           # each open response holds memory the watch is short on
    print("%d %s (%d ms)" % (status, body, ms))
    if status != 200:
        print("FAIL expected 200")
        return False
    print("PASS watch reached the server")
    return True


wlan, ms, connected = join_wifi()
if not connected:
    print("FAIL no Wi-Fi after %d ms (status %s). Wrong password, or no 2.4 GHz network?"
          % (ms, wlan.status()))
else:
    print("Connected in %d ms, IP %s, RSSI %s dBm" % (ms, wlan.ifconfig()[0], rssi(wlan)))
    check_health()
