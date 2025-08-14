# scanimation-generator
create the base image for scanimation use.

# Scanimation Base Generator (Pillow)

Generate an interlaced “scanimation” base image from a sequence of frames, plus an optional grille mask.

## Install
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

## Input
Put your ordered frames into ./frames (natural sort: 1,2,10…).
