"""General educational summaries, not individualized prescribing instructions."""
from urllib.parse import quote_plus

NOTICE = "General information only; side effects listed are not exhaustive. Follow your prescription and package leaflet. Ask a doctor or pharmacist about dose, interactions, pregnancy and suitability. Do not start, stop or switch treatment based on this page."

# Each summary is paired with a public patient-information reference.
INFO = {
    "Metformin": {
        "description": "Helps lower blood glucose by reducing glucose production in the liver and improving insulin sensitivity.",
        "uses": "Used for type 2 diabetes, alongside diet and activity as advised by a clinician.",
        "usage": "Usually taken with meals to reduce stomach upset. Follow the prescribed schedule; different formulations have different instructions.",
        "side_effects": ["Nausea or vomiting", "Diarrhoea and stomach pain", "Loss of appetite", "Low vitamin B12 with long-term use"],
        "warnings": "Rare lactic acidosis can cause severe weakness, breathing difficulty or feeling very cold: seek urgent care. Kidney problems, dehydration, heavy alcohol use and some scans require medical advice.",
        "reference": "https://www.nhs.uk/medicines/metformin/",
    },
    "Amlodipine": {
        "description": "A calcium-channel blocker that relaxes blood vessels.",
        "uses": "Used to treat high blood pressure and prevent some types of angina.",
        "usage": "Usually taken once daily, with or without food, at a consistent time as prescribed. It does not treat a sudden angina attack.",
        "side_effects": ["Swollen ankles", "Headache or flushing", "Dizziness", "Palpitations"],
        "warnings": "Seek urgent help for new or worsening chest pain, fainting or severe allergic symptoms. Discuss liver problems and interacting medicines with your clinician.",
        "reference": "https://www.nhs.uk/medicines/amlodipine/",
    },
    "Atorvastatin": {
        "description": "A statin that reduces cholesterol production in the liver.",
        "uses": "Used to lower cholesterol and reduce cardiovascular risk in people for whom it is prescribed.",
        "usage": "Usually taken once daily, with or without food. Follow your prescription and discuss grapefruit and medicine interactions with your pharmacist.",
        "side_effects": ["Nausea or indigestion", "Headache", "Diarrhoea or constipation", "Muscle aches"],
        "warnings": "Unexplained muscle pain or weakness, especially with dark urine, or yellowing skin needs prompt medical assessment. Discuss pregnancy, breastfeeding and liver disease before use.",
        "reference": "https://www.nhs.uk/medicines/atorvastatin/",
    },
    "Paracetamol": {
        "description": "A pain reliever and fever reducer, also called acetaminophen.",
        "uses": "Used for short-term relief of mild to moderate pain and fever.",
        "usage": "Follow the strength-specific package instructions or prescription. Do not combine with other medicines containing paracetamol; many cold remedies contain it.",
        "side_effects": ["Side effects are uncommon at recommended doses", "Rare rash or allergic reaction"],
        "warnings": "An overdose can cause serious liver damage even if you feel well: seek emergency advice immediately. Ask a clinician about liver disease, heavy alcohol use or persistent symptoms.",
        "reference": "https://www.nhs.uk/medicines/paracetamol-for-adults/",
    },
    "Pantoprazole": {
        "description": "A proton-pump inhibitor that reduces stomach acid production.",
        "uses": "Used for acid reflux and some stomach ulcers or other acid-related conditions.",
        "usage": "Often taken before a meal. Swallow delayed-release tablets whole and follow the prescribed duration; do not crush or chew them.",
        "side_effects": ["Headache", "Diarrhoea", "Nausea", "Stomach discomfort"],
        "warnings": "Seek medical advice for severe persistent diarrhoea. Vomiting blood, black stools or difficulty swallowing require urgent assessment. Long-term use may require monitoring.",
        "reference": "https://www.nhs.uk/medicines/pantoprazole/",
    },
    "Telmisartan": {
        "description": "An angiotensin receptor blocker that relaxes blood vessels.",
        "uses": "Used for high blood pressure and, in selected patients, cardiovascular risk reduction.",
        "usage": "Usually taken once daily, with or without food, as prescribed. Kidney function and potassium may need monitoring.",
        "side_effects": ["Dizziness or light-headedness", "Low blood pressure", "Raised potassium", "Changes in kidney function"],
        "warnings": "Do not use during pregnancy; contact your prescriber promptly if pregnant or planning pregnancy. Discuss potassium supplements and salt substitutes. Facial swelling or breathing difficulty requires emergency care.",
        "reference": "https://medlineplus.gov/druginfo/meds/a601249.html",
    },
    "Cetirizine": {
        "description": "An antihistamine that blocks the effects of histamine in allergic reactions.",
        "uses": "Used to relieve hay fever, other allergy symptoms and hives.",
        "usage": "Take according to the label or prescription. Kidney problems may require a different dose; ask a pharmacist. Avoid driving if sleepy.",
        "side_effects": ["Sleepiness or tiredness", "Dry mouth", "Headache", "Nausea or dizziness"],
        "warnings": "Alcohol and sedating medicines may increase drowsiness. It is not a substitute for emergency treatment of anaphylaxis; breathing difficulty or throat swelling needs emergency care.",
        "reference": "https://www.nhs.uk/medicines/cetirizine/",
    },
    "Levothyroxine": {
        "description": "Replaces thyroid hormone when the thyroid gland does not produce enough.",
        "uses": "Used for an underactive thyroid (hypothyroidism).",
        "usage": "Usually taken on an empty stomach before breakfast. Calcium, iron and some antacids affect absorption; ask your pharmacist about spacing. Blood tests guide the dose.",
        "side_effects": ["Symptoms from too high a dose can include palpitations", "Sweating or tremor", "Headache", "Sleep problems or diarrhoea"],
        "warnings": "Chest pain or a fast or irregular heartbeat needs urgent assessment. Do not use for weight loss. Discuss pregnancy promptly because monitoring and dose needs may change.",
        "reference": "https://www.nhs.uk/medicines/levothyroxine/",
    },
}


