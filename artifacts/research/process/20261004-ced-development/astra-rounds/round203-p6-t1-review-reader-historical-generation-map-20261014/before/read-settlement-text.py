"""R202 batch25: print frozen settlement source as text, never execute it."""
import hashlib
import pathlib
import signal
import sys

signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("120 second read cap")))
signal.alarm(120)
path = pathlib.Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014/implementation/root-settlement.py")
if path.is_symlink():
    raise ValueError("source must not be a symlink")
data = path.read_bytes()
digest = hashlib.sha256(data).hexdigest()
if len(data) != 30449 or digest != "fbf213fed631db3e7c80858788ba68f534559325dcfadcab5329cc6f06e63652":
    raise ValueError("frozen source pin mismatch")
lines = data.decode("utf-8").splitlines()
if len(lines) != 594 or len(lines) > 600:
    raise ValueError("frozen source line count mismatch")
text = "SOURCE " + str(path) + "\nBYTES 30449 SHA256 " + digest + "\n"
text += "\n".join(str(index) + ": " + line for index, line in enumerate(lines, 1)) + "\n"
if len(text.encode("utf-8")) > 40000 or len(text.splitlines()) > 600:
    raise ValueError("bounded source output exceeds cap")
sys.stdout.write(text)
signal.alarm(0)
