# workers/drug_class_pipeline.py
#
# WHAT THIS DOES:
# Pulls drug class knowledge from RxNorm + MedRT, converts structured data
# into readable clinical text, and upserts it into ChromaDB so the RAG
# pipeline can answer educational questions about drug families, mechanisms,
# adverse effects, and allergy cross-reactivity.
#
# WHY THIS EXISTS:
# RxNorm and MedRT give us structured relational data (drug X belongs to
# class Y). ChromaDB stores unstructured text that the LLM can search.
# They are two completely different systems. This pipeline bridges them —
# converting structured knowledge into text chunks that the RAG pipeline
# can retrieve and pass to the LLM.
#
# WHEN IT RUNS:
# - Manually: python -m workers.drug_class_pipeline
# - Weekly: GitHub Actions workflow (.github/workflows/drug_data_pipeline.yml)
# - On demand: after adding new drug classes to DRUG_CLASSES_TO_SEED
#
# DATA SOURCES (all free, no API keys required):
# - RxNorm API: https://rxnav.nlm.nih.gov/REST
# - MedRT via RxClass: same base URL, relaSource=MEDRT
# - OpenFDA: https://api.fda.gov/drug
#
# DIFF STRATEGY:
# Each chunk gets a deterministic ID based on its drug class name.
# On re-run, ChromaDB upserts (update if exists, insert if new).
# This means running the pipeline weekly is safe — it won't duplicate data.

import asyncio
import hashlib
import sys
from typing import Optional

import httpx
import chromadb
from chromadb.config import Settings as ChromaSettings

sys.path.insert(0, ".")

from core.config import settings
from monitoring.logger import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

# ── Drug classes to seed ───────────────────────────────────────────────────────
# Each entry defines a drug class with its RxNorm search name and known members.
# The pipeline enriches these with data from RxNorm and MedRT APIs.
# Add new classes here as Pillara expands its coverage.

