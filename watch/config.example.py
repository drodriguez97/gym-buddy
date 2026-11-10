# config.example.py: the settings the watch needs, with placeholder values.
# Copy to config.py, fill in the real values, and save config.py to the watch.
# config.py is in .gitignore, so the Wi-Fi password and token never reach Git.
WIFI_SSID = "your-network-name"         # must offer 2.4 GHz; the ESP32 can't see 5 or 6 GHz
WIFI_PASSWORD = "your-wifi-password"
SERVER = "http://192.168.1.23:8000"     # the laptop's IPv4 address from ipconfig, then the port
TOKEN = "dev-token"                     # must match GYM_BUDDY_TOKEN on the server
