from aqt import mw


class Parameter:
    def __init__(self, keys: list[str]) -> None:
        self.keys = keys

    # obj reffers to the instance of the class and since we're using a singleton
    # all the instances of the class are the same.
    def __get__(self, obj: "ConfigManager", type=None) -> object:
        value = obj.config
        for key in self.keys:
            value = value[key]
        return value

    def __set__(self, obj: "ConfigManager", value):
        temp = obj.config
        # find the dictionary than actually contains the key
        for key in self.keys[:-1]:
            temp = temp[key]
        temp[self.keys[-1]] = value

        mw.addonManager.writeConfig(__name__, obj.config)


class ConfigManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            # get access to the obj.__new__() of object Class
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        self.config = mw.addonManager.getConfig(__name__)
        if self.config is None:
            raise ValueError("config.json/meta.json contains typos or doesn't exist!!!")

    def save(self):
        mw.addonManager.writeConfig(__name__, self.config)

    virt_env = Parameter(["settings", "virt_env"])
    hsa_version = Parameter(["settings", "hsa", "ver"])
    hsa_enabled = Parameter(["settings", "hsa", "enabled"])
    preserve_audio = Parameter(["preserve_audio"])
    regex_rules = Parameter(["regex_rules"])
    presets = Parameter(["presets"])
    exaggeration = Parameter(["model", "exaggeration"])
    cfg_weight = Parameter(["model", "cfg_weight"])
    temp = Parameter(["model", "temp"])
    model_path = Parameter(["model", "path"])


cfg = ConfigManager()
