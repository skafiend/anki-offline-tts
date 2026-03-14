import torchaudio as ta
import torch
import sys

from chatterbox.tts_turbo import ChatterboxTurboTTS


def main():
    try:
        if torch.cuda.is_available():
            device = "cuda"
        elif torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"

        print(f"\nDevice: {device}")

        model = ChatterboxTurboTTS.from_local(
            ckpt_dir="/media/stuff/Development/models/chatterbox-turbo", device=device
        )

        print("model:", model)

        file = sys.argv[1]
        text = sys.argv[2]

        audio = model.generate(text)
        print("audio:", audio)

        ta.save(file, audio, model.sr)

    except Exception as e:
        print(f"{__file__}: {str(e)}", file=sys.stderr)
        sys.exit(67)


if __name__ == "__main__":
    main()
