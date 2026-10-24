#!/usr/bin/env python3
import wave
import sys

def wav_to_pcm_be(wav_path, pcm_path):
    with wave.open(wav_path, "rb") as w:
        nch = w.getnchannels()
        sampwidth = w.getsampwidth()
        fr = w.getframerate()

        if sampwidth != 2:
            raise ValueError("16bit PCM 以外は未対応です")
        if fr != 44100:
            print(f"警告: サンプリング周波数が 44100Hz ではありません ({fr}Hz)")

        frames = w.readframes(w.getnframes())

    # Little-endian → Big-endian に変換
    # 2byte 単位でひっくり返す
    pcm_be = bytearray()
    for i in range(0, len(frames), 2):
        lo = frames[i]
        hi = frames[i+1]
        pcm_be.append(hi)
        pcm_be.append(lo)

    with open(pcm_path, "wb") as f:
        f.write(pcm_be)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: wav_to_pcm_be.py input.wav output.pcm")
        sys.exit(1)

    wav_to_pcm_be(sys.argv[1], sys.argv[2])
