import os
import sys
import platform

from aqt import mw

script_to_run = "tts.py"
# script_to_run = "tts_turbo.py"


def load_psutil():
    """
    Dynamically adds the platform-specific psutil library path to sys.path.

    This function detects the current operating system and architecture to
    locate the appropriate pre-compiled psutil binaries within the 'lib'
    directory. It supports Windows (x64), Linux (x64), and macOS (Intel/ARM).

    Raises:
        ImportError: If the current platform is not supported.
    """
    base_path = os.path.dirname(__file__)
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        folder = "win_amd64"
    elif system == "linux":
        folder = "manylinux2014_x86_64"
    elif system == "darwin":  # macOS
        folder = "macosx_11_0_arm64" if "arm" in machine else "macosx_10_9_x86_64"
    else:
        raise ImportError(f"psutils are not supported on the platform {system}")

    lib_path = os.path.join(base_path, "lib", folder)

    if lib_path not in sys.path:
        sys.path.insert(0, lib_path)


class ConfigManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        self.config = mw.addonManager.getConfig(__name__)
        if self.config is None:
            raise ValueError("config.json/meta.json contains typos or doesn't exist!!!")

    @property
    def virt_env(self):
        return self.config["settings"]["virt_env"]

    @virt_env.setter
    def virt_env(self, value):
        self.config["settings"]["virt_env"] = value
        self.save()

    @property
    def hsa_version(self):
        return self.config["settings"]["hsa"]["ver"]

    @hsa_version.setter
    def hsa_version(self, value):
        self.config["settings"]["hsa"]["ver"] = value
        self.save()

    @property
    def hsa_enabled(self):
        return self.config["settings"]["hsa"]["enabled"]

    @hsa_enabled.setter
    def hsa_enabled(self, value):
        self.config["settings"]["hsa"]["enabled"] = value
        self.save()

    @property
    def regex_rules(self):
        return self.config["regex_rules"]

    @regex_rules.setter
    def regex_rules(self, value):
        self.config["regex_rules"] = value
        self.save()

    @property
    def presets(self):
        return self.config["presets"]

    @property
    def fallback_src(self):
        return self.config["presets"]["fallback"]["source"]

    @fallback_src.setter
    def fallback_src(self, value):
        self.config["presets"]["fallback"]["source"] = value
        cfg.save()

    @property
    def fallback_dst(self):
        return self.config["presets"]["fallback"]["destination"]

    @fallback_dst.setter
    def fallback_dst(self, value):
        self.config["presets"]["fallback"]["destination"] = value
        cfg.save()

    @property
    def fallback_lang(self):
        return self.config["presets"]["fallback"]["language"]

    @property
    def fallback_voice(self):
        return self.config["presets"]["fallback"]["voice"]

    @property
    def exaggeration(self):
        return self.config["model"]["exaggeration"]

    @exaggeration.setter
    def exaggeration(self, value):
        self.config["model"]["exaggeration"] = value
        cfg.save()

    @property
    def cfg_weight(self):
        return self.config["model"]["cfg_weight"]

    @cfg_weight.setter
    def cfg_weight(self, value):
        self.config["model"]["cfg_weight"] = value
        cfg.save()

    @property
    def temp(self):
        return self.config["model"]["temp"]

    @temp.setter
    def temp(self, value):
        self.config["model"]["temp"] = value
        cfg.save()

    @property
    def model_path(self):
        return self.config["model"]["path"]

    @model_path.setter
    def model_path(self, value):
        self.config["model"]["path"] = value
        cfg.save()

    def save(self):
        mw.addonManager.writeConfig(__name__, self.config)


cfg = ConfigManager()


print("\nCONSTANTS:")
print("Path to Python Executable:", cfg.virt_env)
print(f"HSA Version Override: {cfg.hsa_version}, Enabled: {cfg.hsa_enabled}")
print("Presets:", cfg.presets)
print("Text Processing Rules:", cfg.regex_rules)
