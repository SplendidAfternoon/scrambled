"""Single source of truth for the piece's structure (seconds). Audio and video both read this."""

FPS = 30
W, H = 1080, 1350          # 4:5; top 1080x1080 is the image field, bottom 270 px the data panel
BPM = 90
STEP_S = 60 / BPM / 4      # one echo step t = one sixteenth note at 90 bpm (32 steps = 2 bars)

# name, start, end, measured run, act card text
SEGMENTS = [
    ("intro", 0.0, 6.0, None),
    ("control", 6.0, 26.0, "control_clifford_n12"),
    ("lowx", 26.0, 48.0, "lowx_n12"),
    ("scrambling", 48.0, 78.0, "scrambling_n12"),
    ("end", 78.0, 88.0, None),
]
DURATION = SEGMENTS[-1][2]
CARD_S = 3.0               # act card length at the start of each act
XFADE_S = 1.0

ACT_TEXT = {
    "control": ("I", "A circuit that cannot scramble",
                "Clifford coupling. The nudge never leaves its qubit; every other echo returns intact."),
    "lowx": ("II", "A gentle drive",
             "Weak transverse kick. The nudge creeps outward at about 0.3 qubits per step; echoes fade slowly."),
    "scrambling": ("III", "Scrambling",
                   "Stronger kick. The nudge races through the chain, echoes invert and erase, "
                   "then partly return as the wave reflects off the ends of the chain."),
}
ACT_PARAMS = {
    "control": "θx = 0.3π · θzz = π (Clifford)",
    "lowx": "θx = 0.1π · θzz = 0.35π",
    "scrambling": "θx = 0.3π · θzz = 0.35π",
}

# stem (media/stem_full.wav, 58 s) window used under each act
STEM_WINDOW = {"intro": (0.0, 6.0), "control": (2.0, 22.0), "lowx": (16.0, 38.0),
               "scrambling": (26.0, 56.0), "end": (48.0, 58.0)}


def segment(name):
    for s in SEGMENTS:
        if s[0] == name:
            return s
    raise KeyError(name)
