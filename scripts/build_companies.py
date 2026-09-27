"""Rebuild companies.csv from an h1bdata.info "top companies" PDF export.

Usage:  python scripts/build_companies.py path/to/H1B_Database.pdf
Needs `pdftotext` (poppler-utils): `brew install poppler` or `sudo apt-get install poppler-utils`.
Tier 1 = healthcare / healthcare-adjacent (by the sector rules below), Tier 2 = everything else.
Edit the SECTOR_RULES patterns to move a company between tiers, or edit companies.csv directly.
"""
import csv, re, subprocess, sys
from pathlib import Path

SECTOR_RULES = {  # sector: patterns (regex on uppercase name)
 'Pharma & Biotech': r"(?:PHARMA|REGENERON|GENENTECH|ABBVIE|AMGEN|GILEAD|ELI LILLY|BRISTOL-MYERS|MERCK SHARP|NOVARTIS|PFIZER|SANOFI|GLAXO|BOEHRINGER|TAKEDA|BAYER|BIOGEN|MODERNA|ALEXION|KITE PHARMA|SEAGEN|INCYTE|CSL BEHRING|JANSSEN|ZOETIS|NOVITIUM|CATALENT|EMD MILLIPORE)",
 'CRO & Life-sci services': r"PHARMACEUTICAL RESEARCH ASSOC|IQVIA|SYNEOS|PAREXEL|PPD DEVELOPMENT|PHARMACEUTICAL RESEARCH ASSOC|FRONTAGE LAB|CHARLES RIVER LAB|CYTEL|SAAMA|MEDIDATA|VEEVA|ZIFO|VALIDATION ASSOCIATES",
 'Healthcare & life-sci consulting': r"ZS ASSOCIATES|AXTRIA|TRINITY PARTNERS|HURON CONSULTING|GUIDEHOUSE",
 'Life-sci tools & Diagnostics': r"THERMO FISHER|AGILENT|BIO-RAD|ILLUMINA|10X GENOMICS|CEPHEID|NATERA|GUARDANT|FOUNDATION MEDICINE|TEMPUS|ROCHE MOLECULAR|LABORATORY CORPORATION",
 'MedTech & Devices': r"MEDTRONIC|STRYKER|ZIMMER|BECTON|BOSTON SCIENTIFIC|INTUITIVE SURGICAL|EDWARDS LIFESCIENCES|SMITH & NEPHEW|VARIAN MEDICAL|DEXCOM|INSULET|PENUMBRA|ALIGN TECHNOLOGY|ABBOTT LAB|COVIDIEN|ST JUDE MEDICAL|ALCON|GE PRECISION HEALTHCARE|\bGE HEALTHCARE|SIEMENS MEDICAL|PHILIPS NORTH AMERICA|AURIS HEALTH|VERILY",
 'Payers & Pharmacy benefits': r"OPTUM|UNITED HEALTHCARE|ELEVANCE|ANTHEM|AETNA|HUMANA|CIGNA|EVERNORTH|EXPRESS SCRIPTS|EVICORE|CAREMARK|CENTENE|MOLINA|HIGHMARK|BLUE CROSS|BLUECROSS|HEALTH CARE SERVICE CORP|CARESOURCE|DELTA DENTAL|GROUP HEALTH PLAN|HM HEALTH SOLUTIONS|MULTIPLAN|EHEALTHINSURANCE|PHYSICIANS MUTUAL",
 'Pharmacy & Distribution': r"CVS |CVS$|WALGREEN|MCKESSON|CARDINAL HEALTH|MEDLINE|PILLPACK",
 'Health tech & Health IT': r"CERNER|ATHENAHEALTH|ECLINICALWORKS|INTERSYSTEMS|TELADOC|INOVALON|COTIVITI|CHANGE HEALTHCARE|GAINWELL|EDIFECS|HEALTHEDGE|CITIUSTECH|VIZIENT|CEREBRAL",
 'Hospitals & Health systems': r"HOSPITAL|MEDICAL CENTER|HEALTH SYSTEM|CLINIC\b|CLINIC FOUNDATION|MAYO CLINIC|NORTHWELL|MASS GENERAL|GENERAL HOSPITAL CORP|STANFORD HEALTH CARE|HCA MANAGEMENT|DAVITA|FRESENIUS|PEACEHEALTH|PRESBYTERIAN HEALTHCARE|OSF |OCHSNER|GEISINGER|MARSHFIELD|SANFORD CLINIC|HEALTHCARE SYSTEM|NORTHWESTERN MEMORIAL|MEDSTAR|BAPTIST HEALTH|HARTFORD HEALTHCARE|BANNER UNIVERSITY MEDICAL|ADVENTIST HEALTH|HENRY FORD HEALTH|BRONXCARE|UPMC|PHYSICIANS ORGANIZATION|PHYSICIAN AFFILIATE|UNIVERSITY OF PITTSBURGH PHYSICIANS|HEALTH SERVICES FOUNDATION|VCU HEALTH|FAMILY HEALTHCARE NETWORK|MEDICAL GROUP|PRISTINE REHAB|MENTAL HEALTH CENTER|CANCER CENTER|CANCER INSTITUTE|MOUNT SINAI HOSPITAL|DEVEREUX|MULTI-SPECIALTY",
 'Academic medicine & Research': r"SCHOOL OF MEDICINE|COLLEGE OF MEDICINE|MEDICAL COLLEGE|MEDICAL SCHOOL|HEALTH SCIENCE|MEDICAL SCIENCES|MEDICAL BRANCH|MEDICAL UNIVERSITY|MEDICAL CENTER|HEALTH CENTER|NATIONAL INSTITUTES OF HEALTH|FOOD AND DRUG ADMIN|HOWARD HUGHES|BROAD INSTITUTE|SALK INSTITUTE|SCRIPPS RESEARCH|JACKSON LABORATORY|COLD SPRING HARBOR|FRED HUTCHINSON|BECKMAN RESEARCH|CITY OF HOPE|METHODIST HOSPITAL RESEARCH|BIOMEDICAL RESEARCH|ROCKEFELLER UNIVERSITY|OREGON HEALTH & SCIENCE|UNIVERSITY OF CALIFORNIA SAN FRANCISCO|MD ANDERSON|MEMORIAL SLOAN|DANA-FARBER|MOFFITT|ST JUDE CHILDREN",
}
EXCLUDE = r"BANKERS HEALTHCARE|VERITAS HEALTHCARE SOLUTIONS|UNICON PHARMA"  # finance / IT staffing names that only look healthcare
order=['Pharmacy & Distribution','CRO & Life-sci services','Pharma & Biotech','Healthcare & life-sci consulting','Health tech & Health IT','Life-sci tools & Diagnostics','MedTech & Devices','Payers & Pharmacy benefits','Academic medicine & Research','Hospitals & Health systems']

