# ============================================================
# watcher.py - Central Control + mesh bridge + voice
#
# Wokwi projects cannot talk to each other, so this script carries the packets:
#   1. You type an announcement here -> it is sent to the GATEWAY (port 4000).
#   2. The gateway prints "ANNOUNCE:seq|hmac|message" -> this script delivers that
#      packet to the household(s) listed in HEARD_RELAY_DIRECTLY (the relay's coverage).
#   3. A household that accepts a NEW message prints "FORWARD:..." -> this script delivers
#      it to its neighbours in the chain (H1-H2-H3-...), like a Wi-Fi mesh broadcast.
#   4. Voice: only the message a household ACCEPTED (its "RECEIVED:" line) is spoken,
#      so a message that failed the HMAC/replay checks is never spoken.
# ============================================================
import serial
import threading
import queue
import time
import os
import asyncio
import pyttsx3
import pythoncom
import edge_tts
from playsound import playsound
 
BAUD = 115200
 
# ---- Ports (each Wokwi project needs its OWN rfc2217ServerPort in its wokwi.toml) ----
GATEWAY_URL = "rfc2217://localhost:4000"
HOUSEHOLD_URLS = [
    "rfc2217://localhost:4001",   # H1
    "rfc2217://localhost:4002",   # H2
    "rfc2217://localhost:4003",   # H3
]
 
# ---- Mesh layout (0 = H1, 1 = H2, ...) ----
HEARD_RELAY_DIRECTLY = [0]   # only H1 is in the relay's range; the rest get it by forwarding
SPEAK_FROM = 0               # the voice speaks what this household accepted (0 = H1)
 
TAGALOG_VOICE = "fil-PH-BlessicaNeural"
TEMP_AUDIO_FILE = "temp_announcement.mp3"
 
 
def connect(url, name, attempts=5, delay=1.0):
    for i in range(1, attempts + 1):
        try:
            s = serial.serial_for_url(url, baudrate=BAUD, timeout=1)
            print(f"Connected to {name} ({url})")
            return s
        except Exception as exc:
            print(f"{name}: attempt {i}/{attempts} failed: {exc}")
            time.sleep(delay)
    return None
 
 
gateway = connect(GATEWAY_URL, "Gateway", attempts=10, delay=1.5)
if gateway is None:
    raise RuntimeError("Could not connect to the Gateway. Is its Wokwi simulation running?")
 
households = []
for idx, url in enumerate(HOUSEHOLD_URLS):
    households.append(connect(url, f"H{idx + 1}"))   # None if that simulation is not running
 
write_lock = threading.Lock()
 
 
def send_line(ser, text):
    with write_lock:
        ser.write((text + "\n").encode("utf-8"))
 
 
# ---------------- Voice (one worker thread, so speech never overlaps) ----------------
speech_queue = queue.Queue()
 
 
def speaker_worker():
    pythoncom.CoInitialize()
 
    async def _generate_tagalog(text, filename):
        communicate = edge_tts.Communicate(text, TAGALOG_VOICE)
        await communicate.save(filename)
 
    def speak_tagalog(text):
        asyncio.run(_generate_tagalog(text, TEMP_AUDIO_FILE))
        playsound(TEMP_AUDIO_FILE)
        os.remove(TEMP_AUDIO_FILE)
 
    def speak_fallback(text):
        engine = pyttsx3.init()
        engine.setProperty("rate", 150)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
        del engine
 
    while True:
        text = speech_queue.get()
        print(f"Speaking: {text}")
        try:
            speak_tagalog(text)
        except Exception as exc:
            print(f"Tagalog TTS failed ({exc}), falling back to offline voice...")
            try:
                speak_fallback(text)
            except Exception as exc2:
                print(f"TTS error: {exc2}")
 
 
# ---------------- Readers ----------------
def read_lines(ser):
    """Yield complete lines from a serial port forever."""
    buffer = ""
    while True:
        data = ser.read(1)
        if not data:
            time.sleep(0.02)
            continue
        buffer += data.decode(errors="ignore")
        if "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if line:
                yield line
 
 
def gateway_loop():
    try:
        for line in read_lines(gateway):
            if line.startswith("ANNOUNCE:"):
                packet = line[len("ANNOUNCE:"):].strip()
                print(f"[Gateway] {line}")
                for i in HEARD_RELAY_DIRECTLY:
                    if i < len(households) and households[i] is not None:
                        print(f"   relay -> H{i + 1}: {packet}")
                        send_line(households[i], packet)
            else:
                print(f"[Gateway] {line}")
    except Exception as exc:
        print(f"Gateway listener error: {exc}")
 
 
def household_loop(i):
    ser = households[i]
    name = f"H{i + 1}"
    try:
        for line in read_lines(ser):
            print(f"[{name}] {line}")
            if line.startswith("FORWARD:"):
                packet = line[len("FORWARD:"):].strip()
                for j in (i - 1, i + 1):                      # chain neighbours
                    if 0 <= j < len(households) and households[j] is not None:
                        print(f"   {name} -> H{j + 1}: {packet}")
                        send_line(households[j], packet)
            elif line.startswith("RECEIVED:") and i == SPEAK_FROM:
                speech_queue.put(line[len("RECEIVED:"):].strip())
    except Exception as exc:
        print(f"{name} listener error: {exc}")
 
 
def send_loop():
    print("Central Control ready. Type an announcement and press Enter ('exit' to quit).")
    while True:
        text = input("Announcement: ").strip()
        if text.lower() in ("exit", "quit"):
            break
        send_line(gateway, text)
        print(f"Sent to Gateway: {text}")
 
 
if __name__ == "__main__":
    threading.Thread(target=speaker_worker, daemon=True).start()
    threading.Thread(target=gateway_loop, daemon=True).start()
    for k, h in enumerate(households):
        if h is not None:
            threading.Thread(target=household_loop, args=(k,), daemon=True).start()
    send_loop()