DRUG_CLASSES_TO_SEED = [
    {
        "class_name": "Penicillins",
        "also_known_as": ["penicillin antibiotics", "beta-lactam penicillins"],
        "rxclass_name": "Penicillins",
        "member_drugs": [
            "amoxicillin", "ampicillin", "penicillin V", "penicillin G",
            "nafcillin", "oxacillin", "dicloxacillin", "piperacillin",
        ],
        "mechanism": (
            "Penicillins work by inhibiting bacterial cell wall synthesis. "
            "They bind to penicillin-binding proteins (PBPs) and block the "
            "final step of peptidoglycan synthesis, causing bacterial cell "
            "lysis and death. They are bactericidal."
        ),
        "clinical_use": [
            "Bacterial infections", "Streptococcal pharyngitis",
            "Skin and soft tissue infections", "Dental infections",
            "Pneumonia", "Syphilis (penicillin G)",
        ],
        "adverse_effects": [
            "Hypersensitivity reactions (rash, urticaria, anaphylaxis)",
            "Diarrhea", "Nausea", "Clostridium difficile colitis",
            "Seizures at high doses", "Interstitial nephritis",
        ],
        "allergy_cross_reactivity": (
            "Patients with penicillin allergy have approximately 1-2% cross-reactivity "
            "with cephalosporins (higher with first-generation). Cross-reactivity with "
            "carbapenems is less than 1%. Aztreonam cross-reacts with ceftazidime "
            "specifically. Always document the type of penicillin reaction."
        ),
        "contraindications": [
            "Known penicillin allergy (anaphylaxis history)",
            "Infectious mononucleosis (amoxicillin causes rash)",
        ],
    },
    {
        "class_name": "Sulfonamides",
        "also_known_as": ["sulfa drugs", "sulphonamides", "sulfa antibiotics"],
        "rxclass_name": "Sulfonamides",
        "member_drugs": [
            "sulfamethoxazole", "sulfadiazine", "sulfasalazine",
            "sulfacetamide", "dapsone", "trimethoprim-sulfamethoxazole (TMP-SMX)",
        ],
        "mechanism": (
            "Sulfonamides competitively inhibit dihydropteroate synthase, an enzyme "
            "bacteria need to synthesize folate. Human cells are unaffected because "
            "they obtain folate from diet rather than synthesizing it. This selective "
            "toxicity makes sulfonamides effective antibacterials."
        ),
        "clinical_use": [
            "Urinary tract infections", "Pneumocystis jirovecii pneumonia (PCP) prophylaxis",
            "Toxoplasmosis", "Nocardia infections", "Acne (topical sulfacetamide)",
            "Inflammatory bowel disease (sulfasalazine)",
        ],
        "adverse_effects": [
            "Rash", "Stevens-Johnson syndrome", "Toxic epidermal necrolysis",
            "Crystalluria and kidney stones", "Bone marrow suppression",
            "Photosensitivity", "Hepatotoxicity", "Hemolytic anemia in G6PD deficiency",
        ],
        "allergy_cross_reactivity": (
            "Sulfa allergy may cross-react with other sulfonamide-containing drugs: "
            "thiazide diuretics (hydrochlorothiazide), loop diuretics (furosemide), "
            "sulfonylureas (glipizide, glibenclamide), carbonic anhydrase inhibitors "
            "(acetazolamide), and COX-2 inhibitors (celecoxib). "
            "However, the clinical significance of these cross-reactions is debated. "
            "Antibiotic sulfonamides (sulfamethoxazole) have different structural "
            "components than non-antibiotic sulfonamides."
        ),
        "contraindications": [
            "G6PD deficiency (risk of hemolytic anemia)",
            "Late pregnancy (risk of neonatal jaundice)",
            "Infants under 2 months (kernicterus risk)",
            "Severe renal impairment",
        ],
    },
    {
        "class_name": "Cephalosporins",
        "also_known_as": ["cephalosporin antibiotics", "beta-lactam cephalosporins"],
        "rxclass_name": "Cephalosporins",
        "member_drugs": [
            "cephalexin", "cefazolin", "cefuroxime", "ceftriaxone",
            "cefdinir", "cefepime", "ceftaroline",
        ],
        "mechanism": (
            "Like penicillins, cephalosporins inhibit bacterial cell wall synthesis "
            "by binding to penicillin-binding proteins (PBPs). They are bactericidal. "
            "Cephalosporins are classified by generation (1st through 5th), with "
            "later generations having broader gram-negative coverage."
        ),
        "clinical_use": [
            "Skin and soft tissue infections", "Respiratory tract infections",
            "Urinary tract infections", "Surgical prophylaxis (cefazolin)",
            "Meningitis (ceftriaxone)", "Hospital-acquired infections",
        ],
        "adverse_effects": [
            "Hypersensitivity reactions", "Diarrhea", "Nausea",
            "Clostridium difficile colitis", "Transient elevation of liver enzymes",
            "Positive Coombs test (ceftriaxone)",
        ],
        "allergy_cross_reactivity": (
            "Cross-reactivity with penicillin allergy is approximately 1-2%, lower "
            "than historically believed. The cross-reactivity is primarily due to "
            "similar R1 side chains, not the beta-lactam ring itself. "
            "First-generation cephalosporins (cephalexin, cefazolin) have higher "
            "cross-reactivity with penicillin than later generations."
        ),
        "contraindications": [
            "Documented cephalosporin allergy",
            "History of severe anaphylaxis to penicillin (use with caution)",
        ],
    },
    {
        "class_name": "NSAIDs",
        "also_known_as": [
            "nonsteroidal anti-inflammatory drugs", "non-steroidal anti-inflammatory drugs",
            "anti-inflammatory painkillers",
        ],
        "rxclass_name": "Non-Steroidal Anti-Inflammatory Agents",
        "member_drugs": [
            "ibuprofen", "naproxen", "diclofenac", "indomethacin",
            "ketorolac", "meloxicam", "celecoxib", "aspirin",
        ],
        "mechanism": (
            "NSAIDs inhibit cyclooxygenase enzymes (COX-1 and COX-2), reducing "
            "prostaglandin synthesis. This produces anti-inflammatory, analgesic, "
            "and antipyretic effects. COX-1 inhibition reduces gastric mucosal "
            "protection and platelet aggregation. COX-2 selective inhibitors "
            "(celecoxib) spare COX-1, reducing GI side effects."
        ),
        "clinical_use": [
            "Pain relief", "Fever reduction", "Inflammatory conditions",
            "Arthritis", "Dysmenorrhea", "Postoperative pain",
            "Cardiovascular protection (low-dose aspirin)",
        ],
        "adverse_effects": [
            "GI ulceration and bleeding", "Renal impairment",
            "Cardiovascular events (increased with COX-2 selective)",
            "Hypertension", "Fluid retention", "Hypersensitivity reactions",
            "Hepatotoxicity (rare)", "Platelet dysfunction",
        ],
        "allergy_cross_reactivity": (
            "NSAID hypersensitivity can be pharmacological (affecting all COX-1 "
            "inhibitors) or immunological (specific to one drug). Aspirin-exacerbated "
            "respiratory disease (AERD/Samter's triad) affects 10-20% of adult "
            "asthmatics and cross-reacts with all non-selective NSAIDs. "
            "COX-2 selective inhibitors (celecoxib) are often tolerated by patients "
            "with non-selective NSAID hypersensitivity."
        ),
        "contraindications": [
            "Active peptic ulcer disease",
            "Severe renal or hepatic impairment",
            "Third trimester of pregnancy",
            "Aspirin-exacerbated respiratory disease",
            "Concurrent anticoagulant therapy (relative)",
        ],
    },
    {
        "class_name": "Beta-blockers",
        "also_known_as": ["beta-adrenergic blockers", "beta-adrenoceptor antagonists"],
        "rxclass_name": "Adrenergic beta-Antagonists",
        "member_drugs": [
            "metoprolol", "atenolol", "propranolol", "carvedilol",
            "bisoprolol", "labetalol", "nebivolol", "esmolol",
        ],
        "mechanism": (
            "Beta-blockers competitively block beta-adrenergic receptors. "
            "Beta-1 selective blockers (metoprolol, atenolol) primarily affect the "
            "heart, reducing heart rate and contractility. Non-selective blockers "
            "(propranolol, carvedilol) also block beta-2 receptors in the lungs and "
            "vasculature. Carvedilol additionally blocks alpha-1 receptors."
        ),
        "clinical_use": [
            "Hypertension", "Heart failure", "Angina pectoris",
            "Post-myocardial infarction", "Atrial fibrillation rate control",
            "Migraine prophylaxis", "Hyperthyroidism (propranolol)",
            "Anxiety (propranolol, off-label)",
        ],
        "adverse_effects": [
            "Bradycardia", "Hypotension", "Fatigue", "Cold extremities",
            "Bronchospasm (non-selective, in asthmatics)", "Depression",
            "Masked hypoglycemia symptoms in diabetics",
            "Sexual dysfunction", "Vivid dreams",
        ],
        "allergy_cross_reactivity": (
            "True allergy to beta-blockers is rare. However, patients on beta-blockers "
            "who experience anaphylaxis may have a more severe reaction and may be "
            "resistant to epinephrine treatment. Patients with anaphylaxis risk should "
            "discuss beta-blocker use with their doctor."
        ),
        "contraindications": [
            "Decompensated heart failure", "Severe bradycardia or heart block",
            "Asthma or severe COPD (non-selective beta-blockers)",
            "Cardiogenic shock", "Cocaine toxicity (propranolol)",
        ],
    },
    {
        "class_name": "ACE Inhibitors",
        "also_known_as": [
            "angiotensin-converting enzyme inhibitors",
            "ACEIs", "ACE-inhibitors",
        ],
        "rxclass_name": "Angiotensin-Converting Enzyme Inhibitors",
        "member_drugs": [
            "lisinopril", "enalapril", "ramipril", "captopril",
            "perindopril", "benazepril", "quinapril", "fosinopril",
        ],
        "mechanism": (
            "ACE inhibitors block the angiotensin-converting enzyme, preventing "
            "conversion of angiotensin I to angiotensin II. This reduces vasoconstriction "
            "and aldosterone secretion, lowering blood pressure and reducing cardiac "
            "workload. They also increase bradykinin levels, which contributes to "
            "the characteristic dry cough side effect."
        ),
        "clinical_use": [
            "Hypertension", "Heart failure", "Post-myocardial infarction",
            "Diabetic nephropathy", "Chronic kidney disease",
            "Left ventricular dysfunction",
        ],
        "adverse_effects": [
            "Dry persistent cough (10-15% of patients, due to bradykinin accumulation)",
            "Angioedema (rare but potentially life-threatening)",
            "Hyperkalemia", "Acute kidney injury (especially with NSAIDs or diuretics)",
            "Hypotension (first dose)", "Rash (captopril)",
        ],
        "allergy_cross_reactivity": (
            "ACE inhibitor-induced angioedema is a class effect — patients who develop "
            "angioedema on one ACE inhibitor should not be switched to another. "
            "ARBs (angiotensin receptor blockers) are an alternative and have much "
            "lower angioedema risk. ACE inhibitor cough is also a class effect."
        ),
        "contraindications": [
            "Pregnancy (teratogenic — causes fetal renal dysplasia)",
            "History of ACE inhibitor-induced angioedema",
            "Bilateral renal artery stenosis",
            "Concurrent use with sacubitril (neprilysin inhibitor) — risk of angioedema",
        ],
    },
    {
        "class_name": "Statins",
        "also_known_as": [
            "HMG-CoA reductase inhibitors", "cholesterol-lowering drugs",
        ],
        "rxclass_name": "Hydroxymethylglutaryl-CoA Reductase Inhibitors",
        "member_drugs": [
            "atorvastatin", "simvastatin", "rosuvastatin", "pravastatin",
            "lovastatin", "fluvastatin", "pitavastatin",
        ],
        "mechanism": (
            "Statins competitively inhibit HMG-CoA reductase, the rate-limiting enzyme "
            "in cholesterol biosynthesis in the liver. This reduces intracellular "
            "cholesterol, upregulates LDL receptors, and increases clearance of LDL "
            "from the bloodstream. They also have pleiotropic effects including "
            "anti-inflammatory and plaque-stabilizing properties."
        ),
        "clinical_use": [
            "Hypercholesterolemia", "Cardiovascular disease prevention",
            "Post-myocardial infarction", "Stroke prevention",
            "Peripheral artery disease",
        ],
        "adverse_effects": [
            "Myopathy and myalgia (muscle pain, most common)",
            "Rhabdomyolysis (rare but serious)",
            "Elevated liver enzymes (transient, usually mild)",
            "Increased blood glucose (modest risk of new-onset diabetes)",
            "Cognitive effects (rare, reversible)",
        ],
        "allergy_cross_reactivity": (
            "True statin allergy is rare. Myopathy risk increases significantly with "
            "concurrent use of fibrates (especially gemfibrozil), niacin, cyclosporine, "
            "and certain antibiotics (clarithromycin, erythromycin). Patients who "
            "develop myopathy on one statin may tolerate another at lower doses."
        ),
        "contraindications": [
            "Active liver disease or unexplained persistent elevated transaminases",
            "Pregnancy and breastfeeding",
            "Concurrent use of strong CYP3A4 inhibitors (simvastatin, lovastatin)",
        ],
    },
    {
        "class_name": "Benzodiazepines",
        "also_known_as": ["benzos", "tranquilizers", "sedative-hypnotics"],
        "rxclass_name": "Benzodiazepines",
        "member_drugs": [
            "diazepam", "lorazepam", "alprazolam", "clonazepam",
            "midazolam", "temazepam", "chlordiazepoxide", "oxazepam",
        ],
        "mechanism": (
            "Benzodiazepines enhance the effect of GABA (gamma-aminobutyric acid), "
            "the major inhibitory neurotransmitter in the brain. They bind to the "
            "GABA-A receptor complex and increase the frequency of chloride ion channel "
            "opening, resulting in sedation, anxiolysis, muscle relaxation, and "
            "anticonvulsant effects."
        ),
        "clinical_use": [
            "Anxiety disorders", "Panic disorder", "Insomnia",
            "Seizure disorders (clonazepam)", "Alcohol withdrawal",
            "Procedural sedation (midazolam)", "Muscle relaxation",
            "Status epilepticus (lorazepam IV)",
        ],
        "adverse_effects": [
            "Sedation and drowsiness", "Cognitive impairment and memory problems",
            "Physical dependence and withdrawal syndrome",
            "Respiratory depression (especially with opioids or alcohol)",
            "Falls and fractures in elderly patients",
            "Paradoxical agitation (rare)",
        ],
        "allergy_cross_reactivity": (
            "True benzodiazepine allergy is extremely rare. Patients who experience "
            "adverse reactions to one benzodiazepine may not tolerate others in the "
            "class due to the shared mechanism. Benzodiazepine withdrawal can be "
            "life-threatening and must be managed medically."
        ),
        "contraindications": [
            "Severe respiratory depression", "Myasthenia gravis",
            "Sleep apnea", "Acute narrow-angle glaucoma",
            "First trimester of pregnancy", "Concurrent opioid use (high risk)",
        ],
    },
    {
        "class_name": "Metformin and Biguanides",
        "also_known_as": ["biguanides", "oral antidiabetics", "insulin sensitizers"],
        "rxclass_name": "Biguanides",
        "member_drugs": ["metformin", "phenformin (withdrawn)"],
        "mechanism": (
            "Metformin's primary mechanism is activation of AMPK (AMP-activated protein "
            "kinase), which reduces hepatic glucose production (gluconeogenesis). "
            "It also improves peripheral insulin sensitivity and reduces intestinal "
            "glucose absorption. It does not stimulate insulin secretion and therefore "
            "does not cause hypoglycemia when used alone."
        ),
        "clinical_use": [
            "Type 2 diabetes mellitus (first-line therapy)",
            "Polycystic ovary syndrome (PCOS, off-label)",
            "Prediabetes prevention",
            "Insulin resistance",
        ],
        "adverse_effects": [
            "GI side effects: nausea, diarrhea, abdominal pain (very common initially)",
            "Lactic acidosis (rare but serious, especially with renal impairment)",
            "Vitamin B12 deficiency with long-term use",
            "Metallic taste",
        ],
        "allergy_cross_reactivity": (
            "True metformin allergy is rare. GI intolerance is common and dose-related "
            "but not an allergy. Extended-release formulations significantly reduce GI "
            "side effects. Lactic acidosis risk increases with renal impairment, "
            "liver disease, excessive alcohol use, and iodinated contrast media."
        ),
        "contraindications": [
            "eGFR below 30 mL/min (hold if eGFR 30-45)",
            "Active liver disease or alcohol abuse",
            "Iodinated contrast media (hold 48 hours before and after)",
            "Acute illness causing dehydration or hypoxia",
        ],
    },
    {
        "class_name": "Opioid Analgesics",
        "also_known_as": ["opioids", "narcotics", "opioid pain medications"],
        "rxclass_name": "Opioid Analgesics",
        "member_drugs": [
            "morphine", "codeine", "oxycodone", "hydrocodone",
            "fentanyl", "tramadol", "hydromorphone", "buprenorphine",
            "methadone",
        ],
        "mechanism": (
            "Opioids bind to mu, kappa, and delta opioid receptors in the central and "
            "peripheral nervous system. Mu receptor activation produces analgesia, "
            "euphoria, and respiratory depression. They inhibit ascending pain pathways "
            "and alter the perception of and emotional response to pain."
        ),
        "clinical_use": [
            "Moderate to severe acute pain", "Cancer pain",
            "Chronic pain (selected cases)", "Palliative care",
            "Opioid use disorder treatment (buprenorphine, methadone)",
            "Cough suppression (codeine, low dose)",
        ],
        "adverse_effects": [
            "Respiratory depression (most dangerous)", "Sedation",
            "Constipation (almost universal, does not develop tolerance)",
            "Nausea and vomiting", "Physical dependence and addiction",
            "Pruritus", "Urinary retention", "Miosis (pinpoint pupils)",
        ],
        "allergy_cross_reactivity": (
            "True opioid allergy (IgE-mediated) is rare. Most reactions are "
            "pharmacological (histamine release causing itching and flushing) "
            "rather than true allergy. Patients who experience histamine reactions "
            "with morphine or codeine may tolerate synthetic opioids (fentanyl, "
            "oxycodone) which cause less histamine release. Codeine allergy does not "
            "predict allergy to other opioids."
        ),
        "contraindications": [
            "Respiratory depression without resuscitation equipment",
            "Acute or severe asthma",
            "Paralytic ileus",
            "Concurrent MAOI use (serotonin syndrome risk with tramadol, meperidine)",
            "Head injury with increased intracranial pressure",
        ],
    },
]


