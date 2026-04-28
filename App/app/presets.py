PROMPT_PRESETS = {
    "it_devops": {
        "name": "IT / DevOps",
        "words": [
            "worker", "воркер", "commit", "коммит", "push", "пуш", "pull request", "мерж", "merge", 
            "deploy", "деплой", "feature", "фича", "bug", "баг", "refactoring", "рефакторинг", 
            "devops", "девопс", "docker", "доккер", "kubernetes", "кубернетес", "k8s", "ingress", 
            "cluster", "кластер", "node", "нода", "pod", "под", "pipeline", "пайплайн", "ci/cd", 
            "git", "bash", "python", "script", "скрипт", "environment", "энвайронмент", "staging", 
            "стеджинг", "production", "прод", "master", "branch", "бранч", "hotfix", "хотфикс", 
            "release", "релиз", "frontend", "backend", "fullstack", "endpoint", "эндпоинт", "api", 
            "апи", "json", "yaml", "я мл", "config", "конфиг", "log", "логи", "debug", "дебаг"
        ]
    },
    "designer": {
        "name": "Designer",
        "words": [
            "figma", "фигма", "layout", "лейаут", "mock-up", "макет", "prototype", "прототип", 
            "typography", "типографика", "font", "шрифт", "palette", "палитра", "hex", "rgb", 
            "vector", "вектор", "raster", "растр", "layers", "слои", "mask", "маска", "blend", 
            "opacity", "прозрачность", "gradient", "градиент", "padding", "паддинг", "margin", 
            "маржин", "flex", "grid", "грид", "ui", "ux", "юи", "юикс"
        ]
    }
}

def get_preset_text(preset_key):
    if preset_key in PROMPT_PRESETS:
        return ", ".join(PROMPT_PRESETS[preset_key]["words"])
    return ""
