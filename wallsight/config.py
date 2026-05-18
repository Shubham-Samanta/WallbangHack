from pathlib import Path

MAC_B_IP   = "100.84.88.110"    # shubham-sankalps-macbook-air — server (run python server.py here)
MAC_A_IP   = "100.124.162.83"   # shubhams-macbook-air — camera only (browser /camera)
IPHONE_IP  = "100.104.191.98"   # iphone175 — HUD viewer

PORT            = 3000
USE_HTTPS       = True   # required for getUserMedia on Mac A (Chrome blocks camera over http://IP)
_CERT_DIR       = Path(__file__).parent / "certs"
SSL_CERT        = _CERT_DIR / "cert.pem"
SSL_KEY         = _CERT_DIR / "key.pem"
WS_PORT         = 3001
TARGET_W        = 640
TARGET_H        = 480
JPEG_QUALITY    = 82
PROCESS_EVERY_N = 2
MAC_B_CAM_INDEX = 0