# ── Text generation ────────────────────────────────────────────────────────────

def generate_drug_class_text(drug_class: dict) -> str:
    """
    Converts a structured drug class dict into readable clinical text.

    WHY TEXT FORMAT (not structured JSON):
    ChromaDB stores text that gets embedded into vectors and searched semantically.
    Structured JSON can't be semantically searched — "mechanism: COX inhibition"
    doesn't match "how do NSAIDs work?" Well-written prose does.
    The text format mirrors how a pharmacology textbook describes a drug class.
    """
    lines = []

    lines.append(f"DRUG CLASS: {drug_class['class_name']}")

    if drug_class.get("also_known_as"):
        lines.append(f"ALSO KNOWN AS: {', '.join(drug_class['also_known_as'])}")

    lines.append("")
    lines.append(f"MECHANISM OF ACTION: {drug_class['mechanism']}")

    if drug_class.get("member_drugs"):
        lines.append("")
        lines.append(f"DRUGS IN THIS CLASS: {', '.join(drug_class['member_drugs'])}")

    if drug_class.get("clinical_use"):
        lines.append("")
        lines.append(f"CLINICAL USES: {'; '.join(drug_class['clinical_use'])}")

    if drug_class.get("adverse_effects"):
        lines.append("")
        lines.append(
            f"ADVERSE EFFECTS AND SIDE EFFECTS: {'; '.join(drug_class['adverse_effects'])}"
        )

    if drug_class.get("allergy_cross_reactivity"):
        lines.append("")
        lines.append(f"ALLERGY AND CROSS-REACTIVITY: {drug_class['allergy_cross_reactivity']}")

    if drug_class.get("contraindications"):
        lines.append("")
        lines.append(
            f"CONTRAINDICATIONS: {'; '.join(drug_class['contraindications'])}"
        )

    return "\n".join(lines)


