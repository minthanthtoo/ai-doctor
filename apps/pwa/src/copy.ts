// Keyed bilingual copy (R4.1). Single source of truth for my/en UI strings.
// The parity test (state.test.ts → copyParity) fails the build when the two
// locales drift, so adding a key in one locale forces its twin.

export type Language = "my" | "en";
export type CopyKey =
  | "title"
  | "subtitle"
  | "preclinical"
  | "unlock"
  | "create"
  | "recovery"
  | "today"
  | "concern"
  | "measurements"
  | "medications"
  | "documents"
  | "timeline"
  | "evidence"
  | "privacy"
  | "emergency"
  | "incomplete"
  | "checked"
  | "possibilities"
  | "notDiagnosis"
  | "save"
  | "sync";

export const COPY: Record<Language, Record<CopyKey, string>> = {
  en: {
    title: "Personal Health Steward",
    subtitle: "Private longitudinal record · Myanmar · Preclinical",
    preclinical:
      "This is a preclinical organizer, not a medical service. No clinician monitors this record.",
    unlock: "Unlock local record",
    create: "Create encrypted record",
    recovery: "Recovery kit",
    today: "Today",
    concern: "New concern",
    measurements: "Measurements",
    medications: "Medications",
    documents: "Documents",
    timeline: "Timeline",
    evidence: "Evidence",
    privacy: "Privacy",
    emergency: "Potential emergency warning signs were identified",
    incomplete: "More information is required",
    checked: "Configured checks completed",
    possibilities: "Possibility map",
    notDiagnosis: "These are possibilities to organize questions, not diagnoses.",
    save: "Save",
    sync: "Sync encrypted events",
  },
  my: {
    title: "ကိုယ်ပိုင်ကျန်းမာရေး အကူအညီစနစ်",
    subtitle: "ကိုယ်ပိုင်မှတ်တမ်း · မြန်မာ · စမ်းသပ်ဆဲ",
    preclinical:
      "ဤစနစ်သည် စမ်းသပ်ဆဲမှတ်တမ်းကူညီစနစ်ဖြစ်ပြီး ဆေးကုသမှုဝန်ဆောင်မှု မဟုတ်ပါ။ ဆရာဝန်က ဤမှတ်တမ်းကို စောင့်ကြည့်နေခြင်း မရှိပါ။",
    unlock: "ကိုယ်ပိုင်မှတ်တမ်း ဖွင့်ရန်",
    create: "လုံခြုံသောမှတ်တမ်း ဖန်တီးရန်",
    recovery: "ပြန်လည်ရယူရေးကုဒ်",
    today: "ယနေ့",
    concern: "အခြေအနေအသစ်",
    measurements: "တိုင်းတာချက်များ",
    medications: "ဆေးဝါးမှတ်တမ်း",
    documents: "စာရွက်စာတမ်းများ",
    timeline: "အချိန်လိုက်မှတ်တမ်း",
    evidence: "အထောက်အထား",
    privacy: "ကိုယ်ရေးအချက်အလက်",
    emergency: "အရေးပေါ်အန္တရာယ်လက္ခဏာ ဖြစ်နိုင်သည်",
    incomplete: "အချက်အလက် ထပ်မံလိုအပ်သည်",
    checked: "သတ်မှတ်ထားသော စစ်ဆေးမှုများ ပြီးစီးသည်",
    possibilities: "ဖြစ်နိုင်ခြေများ",
    notDiagnosis:
      "ဤအချက်များသည် မေးခွန်းများကို စုစည်းရန်သာဖြစ်ပြီး ရောဂါအတည်ပြုချက် မဟုတ်ပါ။",
    save: "သိမ်းရန်",
    sync: "လုံခြုံသောမှတ်တမ်းများ ပို့ရန်",
  },
};

export function copyFor(language: Language): Record<CopyKey, string> {
  return COPY[language];
}