ROW = re.compile(r'^\s+(\d{1,4})\s{2,}(.+?)\s+\(index\.php\?')
NUMS = re.compile(r'([\d,]+)\s+\$([\d,]+)\s+Latest')

def norm(n): return re.sub(r'[^A-Z0-9]', '', n)

def sector_for(name):
    if re.search(EXCLUDE, name): return ''
    for s in order:
        if re.search(SECTOR_RULES[s], name): return s
    return ''

def main(pdf, out='companies.csv'):
    text = subprocess.run(['pdftotext', '-layout', pdf, '-'], capture_output=True, text=True, check=True).stdout
    lines = text.split('\n'); seen = set(); rows = []
    for i, line in enumerate(lines):
        m = ROW.match(line)
        if not m: continue
        rank, name = int(m.group(1)), m.group(2).strip()
        n = NUMS.search(line + ' ' + (lines[i+1] if i+1 < len(lines) else ''))
        if norm(name) in seen: continue
        seen.add(norm(name))
        sec = sector_for(name)
        rows.append(dict(rank=rank, company=name,
                         h1b_filings=n.group(1).replace(',', '') if n else '',
                         avg_salary=n.group(2).replace(',', '') if n else '',
                         tier=1 if sec else 2, sector=sec or 'Other'))
    with open(out, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f"{len(rows)} companies written to {out} ({sum(r['tier']==1 for r in rows)} Tier 1)")

if __name__ == '__main__':
    if len(sys.argv) < 2: sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).resolve().parent.parent / 'companies.csv'))
