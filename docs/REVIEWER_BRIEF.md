# Reviewer Brief — AI Doctor OS / Personal Health Steward

**Purpose of this document:** recruit one Myanmar clinical reviewer and one Burmese-language reviewer for preclinical content. Nothing here requests clinical endorsement of an unvalidated system; it asks qualified people to help define, check, and bound what the software says about health before anyone else relies on it.

---

## What the system is

A local-first personal health organizer (Burmese/English PWA plus a private home-server relay). It keeps an encrypted record of concerns, measurements, medications, and documents; runs deterministic red-flag screening that can lock the app into an emergency-seeking state; and produces strictly bounded "possibility" information from a small reviewed knowledge pack. It is explicitly **not** a diagnosis, treatment, or prescribing tool, and no model output can change its safety behavior.

## What would be reviewed

The entire clinical surface fits in one sitting — that is the point:

- **Cardiometabolic pack** (`src/ai_doctor/knowledge/v3/cardiometabolic_pack.json`): 7 red-flag symptom rules (e.g., chest pressure, breathing difficulty, sudden facial droop/weakness/slurred speech), 6 home-vital rules, 5 guided-intake questions, 3 evidence entries. Bilingual fields throughout; jurisdiction marked MM; `approved_for_clinical_use=false`.
- **Wording shown in emergencies** (fixed strings: seek urgent care now; never a "you are fine" message).
- **Burmese-language parity** of every user-facing string against intended clinical meaning.

## What review requires

1. Read the pack JSON and mark each rule clinically appropriate or not, with corrections.
2. Review the Burmese renderings with two questions: does it say the clinical thing, and would a layperson in Myanmar understand the action requested?
3. Sign a short statement naming scope ("these 7 rules + these strings") — never a general endorsement.

Estimated effort: 3–4 hours total. The repository supplies diffable bilingual tables on request so nothing needs to be extracted by hand.

## What reviewers get and don't get

- Full source access; the safety architecture is documented honestly (`docs/MASTER_GOAL_STATUS.md`, `docs/security/THREAT_MODEL.md`, `docs/BOUNDARY_ONE_PAGER.md`).
- Named credit as clinical/language review owner in the release manifest once gates pass — or a private acknowledgment if preferred.
- No payment is currently budgeted; this is acknowledged openly rather than hidden.

## Why this matters

Every external gate in the ledger (clinical evaluation CE-01, comprehension HF-01, governance GV-01) is blocked for exactly one reason: no accountable human has reviewed the content. This brief is the smallest honest step to unblock them.

---

*ကိုယ်ရေးအကျဉ်း (စက်ဖြင့်ပြန်ဆိုထားသည် — လူ့စာမေးပွဲစီစစ်မှုမတိုင်မီ ယာယီအသုံးသာဖြစ်ပါသည်):*
*ဤစနစ်သည် ကိုယ်ပိုင်ကျန်းမာရေးမှတ်တမ်းအတွက် စမ်းသပ်ဆဲဆော့ဖ်ဝဲတစ်ခုသာဖြစ်ပါသည်။ ရောဂါအတည်ပြုချက်၊ ဆေးညွှန်း၊ ကုသမှု မျှ မပါဝင်ပါ။ ကျွန်ုပ်တို့ တောင်းရှာနေသည်မှာ — အကြောင်းအရာ (၇ ခုသော အထူးအခြေအနေစည်းမျဉ်းများ) နှင့် မြန်မာဘာသာပြန်ချက်များကို စစ်ဆေးပေးမည့် ဆရာဝန်တစ်ဦးနှင့် ဘာသာစကားစီစစ်သူတစ်ဦးဖြစ်ပါသည်။*

---

Contact: Min Thant Htoo <minthanthtoo.cs@gmail.com> · Repository available on request (private mirror).
