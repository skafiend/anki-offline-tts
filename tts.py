import torchaudio as ta
import torch
import sys
import os

from chatterbox.tts import ChatterboxTTS
# from chatterbox.mtl_tts import ChatterboxMultilingualTTS

languages = {
    "Arabic": "ar",
    "Danish": "da",
    "German": "de",
    "Greek": "el",
    "English": "en",
    "Spanish": "es",
    "Finnish": "fi",
    "French": "fr",
    "Hebrew": "he",
    "Hindi": "hi",
    "Italian": "it",
    "Japanese": "ja",
    "Korean": "ko",
    "Malay": "ms",
    "Dutch": "nl",
    "Norwegian": "no",
    "Polish": "pl",
    "Portuguese": "pt",
    "Russian": "ru",
    "Swedish": "sv",
    "Swahili": "sw",
    "Turkish": "tr",
    "Chinese": "zh",
}


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

        # model = ChatterboxMultilingualTTS.from_local(ckpt_dir=model_path, device=device)
        model = ChatterboxTTS.from_local(ckpt_dir=model_path, device=device)
        audio = model.generate(
            text,
            exaggeration=float(exaggeration),
            temperature=float(temperature),
            cfg_weight=float(cfg_weight),
            audio_prompt_path=os.path.join(
                os.path.dirname(__file__),
                "user_files",
                f"{voice}",
            ),
            # language_id=language_dict.get(language),
        )

        ta.save(file, audio, model.sr)

    except Exception as e:
        print(f"{__file__}: {str(e)}", file=sys.stderr)
        sys.exit(67)


if __name__ == "__main__":
    main()
