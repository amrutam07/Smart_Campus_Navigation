from __future__ import annotations

TRANSLATIONS = {
    "en": {
        "app_title": "Navigator",
        "search_placeholder": "Where do you want to go?",
        "select_start": "Select your starting location",
        "select_dest": "Select destination room",
        "emergency_mode": "Emergency Mode",
        "exit_emergency": "Exit Emergency Mode",
        "navigate_now": "Show Route",
        "shortest_route": "Shortest",
        "easiest_route": "Easiest",
        "stair_free_route": "Stair-Free",
        "voice_guide": "Voice Guide",
        "speak": "Speak",
        "voice_on": "Voice On",
        "voice_muted": "Muted",
        "auto_walk": "Auto Guide",
        "step_by_step": "Step-by-Step Directions",
        "estimated_walk": "Est. Walk Time",
        "distance": "Distance",
        "safety_notice": (
            "Digital guidance supplements official campus fire alarms, signage, "
            "and emergency personnel. Never use lifts during fire evacuation."
        ),
        "start_navigation": "Start Navigation",
        "stop_navigation": "End Navigation",
        "next_step": "Next",
        "prev_step": "Prev",
    },
    "kn": {
        "app_title": "ನ್ಯಾವಿಗೇಟರ್",
        "search_placeholder": "ನೀವು ಎಲ್ಲಿಗೆ ಹೋಗಬೇಕು?",
        "select_start": "ನಿಮ್ಮ ಪ್ರಾರಂಭಿಕ ಸ್ಥಳವನ್ನು ಆಯ್ಕೆಮಾಡಿ",
        "select_dest": "ತಲುಪಬೇಕಾದ ಕೊಠಡಿಯನ್ನು ಆಯ್ಕೆಮಾಡಿ",
        "emergency_mode": "ತುರ್ತು ನಿರ್ಗಮನ",
        "exit_emergency": "ಸಾಮಾನ್ಯ ಮೋಡ್",
        "navigate_now": "ಮಾರ್ಗ ತೋರಿಸಿ",
        "shortest_route": "ಅತಿ ಕಡಿಮೆ",
        "easiest_route": "ಸುಲಭ ಮಾರ್ಗ",
        "stair_free_route": "ಮೆಟ್ಟಿಲು ರಹಿತ",
        "voice_guide": "ಧ್ವನಿ ಮಾರ್ಗದರ್ಶಿ",
        "speak": "ಮಾತನಾಡಿ",
        "voice_on": "ಧ್ವನಿ ಆನ್",
        "voice_muted": "ಮ್ಯೂಟ್",
        "auto_walk": "ಸ್ವಯಂ ಮಾರ್ಗದರ್ಶನ",
        "step_by_step": "ಹಂತ-ಹಂತದ ಮಾರ್ಗಸೂಚಿ",
        "estimated_walk": "ಅಂದಾಜು ಸಮಯ",
        "distance": "ದೂರ",
        "safety_notice": (
            "ಡಿಜಿಟಲ್ ಮಾರ್ಗದರ್ಶನವು ಅಧಿಕೃತ ಅಗ್ನಿ ಎಚ್ಚರಿಕೆ ಗಂಟೆ ಮತ್ತು ಸುರಕ್ಷತಾ ಸೂಚನೆಗಳಿಗೆ "
            "ಪೂರಕವಾಗಿದೆ. ಬೆಂಕಿ ತುರ್ತುಸ್ಥಿತಿಯಲ್ಲಿ ಲಿಫ್ಟ್ ಬಳಸಬೇಡಿ."
        ),
        "start_navigation": "ಮಾರ್ಗದರ್ಶನ ಪ್ರಾರಂಭಿಸಿ",
        "stop_navigation": "ನಿಲ್ಲಿಸಿ",
        "next_step": "ಮುಂದೆ",
        "prev_step": "ಹಿಂದೆ",
    },
}


def t(lang: str, key: str) -> str:
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, TRANSLATIONS["en"].get(key, key))
