import os
from dotenv import load_dotenv

load_dotenv()
from google import genai

client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
MODEL = 'gemini-3.1-pro-preview'

print("=== INITIATING LIVE TO-AND-FRO DEBATE: ARGON vs DEEPSEEK ===", flush=True)
print(f"Engine: {MODEL} | Task: FY-End Land Appraisal Prompt Architecture\n", flush=True)

# ---------------------------------------------------------------------------
# Turn 1: Argon Proposes the Master Methodology & Prompts
# ---------------------------------------------------------------------------
print(">>> TURN 1: ARGON PROPOSES INITIAL LAND VALUATION PROMPTS", flush=True)
argon_turn1_input = """You are Argon, Chief Quantitative Real Estate Architect for Vault Family Wealth.
We are replacing our old hardcoded +6% annual land markup (April 1) with an AI-driven valuation engine.
Asset context:
- Property: Yamuna Expressway Sector 22D Residential Plot (250 Gaj / Sq. Yard).
- Acquired: May 2021 for INR 80,00,000 (Current book value INR 1,37,50,000).
- Key micro-market: Noida International Airport corridor, Formula 1 / Film City belt, YEIDA authority plots.

Propose:
1. The 3-stage prompt architecture to determine the conservative, grounded annual % growth.
2. The specific inputs needed from search grounding (circle rates, registry trends, CPI inflation, repo rates).
3. Draft the exact prompt text for Stage 1 (Market Comps) and Stage 3 (Appreciation Determination).
"""

r1 = client.models.generate_content(model=MODEL, contents=argon_turn1_input)
argon_draft = r1.text
print(argon_draft[:800] + "...\n[Argon Turn 1 complete]\n", flush=True)

# ---------------------------------------------------------------------------
# Turn 2: DeepSeek Cross-Examines and Attacks Optimism
# ---------------------------------------------------------------------------
print(">>> TURN 2: DEEPSEEK SKEPTICAL AUDITOR CROSS-EXAMINES ARGON", flush=True)
deepseek_turn2_input = f"""You are DeepSeek-R1, acting as the Senior Fiduciary Auditor and Adversarial Risk Officer.
Argon has just proposed the following valuation framework for the Yamuna Expressway plot:

--- ARGON PROPOSAL ---
{argon_draft}
----------------------

Interrogate this aggressively from a fiduciary and macro perspective:
1. Listing vs Registry Reality: Real estate portals (99acres, MagicBricks) quote speculative broker ask prices. How do we prevent these asking premiums from inflating book value?
2. Illiquidity & Round-trip friction: Vacant land is illiquid and takes 6-12 months to sell, incurring 7-8% transfer charges, stamp duty, and legal costs.
3. Infrastructure Delay Risk: Projects like Jewar airport and Film City suffer execution slippage. Speculation must not be counted as realized appreciation.
4. Macro Headwinds: High borrowing costs and RBI policy rates dampen land turnover.
5. Mandatory haircuts: Formulate the exact haircut formulas (speculative haircut, illiquidity discount, infra delay haircut) and hard guardrails (appreciation ceiling) that Stage 2 and Stage 3 MUST enforce.
"""

r2 = client.models.generate_content(model=MODEL, contents=deepseek_turn2_input)
deepseek_critique = r2.text
print(deepseek_critique[:800] + "...\n[DeepSeek Turn 2 complete]\n", flush=True)

# ---------------------------------------------------------------------------
# Turn 3: Argon Reconciles and Synthesizes Final Multi-Stage Prompts
# ---------------------------------------------------------------------------
print(">>> TURN 3: ARGON SYNTHESIZES FINAL GROUNDED PROMPTS", flush=True)
argon_turn3_input = f"""You are Argon. DeepSeek-R1 has provided this intense fiduciary critique:

--- DEEPSEEK CRITIQUE ---
{deepseek_critique}
-------------------------

Reconcile DeepSeek's risk mandates. Provide the finalized, hardened production prompts for our Multi-Stage DAG:
- STAGE 1 PROMPT: Grounded Market Comps & Circle Rate Discovery (incorporating circle rate floor, median transacted rate, and macro CPI).
- STAGE 2 PROMPT: DeepSeek Fiduciary Haircut & Skeptical Review (enforcing speculative discount, illiquidity haircut, and appreciation ceiling).
- STAGE 3 PROMPT: Final Conservative Appreciation Determination (calculating the net defensible % increase, conservative margin of safety, and methodology audit trail).

Output the clean, ready-to-use prompt templates with Python format variables (e.g. {{holding_name}}, {{locality}}, {{circle_rate}}, etc.).
"""

r3 = client.models.generate_content(model=MODEL, contents=argon_turn3_input)
final_prompts = r3.text
print(final_prompts[:800] + "...\n[Argon Turn 3 complete]\n", flush=True)

# ---------------------------------------------------------------------------
# Save full debate record to markdown
# ---------------------------------------------------------------------------
output_path = "portfolio/ai/generated_land_prompts.md"
with open(output_path, "w") as f:
    f.write("# Live Multi-Turn Debate: Argon & DeepSeek Land Appraisal Prompts\n\n")
    f.write(f"**Engine**: `{MODEL}`  \n")
    f.write("**Date**: 2026-11-03  \n\n")
    f.write("## Turn 1: Argon Proposed Valuation Architecture\n\n")
    f.write(argon_draft + "\n\n")
    f.write("## Turn 2: DeepSeek Fiduciary Cross-Examination & Haircuts\n\n")
    f.write(deepseek_critique + "\n\n")
    f.write("## Turn 3: Synthesized Production Prompts for Multi-Stage DAG\n\n")
    f.write(final_prompts + "\n")

print(f"\n[DONE] Debate successfully transcribed to {output_path}!", flush=True)

