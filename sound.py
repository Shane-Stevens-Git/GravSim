"""Procedural collision sounds (no audio files): tones and noise bursts
synthesized with numpy. Heavier bodies sound lower. If there's no audio
device, everything silently turns into no-ops."""
import math

import numpy as np
import pygame

from config import *

RATE = 44100


class Sound:
    def __init__(self):
        self.enabled = False
        self.rate, self.channels = RATE, 2
        self.cache = {}
        self.last = {}
        try:
            # allowedchanges=0: ask SDL to convert to our format instead of
            # picking the device's own (some Windows devices are 6- or 8-channel).
            try:
                pygame.mixer.init(frequency=RATE, size=-16, channels=2, buffer=512,
                                  allowedchanges=0)
            except TypeError:                       # older pygame without allowedchanges
                pygame.mixer.init(frequency=RATE, size=-16, channels=2, buffer=512)
            # Build sounds for whatever format we actually got.
            self.rate, _size, self.channels = pygame.mixer.get_init()
            pygame.mixer.set_num_channels(16)
            self.enabled = SOUND_ON
            self.available = True
        except pygame.error:
            self.available = False

    def toggle(self):
        if self.available:
            self.enabled = not self.enabled
        return self.enabled

    def _make(self, kind, freq):
        RATE = self.rate
        n = int(RATE * {"merge": 0.35, "shatter": 0.45, "bounce": 0.12, "tidal": 0.9}[kind])
        t = np.arange(n) / RATE
        rng = np.random.default_rng(int(freq))
        if kind == "merge":            # soft low thump with a quick pitch drop
            f = freq * (1 + 0.6 * np.exp(-t * 30))
            wave = np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t * 9)
        elif kind == "bounce":         # short wooden tock
            wave = np.sin(2 * np.pi * freq * 2.5 * t) * np.exp(-t * 45)
        elif kind == "shatter":        # crunchy noise burst over a low thud
            noise = rng.normal(0, 1, n)
            noise = np.convolve(noise, np.ones(6) / 6, mode="same")      # soften the hiss
            wave = (0.7 * noise * np.exp(-t * 11) +
                    0.6 * np.sin(2 * np.pi * freq * 0.7 * t) * np.exp(-t * 7))
        else:                          # tidal: falling, wobbling whoosh
            f = freq * 1.5 * np.exp(-t * 1.8)
            wave = (np.sin(2 * np.pi * np.cumsum(f) / RATE) * 0.5 +
                    np.convolve(rng.normal(0, 1, n), np.ones(40) / 40, "same") * 1.5)
            wave *= np.sin(np.pi * t / t[-1])                             # swell in and out
        attack = np.minimum(1, t / 0.004)                                 # no click
        wave = wave * attack
        wave /= max(np.max(np.abs(wave)), 1e-9)
        pcm = (wave * 32767 * 0.8).astype(np.int16)
        if self.channels == 1:
            return pygame.sndarray.make_sound(pcm)
        return pygame.sndarray.make_sound(np.ascontiguousarray(
            np.repeat(pcm[:, None], self.channels, axis=1)))

    def play(self, kind, mass, strength):
        """kind: merge / shatter / bounce / tidal. Pitch from mass, volume
        from impact strength. Rate-limited so swarms don't roar."""
        if not self.enabled:
            return
        now = pygame.time.get_ticks()
        if now - self.last.get(kind, -1000) < 70:
            return
        self.last[kind] = now
        freq = min(max(180 * (20 / max(mass, 0.01)) ** 0.22, 45), 700)
        freq = round(freq / 10) * 10                                      # cache buckets
        key = (kind, freq)
        if key not in self.cache:
            try:
                self.cache[key] = self._make(kind, freq)
            except (ValueError, pygame.error):     # odd audio device: go silent, don't crash
                self.enabled = self.available = False
                return
        vol = min(max(0.15 + 0.08 * math.log10(max(strength, 1.0)), 0.15), 0.8) * SOUND_VOLUME
        channel = self.cache[key].play()
        if channel is not None:
            channel.set_volume(vol)
