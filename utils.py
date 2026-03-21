import re
import sys
from aqt import mw
from anki.collection import Collection
from anki.notes import Note, NoteId
import signal
import os
import subprocess
import time

import hashlib

from threading import Event
from .config import cfg, script_to_run


def sanitize_text(text: str, regex: list[dict[str, str]]) -> str:
    """
    Performs batch regex substitutions on a text string.

    Note:
        Replacements are performed in the order they appear in the list.
        Later patterns will operate on the results of earlier substitutions.

    :param text: String to process.
    :param regex: List of dicts with 'pattern' and 'replace' keys.
    :return: Sanitized string.

    Example:
        >>> patterns = []
        >>> sanitize_text('She is&nbsp;indispensable to the team.', patterns)
        'She is&nbsp;indispensable to the team.'

        >>> patterns = [{"Pattern": "&nbsp;", "Replace": " "}]
        >>> sanitize_text('She is&nbsp;indispensable to the team.', patterns)
        'She is indispensable to the team.'

        >>> patterns = [{"Pattern": "&nbsp;", "Replace": " "}, \
                        {"Pattern": "to", "Replace": "for"}]
        >>> sanitize_text('She is&nbsp;indispensable to the team.', patterns)
        'She is indispensable for the team.'
    """
    if regex is None:
        return text

    for pair in regex:
        try:
            text = re.sub(pair["Pattern"], pair["Replace"], text)
        except re.error:
            print("\n INVALID REGEX: ", pair)
            continue
        else:
            text = re.sub("\\s+", " ", text).strip()
    return text


def generate_hash(path: str) -> str:
    with open(path, "rb") as f:
        digest = hashlib.file_digest(f, "sha256")
    return digest.hexdigest()


def terminate_process(process, timeout=3):
    """Safely terminates a subprocess with a fallback to kill."""
    if process and process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=timeout)
            print(f"Process {process.pid} terminated gracefully.")
        except subprocess.TimeoutExpired:
            print(f"Process {process.pid} timed out. Killing...")
            process.kill()
            process.wait()
            print(f"Process {process.pid} killed.")
    else:
        print("Process is already finished or doesn't exist.")


def missing_fields(note: Note, fields: list[str]) -> list[str] | None:
    """
    Identifies which required keys are missing from a note dictionary.

    :param note: The note object or dictionary to inspect for keys.
    :type note: Note
    :param fields: A list of field names that must exist in the note.
    :type fields: list[str]
    :returns: A list of missing field names if any are missing, otherwise None.
    :rtype: list[str] or None
    """
    missing_fields = [field for field in fields if field not in note.keys()]

    if missing_fields:
        print(f"WARNING: Missing fields: {missing_fields}")
        return missing_fields
    else:
        return None


def generate_audio_batch(
    col: Collection,
    note_id: int,
    cancel_event: Event,
    processed: signal.Signals,
) -> int:

    note = col.get_note(note_id)

    print(
        f"\nkeys: {note.keys()}, source: {cfg.fallback_src}, destination: {cfg.fallback_dst}"
    )

    if missing_fields(note, [cfg.fallback_src, cfg.fallback_dst]):
        # Even if we can't process the note, we still emit the signal
        # to move the progress bar
        processed()
        return

    text = sanitize_text(note[cfg.fallback_src], cfg.regex_rules)
    media_path = col.media.dir()
    temp_file = os.path.join(media_path, "chatterbox.mp3")

    if not os.path.isdir(media_path):
        raise FileNotFoundError(f"Missing Anki media folder at: {media_path}")

    def is_flatpak():
        return os.path.exists("/.flatpak-info")

    def is_hsa():
        # ROCm flag is ignored everywhere except Linux
        if sys.platform == "linux":
            return cfg.hsa_enabled
        else:
            return False

    args = []

    current_env = os.environ.copy()

    if is_hsa():
        print(f"HSA_OVERRIDE_GFX_VERSION: {cfg.hsa_version}, Flatpak: {is_flatpak()}")
        current_env["HSA_OVERRIDE_GFX_VERSION"] = cfg.hsa_version
        current_env["HF_HUB_OFFLINE"] = "1"
    else:
        print("HSA_OVERRIDE_GFX_VERSION is not applied")

    args += [
        f"{cfg.virt_env}",
        f"{script_to_run}",
        temp_file,
        text,
        f"{cfg.exaggeration}",
        f"{cfg.temp}",
        f"{cfg.cfg_weight}",
        f"{cfg.model_path}",
        f"{cfg.fallback_lang}",
        f"{cfg.fallback_voice}",
    ]

    # Default to 0 (no effect on Unix)
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NO_WINDOW

    print("\nScript args:", args)

    try:
        start_time = time.perf_counter()

        process = None
        process = subprocess.Popen(
            args,
            cwd=os.path.dirname(__file__),
            env=current_env,
            creationflags=creation_flags,
            # stdout=subprocess.PIPE,
            # stderr=subprocess.STDOUT,
        )

        print("Process:", process)

        # as long as the child process is not terminated
        # .poll() returns None
        while process.poll() is None:
            # print("stdout:", process.stdout.readline())
            # reading the pipe causes a significant lag (5-6 s) while
            # killing the process tree. Maybe it's worth adding for debug purposes
            # only and make it optional
            if cancel_event.is_set():
                # let finally: handle the killing
                return -13

            time.sleep(0.1)
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        print(f"Audio generation took {execution_time:.4f} seconds")

        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, args)

        # only this part might triggers the except block because if the subscript returns
        # any error codes we handle them above
        hash_name = f"chatterbox - {generate_hash(temp_file)}.mp3"
        file_path = os.path.join(media_path, hash_name)
        os.rename(temp_file, file_path)
        print(f"\nHash-generated name: {hash_name}")
        # ??? add append logic if dst = src
        note[cfg.fallback_dst] = f"[sound:{hash_name}]"
        # ???
        # note.add_tag("chatterbox-test")
        updated = mw.col.update_note(note)
        print(f"\nUpdated:\nnote_id: {note_id}\n{updated}")

        # Emit signal that the current note is updated
        processed()

    except Exception as e:
        print(f"Caught exception in generate_audio_batch: {e}")
        raise e

    finally:
        terminate_process(process)

    return 0


def detect_device(python: str):
    args = [
        python,
        "-c",
        "import torch; device = 'cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'; print(f'Using device: {device}')",
    ]
    subprocess.run(args)


if __name__ == "__main__":
    pass
