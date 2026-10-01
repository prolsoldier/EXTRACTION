# Setting up vocals for trap metal, emo trap, rage and hyperpop

These are **generic starting points** from common mixing practice. They are not reconstructions of any artist's chain.

## Who is who (what I could and couldn't verify)
| Artist | What the sources say | Source |
|---|---|---|
| **Lil Peep** | Fans dissecting his vocals say it's "not a matter of reverb or delay, but some kind of distortion"; tutorials exist for FL Studio, Logic and Audition. I found no confirmed chain. | Reddit r/makinghiphop excerpt; YouTube tutorials |
| **ZillaKami** | Described as "more of a growl than a scream"; trap-metal beat tutorials cite City Morgue / ZillaKami / SosMula. Technique write-ups mention fry scream and false-chord approaches. | Reddit r/screaming excerpt; YouTube; a Facebook answer page |
| **Lil Darkie** | "Animated cartoon experimental trap metal artist from Long Beach, California" (Joshua Hamilton). | YouTube description; his SoundCloud lists a "TRAP METAL" track |
| **YNG Martyr** | Australian rapper based in Melbourne (Seaton Rogers); known for a distinctive style and unconventional marketing. | [Wikipedia](https://en.wikipedia.org/wiki/YNG_Martyr) |
| **NIKKO** | A NIKKO appears on SCREAM RAP releases ("SCREAM & NIKKO – STIFF", "GUTS"); SoundCloud/X handle `NIKKO-nrg` / `@NIKKOnrg`. I can't be sure this is the NIKKO you mean. | YouTube, SoundCloud, X search results |
| **Gashum** | "Multi-faceted music artist known for his unique sound that features bass heavy beats, with dark lyrics and vocals" (Genius). SoundCloud: GUTTER (prod. DINCA), GOTH GIRLS (prod. KASUMI), 0837 (feat. Depth Strida, prod. MUTRICK). Apple Music: "Gutter" (2022), "Gas Chamber" (2024). One post describes another artist as "dollbreaker met Gashum" with "distorted production, and aggressive delivery". No published vocal chain found. | Genius, SoundCloud, Apple Music, Instagram results — see `docs/07` |
| **Zedexiah** | **No match found.** Searches returned "Zedekiah" results that look unrelated. Send me a link to a track and I'll build notes from that. | — |

## 1. Tracking setup (do this before any plugin)
- 24-bit, 44.1 or 48 kHz. Buffer 128–256 samples while recording, higher while mixing.
- Set the input gain so loud screams peak around −12 to −6 dBFS. Digital clipping cannot be fixed later; a quiet take can.
- Record **separate tracks** for: main, doubles (same take twice), ad-libs, and each harsh layer. Comp takes before processing.
- Use a pop filter and treat reflections behind you; distortion makes room sound and sibilance louder.
- Monitor with a little reverb in the headphones only, so you don't overdo delivery to compensate for a dry sound.

## 2. Starting chains
Order matters: clean up → control → colour → space.

| Layer | Chain (start here, then trust your ears) |
|---|---|
| **Harsh / growl lead** | Low cut ~90 Hz → compressor (fast attack, ~4:1) → parallel grit: `trapmetal_vocal_grit` Drive 24–30 dB, Blend 25–40 %, Grit high-pass 500 Hz → de-ess around 6–8 kHz → EQ: cut mud 250–400 Hz, lift presence 3–5 kHz → short plate/room reverb, delay throw on phrase ends |
| **Melodic emo-trap lead** | Light tuning (fast retune for the hyperpop end) → low cut ~80 Hz → compression → saturation (tape/tube/`trapmetal_crunch` at low Drive, Tone ~8 kHz) → longer reverb with pre-delay 30–60 ms and a high-passed return → wide delay |
| **Rage-pop / hyperpop lead** | Hard tuning → formant or pitch effect for character → OTT-style multiband on a parallel bus → `trapmetal_vocal_grit` Width 8–14 ms for a stereo spread (check in mono) |
| **Doubles & ad-libs** | Pan the doubles, roll off the top end (LPF ~8 kHz), more distortion and reverb than the lead, and duck the reverb under the lead |
| **Vocal bus** | Gentle glue compression, a touch of saturation, limiter last. Leave 3–6 dB of headroom before mastering. |

Tools: `reaper/jsfx/trapmetal_vocal_grit.jsfx` and `trapmetal_crunch.jsfx` in REAPER; in other DAWs use any saturator and a
short stereo delay to get the same roles. Plugin ideas (Auto-Tune, Little AlterBoy, TrapTune, OTT, Decapitator) are in
`04-scriptable-plugins-and-instruments.md`.

## 3. Check before you print it
- Solo the vocal against the beat at low volume: are the words still clear? If not, lower the grit blend, not the level.
- Fold to mono: does it hollow out? If so, reduce the Haas width.
- A/B against a track you like at matched loudness.

## 4. Look after your voice
Harsh vocal techniques can hurt if done badly (a Reddit thread on trap-metal screaming warns that copying them can be
damaging). Warm up, stay hydrated, keep takes short, stop if it hurts or you go hoarse, and consider a lesson from a vocal
coach who teaches distortion technique.