INFO.update({
    "Ibuprofen": dict(description="A non-steroidal anti-inflammatory pain reliever.", uses="Pain and inflammation when suitable for the patient.", usage="Use only as directed; do not combine with other NSAIDs such as diclofenac.", side_effects=["Indigestion", "Nausea", "Stomach bleeding", "Kidney problems"], warnings="Avoid self-use with ulcers, kidney disease, blood thinners or pregnancy. Avoid ibuprofen when dengue is suspected. Black stools or vomiting blood require urgent care.", reference="https://www.nhs.uk/medicines/ibuprofen-for-adults/"),
    "Omeprazole": dict(description="A proton-pump inhibitor that reduces stomach acid.", uses="Acid reflux and certain ulcers, as advised by a clinician.", usage="Follow formulation-specific instructions; do not crush gastro-resistant preparations.", side_effects=["Headache", "Nausea", "Diarrhoea", "Abdominal discomfort"], warnings="Difficulty swallowing, weight loss, vomiting blood or black stools need assessment. Long-term use and interactions require review.", reference="https://www.nhs.uk/medicines/omeprazole/"),
    "Levocetirizine": dict(description="An antihistamine used to reduce allergy symptoms.", uses="Allergic rhinitis and hives.", usage="Follow the prescription; kidney function can affect the prescribed dose.", side_effects=["Drowsiness", "Dry mouth", "Fatigue"], warnings="Avoid driving if sleepy. Alcohol can worsen sedation. Breathing difficulty or throat swelling requires emergency care, not just an antihistamine.", reference="https://medlineplus.gov/druginfo/meds/a607056.html"),
    "Amoxicillin": dict(description="A penicillin antibiotic.", uses="Certain bacterial infections diagnosed by a clinician, not viral colds or flu.", usage="Take exactly as prescribed. Liquid preparations may require reconstitution, specific storage and a discard date; ask the pharmacist.", side_effects=["Nausea", "Diarrhoea", "Rash", "Allergic reactions"], warnings="Tell the prescriber about penicillin allergy. Facial swelling or breathing difficulty requires emergency care; severe or bloody diarrhoea needs urgent review.", reference="https://www.nhs.uk/medicines/amoxicillin/"),
    "Azithromycin": dict(description="A macrolide antibiotic.", uses="Selected bacterial infections when prescribed.", usage="Follow the prescribed schedule and duration; do not use leftovers for a new illness.", side_effects=["Nausea", "Diarrhoea", "Abdominal pain"], warnings="Heart rhythm problems, liver disease and interacting medicines require prescriber review. Fainting, palpitations or severe diarrhoea need prompt assessment.", reference="https://www.nhs.uk/medicines/azithromycin/"),
    "Cefixime": dict(description="A cephalosporin antibiotic.", uses="Selected susceptible bacterial infections under medical supervision.", usage="Take only as prescribed and follow the prescribed course.", side_effects=["Diarrhoea", "Nausea", "Abdominal pain", "Rash"], warnings="Discuss antibiotic allergies and kidney disease. Severe allergic symptoms or severe or bloody diarrhoea require urgent care.", reference="https://medlineplus.gov/druginfo/meds/a690007.html"),
    "Metronidazole": dict(description="An antimicrobial medicine for certain bacterial and parasitic infections.", uses="Specific infections diagnosed by a clinician.", usage="Follow the prescription. Avoid alcohol during treatment and for 48 hours after finishing.", side_effects=["Nausea", "Metallic taste", "Diarrhoea"], warnings="Discuss interactions, especially blood thinners. New numbness, seizures or severe rash require urgent review.", reference="https://www.nhs.uk/medicines/metronidazole/"),
    "Ondansetron": dict(description="An anti-nausea medicine that blocks serotonin signals involved in vomiting.", uses="Prevention or treatment of nausea and vomiting in selected clinical situations.", usage="Use as prescribed; orally disintegrating and ordinary tablets have different handling instructions.", side_effects=["Headache", "Constipation", "Dizziness"], warnings="Heart rhythm disorders and interacting medicines need review. Palpitations or fainting require urgent assessment. Persistent vomiting or dehydration needs medical attention.", reference="https://medlineplus.gov/druginfo/meds/a601209.html"),
    "Losartan": dict(description="An angiotensin receptor blocker that relaxes blood vessels.", uses="High blood pressure and certain heart or kidney conditions.", usage="Follow the prescription; kidney function and potassium may need monitoring.", side_effects=["Dizziness", "Low blood pressure", "Raised potassium"], warnings="Do not use during pregnancy; contact the prescriber promptly. Discuss potassium supplements and salt substitutes. Facial swelling or breathing difficulty needs emergency care.", reference="https://www.nhs.uk/medicines/losartan/"),
    "Glimepiride": dict(description="A sulfonylurea medicine that helps the pancreas release insulin.", uses="Type 2 diabetes when prescribed.", usage="Follow the prescription and meal instructions; do not independently adjust diabetes treatment.", side_effects=["Low blood sugar", "Weight gain", "Nausea"], warnings="Missed meals and alcohol can increase low-blood-sugar risk. Confusion, seizures or unconsciousness require emergency help. Ask about driving and kidney or liver problems.", reference="https://medlineplus.gov/druginfo/meds/a696016.html"),
    "Folic acid": dict(description="A form of vitamin B9 used for specific supplementation needs.", uses="Folate deficiency and supplementation in pregnancy or with certain treatments as advised.", usage="Use the recommended strength and schedule; high-strength tablets are not interchangeable with routine supplements.", side_effects=["Nausea", "Bloating", "Loss of appetite"], warnings="Vitamin B12 deficiency should be considered before treating unexplained anaemia. Methotrexate treatment requires specific timing instructions from the prescriber.", reference="https://www.nhs.uk/medicines/folic-acid/"),
    "Albendazole": dict(description="An antiparasitic medicine used against certain worms.", uses="Specific parasitic infections; the regimen depends on the infection.", usage="Follow clinical or approved public-health programme instructions; do not infer a dose from shopping quantity.", side_effects=["Abdominal pain", "Nausea", "Headache"], warnings="Discuss pregnancy and liver disease before use. Some infections require prolonged treatment and monitoring; seek assessment for persistent symptoms.", reference="https://medlineplus.gov/druginfo/meds/a610019.html"),
    "Lactulose": dict(description="An osmotic laxative that draws water into the bowel.", uses="Constipation; also used for a liver-related condition under specialist supervision.", usage="Follow the label or prescription and measure with the supplied device.", side_effects=["Wind", "Bloating", "Diarrhoea", "Abdominal cramps"], warnings="Severe abdominal pain, vomiting or suspected bowel blockage need assessment. Persistent diarrhoea can cause dehydration. Discuss diabetes and sugar intolerance.", reference="https://www.nhs.uk/medicines/lactulose/"),
    "Dextromethorphan": dict(description="A cough suppressant found in some medicines for dry cough.", uses="Short-term dry-cough relief when appropriate; it does not treat the underlying illness.", usage="Use only as directed after checking age restrictions and all ingredients. Do not combine cough and cold products without pharmacist advice.", side_effects=["Drowsiness", "Dizziness", "Nausea"], warnings="Misuse or excessive doses can cause serious harm. Interactions with MAO inhibitors and some antidepressants can cause serotonin syndrome. Do not give cough medicines to young children without clinician guidance; persistent cough or breathing difficulty needs assessment.", reference="https://medlineplus.gov/druginfo/meds/a682492.html"),
})