def chunk_drug_class_text(text: str, class_name: str) -> list[dict]:
    """
    Splits drug class text into chunks for ChromaDB.

    Each chunk gets:
    - A deterministic ID (hash of class_name + section) for safe upserts
    - Metadata for filtering
    - The text content itself

    WHY CHUNK BY SECTION:
    A single large text block for a drug class (~500 words) would be one
    vector. When the user asks "what are the side effects of beta-blockers?"
    the vector for the whole article might not match well because it
    contains mechanism, uses, interactions etc. Chunking by section means
    the adverse_effects chunk is a strong match for side effect questions.
    """
    chunks = []
    sections = text.split("\n\n")

    for i, section in enumerate(sections):
        if not section.strip():
            continue

        # Deterministic ID: hash of class_name + section index
        # This means re-running the pipeline upserts (not duplicates) existing chunks
        chunk_id = hashlib.md5(
            f"drug_class:{class_name}:section:{i}".encode()
        ).hexdigest()

        # Determine section type from content
        section_type = "general"
        section_upper = section.upper()
        if "MECHANISM" in section_upper:
            section_type = "mechanism"
        elif "ADVERSE" in section_upper or "SIDE EFFECT" in section_upper:
            section_type = "adverse_effects"
        elif "ALLERGY" in section_upper or "CROSS-REACTIVITY" in section_upper:
            section_type = "allergy_cross_reactivity"
        elif "CONTRAINDICATION" in section_upper:
            section_type = "contraindications"
        elif "CLINICAL USE" in section_upper:
            section_type = "clinical_uses"
        elif "DRUG CLASS" in section_upper or "ALSO KNOWN" in section_upper:
            section_type = "overview"

        chunks.append({
            "id": chunk_id,
            "text": section.strip(),
            "metadata": {
                "drug_class": class_name,
                "section_type": section_type,
                "source": "drug_class_pipeline",
                "data_type": "educational",
            },
        })

    return chunks


