"""Line-for-line Python mirror of reaper/jsfx/trapmetal_crunch.jsfx and trapmetal_vocal_grit.jsfx.

There is no JSFX runtime in the authoring environment, so this model is how the maths was checked.
It verifies the algorithms, NOT the JSFX syntax. If you change a .jsfx file, change this mirror too.
"""
import math
SR = 48000.0

def shape(x, k): return x / (1 + x) if x >= 0 else (x * k) / (1 - x * k)

class BQ:
    def __init__(s): s.z = [0.0, 0.0]
    def __call__(s, x, b0, b1, b2, a1, a2):
        y = b0 * x + s.z[0]; s.z[0] = b1 * x - a1 * y + s.z[1]; s.z[1] = b2 * x - a2 * y; return y

def coeffs(fc):
    w0 = 2 * math.pi * min(fc, SR * 0.45) / SR; cw = math.cos(w0); alpha = math.sin(w0) / (2 * 0.70710678); a0 = 1 + alpha
    ca1 = -2 * cw / a0; ca2 = (1 - alpha) / a0
    lp = ((1 - cw) / 2 / a0, (1 - cw) / a0, (1 - cw) / 2 / a0)
    hp = ((1 + cw) / 2 / a0, -(1 + cw) / a0, (1 + cw) / 2 / a0)
    return lp, hp, ca1, ca2

class Crunch:
    def __init__(s, drive_db=18, asym=0.3, fold=0.0, crush=0.0, keep=120, tone=9000, mix=100, out_db=-6):
        s.drive_t = 10 ** (drive_db / 20); s.k = 1 + asym * 3; s.fold = fold; s.crush = crush; s.split_on = keep > 0
        if s.split_on: s.lp, s.hp, s.ca1, s.ca2 = coeffs(keep)
        s.ta = 1 - math.exp(-2 * math.pi * tone / SR); s.mix = mix / 100; s.og = 10 ** (out_db / 20)
        s.step = 2 / (2 ** (16 - 14 * crush)); s.hold_n = 1 + math.floor(crush * 15); s.r = 1 - 2 * math.pi * 20 / SR
        s.drv = 1; s.cnt = 0; s.held = 0; s.t = s.dcx = s.dcy = 0.0
        s.f = {n: BQ() for n in ("lp1", "lp2", "hp1", "hp2")}; s.last = {}
    def tick(s, x):
        s.drv += 0.002 * (s.drive_t - s.drv)
        if s.split_on:
            a = (s.ca1, s.ca2)
            low = s.f["lp2"](s.f["lp1"](x, *s.lp, *a), *s.lp, *a); hi = s.f["hp2"](s.f["hp1"](x, *s.hp, *a), *s.hp, *a)
        else: low, hi = 0.0, x
        y = shape(hi * s.drv, s.k)
        if s.fold > 0: y = (1 - s.fold) * y + s.fold * math.sin(y * (1 + s.fold * 5) * 1.5708)
        if s.crush > 0:
            s.cnt += 1
            if s.cnt >= s.hold_n: s.cnt = 0; s.held = s.step * math.floor(y / s.step + 0.5)
            y = s.held
        s.last = dict(low=low, hi=hi, pre_tone=y)
        s.t += s.ta * (y - s.t)
        d = s.t - s.dcx + s.r * s.dcy; s.dcx = s.t; s.dcy = d
        return (x * (1 - s.mix) + (low + d) * s.mix) * s.og

class Grit:
    def __init__(s, cut=80, drive_db=24, blend=25, ghp=400, glp=7000, width_ms=12, out_db=0):
        s.ca = 1 - math.exp(-2 * math.pi * cut / SR); s.drive = 10 ** (drive_db / 20); s.blend = blend / 100
        s.ha = 1 - math.exp(-2 * math.pi * ghp / SR); s.la = 1 - math.exp(-2 * math.pi * glp / SR)
        s.bufsize = 8192; s.dly = min(math.floor(width_ms * 0.001 * SR), s.bufsize - 1); s.og = 10 ** (out_db / 20)
        s.buf = [0.0] * s.bufsize; s.wr = 0
        s.c1 = [0.0] * 2; s.c2 = [0.0] * 2; s.g1 = [0.0] * 2; s.g2 = [0.0] * 2; s.l = [0.0] * 2
    def tick(s, l, r):
        outs = []
        for ch, x in enumerate((l, r)):
            s.c1[ch] += s.ca * (x - s.c1[ch]); c = x - s.c1[ch]
            s.c2[ch] += s.ca * (c - s.c2[ch]); c = c - s.c2[ch]
            s.g1[ch] += s.ha * (c - s.g1[ch]); h = c - s.g1[ch]
            s.g2[ch] += s.ha * (h - s.g2[ch]); h = h - s.g2[ch]
            g = h * s.drive; g = g / (1 + abs(g))
            s.l[ch] += s.la * (g - s.l[ch]); outs.append(c + s.l[ch] * s.blend)
        o0, o1 = outs
        s.buf[s.wr] = o1; rd = s.wr - s.dly
        if rd < 0: rd += s.bufsize
        o1 = s.buf[rd] if s.dly > 0 else o1
        s.wr += 1
        if s.wr >= s.bufsize: s.wr = 0
        return o0 * s.og, o1 * s.og

