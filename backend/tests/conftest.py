import base64
import os

os.environ.setdefault("EHUB_DB_PASSWORD", "test")
os.environ.setdefault("EHUB_DEVICE_CRED_KEY", base64.b64encode(b"k" * 32).decode())
