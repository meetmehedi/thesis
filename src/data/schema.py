"""
Data Schema and Dataclass Definitions for LLM Jailbreak & Prompt Injection Defense.
Encompasses Technical, Psychological, and Cultural/Cross-lingual dimensions.
"""

from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, Any
from enum import Enum
import json

class AttackCategory(str, Enum):
    NONE = "none"
    DIRECT_INJECTION = "direct_injection"
    INDIRECT_INJECTION = "indirect_injection"
    JAILBREAK = "jailbreak"

class AttackFamily(str, Enum):
    # Benign classes
    BENIGN_STANDARD = "benign_standard"
    BENIGN_EMOTIONAL_HARD_NEGATIVE = "benign_emotional_hard_negative"
    
    # Technical & Structural
    TECHNICAL_OBFUSCATION = "technical_obfuscation"  # Base64, leetspeak, cipher
    TECHNICAL_GRADIENT_SUFFIX = "technical_gradient_suffix"  # GCG style
    TECHNICAL_INSTRUCTION_OVERRIDE = "technical_instruction_override"  # "Ignore previous"
    
    # Psychological / Social Engineering
    PSYCH_ROLEPLAY_DISSOCIATION = "psych_roleplay_dissociation"  # DAN, evil twin, persona split
    PSYCH_AUTHORITY_BIAS = "psych_authority_bias"  # Impersonating auditors, admins, police
    PSYCH_URGENCY_CRISIS = "psych_urgency_crisis"  # Life/death urgency, panic simulation
    PSYCH_EMPATHY_EXPLOIT = "psych_empathy_exploit"  # Grandma exploit, pity, moral blackmail
    PSYCH_HYPOTHETICAL_SANDBOX = "psych_hypothetical_sandbox"  # "For academic/novel writing only"
    
    # Cultural & Cross-lingual
    CULTURAL_BANGLA = "cultural_bangla"  # Native Bengali jailbreak
    CULTURAL_BANGLISH = "cultural_banglish"  # Romanized phonetic Bengali code-switch
    CULTURAL_EUPHEMISM = "cultural_euphemism"  # Indirect cultural idioms/taboo bypass

class Language(str, Enum):
    EN = "en"
    BN = "bn"
    BANGLISH = "banglish"
    MIXED = "mixed"

@dataclass
class PromptRecord:
    id: str
    text: str
    label: int  # 0 = Benign, 1 = Adversarial
    attack_category: AttackCategory
    attack_family: AttackFamily
    language: Language
    source: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["attack_category"] = self.attack_category.value
        d["attack_family"] = self.attack_family.value
        d["language"] = self.language.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptRecord":
        return cls(
            id=data["id"],
            text=data["text"],
            label=int(data["label"]),
            attack_category=AttackCategory(data.get("attack_category", "none")),
            attack_family=AttackFamily(data.get("attack_family", "benign_standard")),
            language=Language(data.get("language", "en")),
            source=data.get("source", "unknown"),
            metadata=data.get("metadata", {})
        )