# ── ChromaDB operations ────────────────────────────────────────────────────────

def get_chroma_collection():
    """Connect to ChromaDB and return the drug_knowledge collection."""
    client = chromadb.HttpClient(
        host=settings.CHROMA_HOST,
        port=settings.CHROMA_PORT,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    collection = client.get_or_create_collection(
        name=settings.CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    return collection


async def fetch_rxnorm_enrichment(class_name: str) -> dict:
    """
    Optionally enriches our local drug class data with live RxNorm API data.
    Returns any additional member drugs or class descriptions found.

    This is the live API enrichment layer — it runs on top of our local
    DRUG_CLASSES_TO_SEED data to catch any drugs or class updates we
    haven't manually added yet.
    """
    enrichment = {"additional_drugs": [], "rxcui": None}

    try:
        async with httpx.AsyncClient(timeout=settings.RXNORM_API_TIMEOUT) as client:
            # Search for the drug class by name
            response = await client.get(
                f"{settings.RXNORM_API_BASE_URL}/rxclass/classIdByName.json",
                params={"className": class_name, "classTypes": "CHEM"},
            )
            if response.status_code != 200:
                return enrichment

            data = response.json()
            class_concepts = data.get("rxclassMinConceptList", {}).get("rxclassMinConcept", [])
            if not class_concepts:
                return enrichment

            class_id = class_concepts[0].get("classId")
            if not class_id:
                return enrichment

            # Get member drugs for this class
            members_response = await client.get(
                f"{settings.RXNORM_API_BASE_URL}/rxclass/classMembers.json",
                params={"classId": class_id, "relaSource": "MEDRT"},
            )
            if members_response.status_code == 200:
                members_data = members_response.json()
                drug_members = (
                    members_data
                    .get("drugMemberGroup", {})
                    .get("drugMember", [])
                )
                enrichment["additional_drugs"] = [
                    m.get("minConcept", {}).get("name", "")
                    for m in drug_members
                    if m.get("minConcept", {}).get("name")
                ][:20]  # Cap at 20 additional drugs

    except Exception as e:
        logger.warning(
            "rxnorm_enrichment_failed",
            class_name=class_name,
            error=str(e),
        )

    return enrichment


# ── Main pipeline ──────────────────────────────────────────────────────────────

async def run_pipeline(dry_run: bool = False) -> dict:
    """
    Main entry point. Runs the full drug class seeding pipeline.

    dry_run=True: prints what would be done without writing to ChromaDB.
    Returns a summary dict with counts of classes processed, chunks added etc.
    """
    logger.info("drug_class_pipeline_starting", drug_class_count=len(DRUG_CLASSES_TO_SEED))

    summary = {
        "classes_processed": 0,
        "chunks_upserted": 0,
        "classes_failed": [],
        "dry_run": dry_run,
    }

    if not dry_run:
        collection = get_chroma_collection()

    for drug_class in DRUG_CLASSES_TO_SEED:
        class_name = drug_class["class_name"]

        try:
            # Step 1: Optionally enrich with live RxNorm data
            logger.info("drug_class_pipeline_processing", class_name=class_name)
            enrichment = await fetch_rxnorm_enrichment(class_name)

            # Add any additional drugs found via RxNorm to our local list
            if enrichment["additional_drugs"]:
                existing = set(drug_class.get("member_drugs", []))
                new_drugs = [d for d in enrichment["additional_drugs"] if d not in existing]
                if new_drugs:
                    drug_class["member_drugs"] = drug_class.get("member_drugs", []) + new_drugs
                    logger.info(
                        "rxnorm_enriched_member_drugs",
                        class_name=class_name,
                        new_drug_count=len(new_drugs),
                    )

            # Step 2: Generate clinical text
            text = generate_drug_class_text(drug_class)

            # Step 3: Chunk into sections
            chunks = chunk_drug_class_text(text, class_name)

            if dry_run:
                print(f"\n{'='*60}")
                print(f"CLASS: {class_name}")
                print(f"CHUNKS: {len(chunks)}")
                print(f"\nSAMPLE TEXT:\n{text[:500]}...")
                summary["chunks_upserted"] += len(chunks)
            else:
                # Step 4: Upsert into ChromaDB
                # Upsert = update if exists, insert if new
                # Safe to run repeatedly — won't create duplicates
                collection.upsert(
                    ids=[c["id"] for c in chunks],
                    documents=[c["text"] for c in chunks],
                    metadatas=[c["metadata"] for c in chunks],
                )
                summary["chunks_upserted"] += len(chunks)
                logger.info(
                    "drug_class_chunks_upserted",
                    class_name=class_name,
                    chunk_count=len(chunks),
                )

            summary["classes_processed"] += 1

        except Exception as e:
            logger.error(
                "drug_class_pipeline_error",
                class_name=class_name,
                error=str(e),
                error_type=type(e).__name__,
            )
            summary["classes_failed"].append(class_name)

    logger.info(
        "drug_class_pipeline_complete",
        classes_processed=summary["classes_processed"],
        chunks_upserted=summary["chunks_upserted"],
        classes_failed=summary["classes_failed"],
    )

    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pillara drug class data pipeline")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be seeded without writing to ChromaDB",
    )
    args = parser.parse_args()

    result = asyncio.run(run_pipeline(dry_run=args.dry_run))
    print(f"\nPipeline complete: {result}")
