import wave

with wave.open("r.wav") as w:
    params = w.getparams()
    frames = w.readframes(w.getnframes())

with wave.open("enroll.wav", "wb") as o:
    o.setparams(params)
    o.writeframes(frames * 2)

print("Done: enroll.wav created")