var defaults = {language:"system",showPercentage:false,showPercentageWhenLow:false}
function valid(key,value) { return key === "language" ? ["system","en","nb"].indexOf(value)>=0 : ["showPercentage","showPercentageWhenLow"].indexOf(key)>=0 && typeof value === "boolean" }
function value(settings,key) { return settings && valid(key,settings[key]) ? settings[key] : defaults[key] }
function showBarPercentage(settings,fraction,discharging) {
  // Match Omarchy's warning: the rounded battery level is at most 10% while discharging.
  return value(settings,"showPercentage") && (!value(settings,"showPercentageWhenLow") || (discharging
    && typeof fraction === "number" && isFinite(fraction) && fraction >= 0 && fraction <= 1
    && Math.round(fraction*100) <= 10))
}
function language(mode,locale) { return mode === "en" || mode === "nb" ? mode : /^(nb|nn|no)(_|-|$)/i.test(locale || "") ? "nb" : "en" }
var norwegian = {
  "Power":"Strøm", "Settings":"Innstillinger", "General":"Generelt", "Back":"Tilbake", "Language":"Språk", "System":"System",
  "Show bar percentage":"Vis prosent i panelet", "Power profile":"Strømprofil", "Battery details":"Batteridetaljer",
  "Show only when battery is low":"Vis bare ved lavt batterinivå",
  "Default power profiles":"Standard strømprofiler", "Plugged in (AC)":"Tilkoblet strøm (AC)", "On battery (DC)":"På batteri (DC)",
  "Power saver":"Strømsparing", "Balanced":"Balansert", "Performance":"Ytelse", "Unavailable":"Utilgjengelig",
  "Full capacity":"Full kapasitet", "Charge cycles":"Ladesykluser", "Charging":"Lader", "On battery":"På batteri",
  "Charge limit":"Ladegrense", "Fully charged":"Fulladet", "Connected":"Tilkoblet", "Charging at":"Ladeeffekt",
  "Discharging at":"Strømforbruk", "Battery state":"Batteristatus", "Holding":"Holder nivået", "Time to full":"Tid til fulladet",
  "Time left":"Tid igjen", "%1 to full":"%1 til fulladet", "%1 left":"%1 igjen", "Holding at %1%":"Holder på %1 %",
  "Connected to power":"Tilkoblet strøm", "Battery unavailable":"Batteridata utilgjengelig", "No battery detected":"Ingen batterier funnet",
  "Reading battery…":"Leser batteridata…", "Saving…":"Lagrer…", "Retry":"Prøv igjen", "Could not save settings.":"Kunne ikke lagre innstillingene.",
  "Invalid power status.":"Ugyldige strømdata.", "Power query failed. Try again.":"Kunne ikke hente strømdata. Prøv igjen.",
  "Power action failed. Try again.":"Kunne ikke endre strømprofil. Prøv igjen.",
  "A profile selected from the main view lasts until the power source changes.":"En profil valgt i hovedvisningen varer til strømkilden endres.",
  "Battery readings are stale. Try again.":"Batteridata er utdaterte. Prøv igjen.",
  "Cycle counts are per battery; no combined value is available.":"Ladesykluser gjelder hvert batteri; en samlet verdi er ikke tilgjengelig."
}
function text(label,lang) { return lang === "nb" ? norwegian[label] || label : label }
if (typeof module !== "undefined") module.exports={defaults:defaults,valid:valid,value:value,showBarPercentage:showBarPercentage,language:language,text:text}
