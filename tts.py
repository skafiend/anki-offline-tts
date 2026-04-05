import torchaudio as ta
import torch
import sys
import os

from chatterbox.tts import ChatterboxTTS
from chatterbox.mtl_tts import ChatterboxMultilingualTTS


dir_path = os.path.dirname(os.path.abspath(__file__))

if dir_path not in sys.path:
    sys.path.append(dir_path)

from constants import languages


def main():
    try:
        if torch.cuda.is_available():
            device = "cuda"
        elif torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"

        print(f"\nDevice: {device}\n")

        file = sys.argv[1]
        text = sys.argv[2]
        exaggeration = sys.argv[3]
        temperature = sys.argv[4]
        cfg_weight = sys.argv[5]
        model_path = sys.argv[6]
        language = sys.argv[7]
        voice = sys.argv[8]

        options = {
            "exaggeration": float(exaggeration),
            "temperature": float(temperature),
            "cfg_weight": float(cfg_weight),
        }

        if voice != "default":
            options["audio_prompt_path"] = os.path.join(
                os.path.dirname(__file__), "user_files", f"{voice}"
            )

        if language == "English":
            print("\nUsing the original model")
            model = ChatterboxTTS.from_local(ckpt_dir=model_path, device=device)
        else:
            print("\nUsing the multilingual model")
            model = ChatterboxMultilingualTTS.from_local(
                ckpt_dir=model_path, device=device
            )
            options["language_id"] = languages.get(language)

        audio = model.generate(
            text,
            **options,
        )

        ta.save(file, audio, model.sr)

    except Exception as e:
        print(f"{__file__}: {str(e)}", file=sys.stderr)
        sys.exit(67)


if __name__ == "__main__":
    main()
