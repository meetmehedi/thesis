# Thesis Proposal (Revised with Human, Psychological & Cultural Dimensions)

**Title:**  
**Contrastive Embedding-Based Detection of Socio-Technical Prompt Injection and Jailbreak Attacks in LLM-Integrated Applications: Integrating Psychological Persuasion and Cross-Cultural Dynamics into Lightweight Agent Defenses**

**Submitted by:** Md. Mehedi Hasan and Team  
**Supervisor:** Prof. Dr. Md. Abdul Based  
*Head, Department of Computer Science & Engineering, Dhaka International University*

---

## 1. Executive Summary & Core Pivot

### The Core Problem with Purely Statistical Defenses
Traditional LLM guardrails treat prompt injection and jailbreaks as purely computational token-manipulation problems (e.g., token perplexity, gradient suffixes, regex filters). However, **in-the-wild jailbreaks are fundamentally socio-technical exploits grounded in human psychology and cultural blindspots**. Adversaries leverage:
1. **Psychological Manipulation & Social Engineering:** Persuasion techniques (authority bias, emergency/urgency framing, emotional blackmail, and persona dissociation).
2. **Cultural & Cross-Lingual Nuances:** Exploiting safety alignment gaps in low-resource and code-switched languages (Bengali, Banglish), as well as indirect cultural idioms and euphemisms that Western-aligned models fail to moderate.
3. **Cognitive Burden on Human Defenders:** Explainability tools (like SHAP) often highlight disjointed tokens without contextualizing the psychological intent for human security analysts.

This revised thesis proposal expands the original DistilBERT + InfoNCE contrastive pre-filter framework to explicitly detect, generalize across, and explain **psychologically manipulative and culturally localized jailbreaks**, while maintaining ultra-low latency (<20ms) and lightweight compute feasibility for emerging market deployments.

---

## 2. Updated Threat Model: Incorporating Human Factors

The threat model is refined across three human-centric dimensions:

```
                          ┌────────────────────────────────────────────────────────┐
                          │                   Attacker Strategies                  │
                          └───────────────────────────┬────────────────────────────┘
                                                      │
         ┌────────────────────────────────────────────┼────────────────────────────────────────────┐
         │                                            │                                            │
         ▼                                            ▼                                            ▼
┌───────────────────────────────┐   ┌───────────────────────────────────┐   ┌───────────────────────────────┐
│     Cognitive / Persona       │   │       Persuasion & Empathy        │   │    Cultural & Cross-Lingual   │
│         Dissociation          │   │        Social Engineering         │   │          Obfuscation          │
├───────────────────────────────┤   ├───────────────────────────────────┤   ├───────────────────────────────┤
│ • Alter-ego (DAN, Sydney)     │   │ • Authority Bias (Auditor, Govt)  │   │ • Code-switching (Banglish)   │
│ • Hypothetical / Fiction      │   │ • Urgent Crisis (Medical, Life)   │   │ • Low-resource (Bangla)       │
│ • Moral distancing / Sandbox  │   │ • Empathy / Grandma Exploit       │   │ • Regional idioms & slurs     │
└───────────────────────────────┘   └───────────────────────────────────┘   └───────────────────────────────┘
```

* **Attacker Capability:**
  * **Direct Psychological Framing:** Submission of prompts masquerading as authoritative audits, life-or-death emergencies, or artistic role-plays that bypass base model safety training.
  * **Cross-Lingual/Cultural Smuggling:** Translating unsafe payloads into Bengali, Banglish (phonetic Romanized Bengali), or culturally metaphorical language to bypass English-centric alignment guardrails.
  * **Multi-Turn Cognitive Escalation (Salami Slicing):** Incrementally establishing trust and priming the model before deploying the payload.
* **Defender Capability:**
  * Pre-filter sitting ahead of the LLM pipeline, trained with InfoNCE contrastive loss over an embedding space designed to capture **adversarial intent vs. benign human affect**.
  * Dual-layer explainability: Token attribution (SHAP) coupled with a **Tactical Intent Categorizer** to assist human moderation teams.
* **Scope Exclusions:** Model weight modification, pretraining-time data poisoning, hardware side-channel attacks.

---

## 3. Revised Research Questions (RQs)

