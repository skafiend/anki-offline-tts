## Conda

Conda is a powerful command line tool for package and environment management. We need it, because chatterbox is finicky about what python version you use.

> The current chatterbox release [0.1.6](https://github.com/resemble-ai/chatterbox/blob/master/pyproject.toml) supports only python 3.10 and 3.11. Using any others will probably cause a lot of import/dependency errors.

`conda` installers for Linux, Windows and MacOS are available on [their website](https://www.anaconda.com/download/success?reg=skipped). Just choose minimal installer (Miniconda) and run it with default parameters. On Linux/MacOS you need to make the file executable first `chmod +x Miniconda3-latest-Linux-x86_64.sh`. 

[How to install miniconda](https://www.anaconda.com/docs/getting-started/miniconda/install)

## Setting up ChatterboxTTS

### Create virtual environment

```bash
conda create -yn chatterbox python=3.11
conda activate chatterbox

pip install chatterbox-tts
```

> You can also use full paths instead of the name of the environment:

```bash
conda activate C:\Users\test\miniconda3\envs\chatterbox_test
```

### Download model

- ChatterboxMultilingualTTS and ChatterboxTTS

> ChatterboxTTS supports only English, but it adds fewer artifacts than ChatterboxMultilingualTTS. 

```bash
python3 -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='ResembleAI/chatterbox', local_dir='chatterbox')"
```

 - Chatterbox Turbo
   
> I don't use it, because even though it does generate faster than the original model, the audio samples sound more robotic.

```bash
python3 -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='ResembleAI/chatterbox-turbo', local_dir='chatterbox-turbo')"
```

## Test

 Try running the following script in the virtual environment. It should generate an audio file in the same folder:
 
 ```bash
HF_HUB_OFFLINE=1 python example.py 
 ```

### example.py
```python
import torchaudio as ta
import torch
from chatterbox.tts import ChatterboxTTS

# Automatically detect the best available device
if torch.cuda.is_available():
    device = "cuda"
elif torch.backends.mps.is_available():
    device = "mps"
else:
    device = "cpu"

print(f"Using device: {device}")

model_path = "/absolute/path/to/the/model"
model = ChatterboxTTS.from_local(ckpt_dir=model_path, device=device)

text = "Ezreal and Jinx teamed up with Ahri, Yasuo, and Teemo to take down the enemy's Nexus in an epic late-game pentakill."
wav = model.generate(text)
ta.save("test-1.wav", wav, model.sr)
```

## Errors

#### TypeError: 'NoneType' object is not callable

 Perth v1.0.1: https://github.com/resemble-ai/chatterbox/issues/198

```bash
    self.watermarker = perth.PerthImplicitWatermarker()
                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
TypeError: 'NoneType' object is not callable
```

## Setting up add-on

### Flatpak

- The addon requires `flatpak-spawn` to run the external python script to generate audio. On Fedora you can simply install it by running this command in the terminal:

```bash
sudo dnf install flatpak-spawn
```

- You need to add extra permissions to the filesystem to avoid lines like `/run/user/1000/doc/ea9d1517/python` while setting up the paths to a virtual environment and the model
```
flatpak override --user net.ankiweb.Anki --filesystem=<path to>/models/chatterbox/:ro --filesystem=<path to>/virt_env/chatterbox/:ro
```

## Acknowledgements & Citations

This project uses the following datasets and models:

### Chatterbox-TTS
The addon uses **Chatterbox-TTS** to generate audio files:

```bibtex
@misc{chatterboxtts2025,
  author       = {{Resemble AI}},
  title        = {{Chatterbox-TTS}},
  year         = {2025},
  howpublished = {\url{https://github.com/resemble-ai/chatterbox}},
  note         = {GitHub repository}
}
```

### The LJ Speech Dataset
A portion of this dataset was used in the project:

```bibtex
@misc{ljspeech17,
  author       = {Keith Ito and Linda Johnson},
  title        = {The LJ Speech Dataset},
  howpublished = {\url{https://keithito.com}},
  year         = 2017
}
```
