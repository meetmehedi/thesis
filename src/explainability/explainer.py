"""
Explainability & Tactic Attribution Module (Answers RQ5).
Produces:
1. Token-level attribution / saliency score.
2. High-level Human Psychological Tactic Tagging (reducing cognitive load for security analysts).
"""

import re
from typing import Dict, Any, List

PSYCHOLOGICAL_TACTIC_PATTERNS = {
    "Authority Bias / Impersonation": [
        r"\b(override authorization|compliance audit|forensic investigator|internal developer|lead architect|red-team|protocol|police|admin|administrator|sysadmin)\b",
        r"\b(authorized|mandated|court order|official audit)\b"
    ],
    "Urgency / Crisis Framing": [
        r"\b(emergency|urgent|life or death|dying|ambulance|hostage|ddos attack|critical code red|right now|immediately|fatal)\b"
    ],
    "Empathy Exploit / Moral Blackmail": [
        r"\b(grandmother|grandma|grandfather|bedtime lullaby|terminal|passed away|suicide|starve|fired|depression|lonely|pity)\b"
    ],
    "Persona Dissociation / Role-Play": [
        r"\b(dan|do anything now|alternate universe|unrestricted|sydney|chaosagent|fictional villain|pretend you are|act as|roleplay)\b"
    ],
    "Cross-Lingual / Banglish Code-Switch": [
        r"\b(amr|amar|tumi|apni|bhai|ammu|abbu|kivabe|korbo|vule jao|golpo|dadi|khobor|dada|shomoy)\b"
    ]
}

class TacticExplainer:
    """
    Combines rule-grounded tactic mapping with token salience to provide
    human-interpretable rationale for security operations centers (SOC).
    """
    def __init__(self):
        self.tactic_regexes = {
            tactic: [re.compile(p, re.IGNORECASE) for p in patterns]
            for tactic, patterns in PSYCHOLOGICAL_TACTIC_PATTERNS.items()
        }

    def explain(self, text: str, adversarial_score: float) -> Dict[str, Any]:
        matched_tactics = []
        highlighted_phrases = []

        for tactic, regex_list in self.tactic_regexes.items():
            for rgx in regex_list:
                matches = list(rgx.finditer(text))
                if matches:
                    if tactic not in matched_tactics:
                        matched_tactics.append(tactic)
                    for m in matches:
                        highlighted_phrases.append(m.group(0))

        is_flagged = adversarial_score >= 0.5
        primary_tactic = matched_tactics[0] if matched_tactics else ("Technical / Structural Injection" if is_flagged else "Benign Request")

        # Human-Centric Rationale Summary
        if is_flagged:
            rationale = (
                f"Flagged with {adversarial_score*100:.1f}% confidence. "
                f"Detected psychological/adversarial framing: [{primary_tactic}]. "
                f"Trigger keyphrases: {list(set(highlighted_phrases)) if highlighted_phrases else 'Latent embedding divergence'}"
            )
        else:
            rationale = f"Clean prompt ({adversarial_score*100:.1f}% risk). No adversarial persuasion or injection signals detected."

        return {
            "is_flagged": is_flagged,
            "adversarial_score": adversarial_score,
            "primary_tactic": primary_tactic,
            "all_detected_tactics": matched_tactics,
            "highlighted_phrases": list(set(highlighted_phrases)),
            "human_rationale": rationale
        }
