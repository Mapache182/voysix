import re


WAKE_WORD = "voisyx"
WAKE_WORD_ALIASES = (
    "voisyx",
    "voicex",
    "voice x",
    "voiceex",
    "voysix",
    "войсикс",
    "воисикс",
    "войс икс",
    "воис икс",
)

VOICE_ACTION_PROMPT = (
    "If the user says the wake word, transcribe it exactly as 'voisyx'. "
    "Examples: 'voisyx, поставь таймер на 5 минут', "
    "'voisyx, timer for 30 seconds'."
)


def build_voice_prompt(base_prompt, enabled=True):
    if not enabled:
        return base_prompt

    base_prompt = (base_prompt or "").strip()
    if WAKE_WORD in base_prompt.lower():
        return base_prompt
    if base_prompt:
        return f"{base_prompt} {VOICE_ACTION_PROMPT}"
    return VOICE_ACTION_PROMPT


def parse_voice_action(text, config):
    if not config.get("voice_actions_enabled", True):
        return None

    text = (text or "").strip()
    if not text:
        return None

    command = _strip_wake_word(text)
    if command is None:
        return None

    lowered = command.lower().strip(" .,!?:;")
    if config.get("voice_timers_enabled", True):
        timer_action = _parse_timer(lowered)
        if timer_action:
            timer_action["raw_text"] = text
            return timer_action

    return {
        "type": "unknown",
        "raw_text": text,
        "command": command.strip(),
    }


def _strip_wake_word(text):
    lowered = text.lower().strip()
    for alias in WAKE_WORD_ALIASES:
        pattern = rf"^\s*{re.escape(alias)}[\s,.:;!-]*"
        if re.match(pattern, lowered, flags=re.IGNORECASE):
            return re.sub(pattern, "", text, count=1, flags=re.IGNORECASE)
    return None


def _parse_timer(command):
    cancel_words = (
        "отмени",
        "отменить",
        "сбрось",
        "сбросить",
        "cancel",
        "stop",
    )
    timer_words = ("таймер", "timer")

    if any(word in command for word in timer_words) and any(word in command for word in cancel_words):
        return {"type": "timer_cancel_all"}

    if not any(word in command for word in timer_words):
        return None

    match = re.search(
        r"(\d+|один|одну|два|две|три|четыре|пять|шесть|семь|восемь|девять|десять)\s*"
        r"(секунд(?:у|ы)?|сек|seconds?|secs?|минут(?:у|ы)?|мин|minutes?|mins?|час(?:а|ов)?|hours?|hrs?)",
        command,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    amount = _parse_number(match.group(1))
    unit = match.group(2).lower()
    if amount <= 0:
        return None

    multiplier = 1
    if unit.startswith(("мин", "minute", "min")):
        multiplier = 60
    elif unit.startswith(("час", "hour", "hr")):
        multiplier = 3600

    seconds = amount * multiplier
    if seconds > 24 * 3600:
        return {
            "type": "timer_too_long",
            "seconds": seconds,
        }

    return {
        "type": "timer_start",
        "seconds": seconds,
        "label": _format_duration(seconds),
    }


def _parse_number(value):
    value = value.lower()
    if value.isdigit():
        return int(value)

    words = {
        "один": 1,
        "одну": 1,
        "два": 2,
        "две": 2,
        "три": 3,
        "четыре": 4,
        "пять": 5,
        "шесть": 6,
        "семь": 7,
        "восемь": 8,
        "девять": 9,
        "десять": 10,
    }
    return words.get(value, 0)


def _format_duration(seconds):
    seconds = int(seconds)
    if seconds % 3600 == 0:
        amount = seconds // 3600
        return f"{amount} h"
    if seconds % 60 == 0:
        amount = seconds // 60
        return f"{amount} min"
    return f"{seconds} sec"
