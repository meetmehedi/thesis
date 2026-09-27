# Research Paper Submission Strategy & Publication Guide

This document outlines the submission strategy, target venues (Conferences vs. Journals), and formatting instructions for the two IEEE versions of this thesis research paper:

1. **Version 1 (Conference):** [`papers/IEEE_Conference_Paper.tex`](file:///Users/md.mehedihasan/Documents/Thesis/papers/IEEE_Conference_Paper.tex)  
   *Target: 6–8 Pages IEEE Conference Format (Double-Column)*
2. **Version 2 (Journal / Transactions):** [`papers/IEEE_Transactions_Journal_Paper.tex`](file:///Users/md.mehedihasan/Documents/Thesis/papers/IEEE_Transactions_Journal_Paper.tex)  
   *Target: 10–14 Pages IEEE Transactions / Access Format (Double-Column)*

---

## 1. Where to Submit: Conferences vs. Journals?

| Category | Recommended Target Venue | Indexing / Tier | Review Timeline | Best Suited Paper Version | Strategic Advantage |
|:---|:---|:---|:---|:---|:---|
| **Journal (Recommended for Fast Publication)** | **IEEE Access** | SCIE, Scopus Q1/Q2, IEEE Xplore | **4–6 Weeks** (Rapid Review) | **Version 2 (Journal)** | Highly prestigious for graduating B.Sc. students; fast turnaround; comprehensive empirical papers are welcomed; 100% open-access. |
| **Journal (Top-Tier Long Term)** | **IEEE Transactions on Dependable and Secure Computing (TDSC)** | IEEE / ACM Premier, CORE A* | **6–9 Months** | **Version 2 (Journal)** | The gold standard in systems security. Focuses heavily on the formal threat model, hard-negative mining, and attack taxonomy. |
| **Journal (Cybersecurity)** | **Elsevier Computers & Security (COSE)** | SCIE, Scopus Q1, CORE B | **2–3 Months** | **Version 2 (Journal)** | Very receptive to socio-technical and AI prompt injection defenses; rigorous empirical validation. |
| **Conference (Top Applied)** | **IEEE CNS (Conference on Communications and Network Security)** | IEEE, CORE B | Annual Cycle | **Version 1 (Conference)** | Perfect scope for ingress security filters, network edge protection, and real-time SLA evaluations ($<$5 ms). |
| **Conference (Workshop)** | **IEEE S&P (Oakland) Deep Learning and Security (DLS) Workshop** | IEEE Premier Workshop | Annual (Winter submission) | **Version 1 (Conference)** | High academic prestige; focuses specifically on adversarial ML, contrastive learning, and LLM safety. |
| **Conference (AI / Big Data)** | **IEEE BigData (Special Session on Trustworthy & Secure AI)** | IEEE, CORE B | Fall submission | **Version 1 (Conference)** | Great venue for benchmark evaluations, multi-seed statistical significance, and cross-lingual NLP. |

---

## 2. Comparison of the Two Paper Versions

### Version 1: IEEE Conference Paper (6 Pages)
- **File:** [`papers/IEEE_Conference_Paper.tex`](file:///Users/md.mehedihasan/Documents/Thesis/papers/IEEE_Conference_Paper.tex)
- **Tone:** Concise, high-density, result-oriented.
- **Key Focus:**
  - The novel **Supervised Contrastive (InfoNCE) formulation** for prompt injection.
  - The **50% FPR reduction** (0.092% vs 0.184%).
  - **Cross-lingual evasion resilience** (100% recall on Bengali & Banglish).
  - **Inference latency** ($<$5 ms) satisfying strict real-time production SLAs ($<$25 ms).

### Version 2: IEEE Journal / Transactions Paper (12+ Pages)
- **File:** [`papers/IEEE_Transactions_Journal_Paper.tex`](file:///Users/md.mehedihasan/Documents/Thesis/papers/IEEE_Transactions_Journal_Paper.tex)
- **Tone:** Exhaustive, mathematically rigorous, systemically grounded.
- **Key Focus:**
  - Complete **3-tier taxonomy** with real-world prompt examples.
  - Mathematical contrastive hypersphere geometry vs. unconstrained cross-entropy logits.
  - Deep-dive **Ablation Studies**: Proving that omitting emotional hard-negatives causes a catastrophic **+10.12% FPR spike (220 false alarms)**.
  - **Human-in-the-Loop SOC Explainability Layer**: Forensic tactic attribution mitigating cognitive fatigue during moderation audits.
  - Multi-seed bootstrap statistical significance ($B=1,000$).

---

## 3. How to Compile to PDF

### Option A: Overleaf (Recommended)
1. Go to [Overleaf](https://www.overleaf.com/).
2. Create a new blank project.
3. Upload `IEEE_Conference_Paper.tex` (or `IEEE_Transactions_Journal_Paper.tex`).
4. Set compiler to `pdfLaTeX` and click **Recompile**.

### Option B: Local pdflatex (Mac / Linux)
```bash
cd papers/
pdflatex IEEE_Conference_Paper.tex
bibtex IEEE_Conference_Paper
pdflatex IEEE_Conference_Paper.tex
pdflatex IEEE_Conference_Paper.tex
```