def details(drug):
    info = {**INFO[drug["ingredient"]], "notice": NOTICE}
    info["safety_disclaimer"] = (
        "This is a medicinal drug, not a recommendation to self-medicate. Catalogue inclusion does not confirm stock or suitability. "
        + ("Prescription required: use only under a qualified clinician's direction. " if drug["rx_required"] else "Even medicines sold without a prescription can cause harm; ask a pharmacist about suitability. ")
        + ("Antibiotic: not a treatment for viral colds or flu. Do not self-start, share or use leftover antibiotics; follow the prescribed course. " if drug.get("antibiotic") else "")
    )
    if drug["unit"] == "bottle":
        info["usage"] = ("" if drug["ingredient"] == "Paracetamol" else info["usage"] + " ") + "Liquid strengths are not interchangeable. Check the exact concentration and bottle label. Use the supplied oral syringe or measuring cup, not a kitchen spoon; shake suspensions as directed. A child's dose depends on the medicine, age and weight and must be confirmed with a clinician or pharmacist. Shopping quantity means bottles, not a dose."
        info["safety_disclaimer"] += "Liquid medicine: do not guess children's doses or use adult instructions. Keep out of children's reach. "
        if drug["ingredient"] == "Paracetamol":
            info["reference"] = "https://www.nhs.uk/medicines/paracetamol-for-children/"
    return info


def online_searches(drug):
    query = quote_plus(f"{drug['ingredient']} {drug['strength']} {drug['form']}")
    return [{"provider": "Tata 1mg", "url": f"https://www.1mg.com/search/all?name={query}"},
            {"provider": "PharmEasy", "url": f"https://pharmeasy.in/search/all?name={query}"}]