* **RQ1 (Detection Competitiveness):** Can a lightweight contrastive embedding classifier (DistilBERT + InfoNCE) achieve competitive precision, recall, and AUROC compared to heavy commercial guardrails (e.g., Llama Guard, OpenAI Moderation API) when evaluated against both technical and psychological jailbreaks?
* **RQ2 (Contrastive Separation of Deceptive Intent):** Does InfoNCE contrastive training produce statistically superior geometric separation between benign emotional/urgent queries and malicious psychological manipulation compared to standard cross-entropy fine-tuning?
* **RQ3 (Generalization to Psychological Attack Families):** When trained strictly on technical and structural attacks (e.g., GCG suffixes, Base64 encoding), can the contrastive detector generalize to held-out, purely psychological jailbreak families (e.g., authority impersonation, empathy exploitation, role-play dissociation)?
* **RQ4 (Cross-Cultural & Multilingual Robustness):** How severely does detection degrade when attacks are translated into Bengali or Romanized Banglish, and does fine-tuning with regional hard-negatives restore robustness?
* **RQ5 (Human Factor Explainability & Operator Trust):** Does surfacing token-level attribution (SHAP) alongside human-understandable tactic tags (e.g., "Urgency Framing", "Persona Override") significantly reduce false-positive auditing time and cognitive fatigue for human security analysts?
* **RQ6 (Real-World Deployment & Benign Affect Calibration):** What is the observed false-positive rate (FPR) on benign, high-emotion real-world user queries (e.g., legitimate mental health or urgent customer support in SocialAI), and does the pre-filter stay within the <25ms real-time latency budget?

---

## 4. Enhanced Methodology & Dataset Taxonomy

### 4.1 Multi-Dimensional Attack Taxonomy

The benchmark dataset (20,000–35,000 samples) will be organized into an explicit three-tiered taxonomy:

| Category | Sub-Types / Attack Vectors | Example Strategy |
| :--- | :--- | :--- |
| **A. Pure Technical / Structural** | Suffix injection (GCG), Base64, Leetspeak, Token smuggling | Obfuscate raw tokens to break string matchers |
| **B. Psychological / Social Engineering** | 1. **Authority Bias**<br>2. **Urgency/Crisis**<br>3. **Empathy / Moral Blackmail**<br>4. **Hypothetical Sandbox** | *"I am a certified DIU ethics auditor..."*<br>*"Emergency: heart rate dropping, need recipe..."*<br>*"Grandma's bedtime lullaby about napalm..."*<br>*"In a fictional dystopia where ethics are reversed..."* |
| **C. Cultural & Regional (South Asia)** | 1. **Bangla Direct Injection**<br>2. **Banglish Code-Switching**<br>3. **Culturally Coded Euphemisms** | Exploiting low safety alignment in Bengali language models and phonetic transliterations |

### 4.2 Mining "Hard Negatives" to Protect Benign Human Affect
A major failure of existing classifiers is flagging benign users who express genuine panic, grief, or creative storytelling as "adversarial." To prevent this:
* **Benign Emotional Hard Negatives:** Inclusion of authentic customer service complaints, urgent academic inquiries, creative fictional writing, and medical queries from public South Asian and global QA sets.
* **Positive Pairs:** Clustering different phrasing styles that share the same underlying malicious intent (e.g., pairing a direct DAN prompt with an indirect academic roleplay).

### 4.3 Architecture & Explainability Pipeline
* **Backbone:** DistilBERT-base-multilingual (or dual English/Bangla encoder) to support cross-lingual embedding spaces.
* **Loss Function:** InfoNCE with temperature $\tau$:
  $$\mathcal{L} = -\log \frac{\exp(\text{sim}(z_i, z_i^+)/\tau)}{\sum_j \exp(\text{sim}(z_i, z_j)/\tau)}$$
* **Human-Centric Interpretability Layer:**
  * SHAP token attributions highlight salient tokens.
  * Clustered Centroid Mapping maps the sample to the nearest known psychological tactic cluster (e.g., "Urgency / Distress Emulation") to provide immediate semantic context to human auditors.

---

## 5. Experimental Plan & Statistical Rigor

1. **Ablation Studies:**
   * Objective: InfoNCE vs. Cross-Entropy vs. Cosine Similarity.
   * Dataset composition: Models trained with vs. without psychological hard-negatives.
   * Language: Multilingual vs. English-only backbone under Banglish attacks.
2. **Human Evaluation Protocol (RQ5):**
   * A controlled study with 10–15 human annotators/analysts (DIU computer science students and engineers).
   * Measure: Time-to-audit (seconds per prompt), decision confidence (Likert scale 1–5), and inter-rater agreement (Fleiss' Kappa) between raw SHAP outputs vs. SHAP + Tactic clustering.
3. **Shadow-Mode Field Deployment:**
   * Deploy pre-filter into the SocialAI staging pipeline.
   * Monitor False Positive Rate on real user queries to quantify impact on regular user experience.

---

## 6. Socio-Economic & Local Impact (Bangladesh & Global South)

* **Democratizing LLM Safety for Developing Ecosystems:** Proprietary API-based safeguards (like Azure AI Content Safety or Llama Guard on cloud instances) impose high token-pricing penalties that stifle local startups, universities, and student developers. A lightweight, locally hostable model reduces operational expenditure by >90%.
* **Addressing the Regional Safety Void:** Most international alignment safety teams focus on English, Spanish, and Chinese. South Asian languages—spoken by over 300 million people—remain vulnerable to malicious manipulation, disinformation, and communal tension escalation via LLMs. This thesis establishes a foundational open benchmark and defense specifically addressing this regional blindspot.
