// Exercise the kit's real FoamyI18n substitution and plural code with the
// plugin catalogs in pure node tests.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../kit/FoamyI18n.qml'), 'utf8');
const start = source.indexOf('  function englishText(');
const end = source.lastIndexOf('}');
const en = require('../i18n/en.json');
const no = require('../i18n/no.json');
function plural(entry, count) {
  if (entry && typeof entry === 'object') return Math.abs(Number(count)) === 1 ? entry.one : entry.other;
  return entry;
}
function scope(language) {
  const catalog = language === 'no' || language === 'nb' ? no : en;
  const context = vm.createContext({ english: en, backend: null, root: null });
  vm.runInContext(source.slice(start, end), context);
  context.root = { number: (v, d) => (d === undefined ? String(v) : Number(v).toFixed(d)) };
  context.backend = {
    t(label, fallback) { return Object.hasOwn(catalog, label) && typeof catalog[label] === 'string' ? catalog[label] : fallback; },
    tn(label, count, fallback) { return Object.hasOwn(catalog, label) ? plural(catalog[label], count) : fallback; },
    number: context.root.number,
  };
  return context;
}
function text(key, language, values) { return scope(language).t(key, values); }
function plural_text(key, count, language) { return scope(language).tn(key, count); }
module.exports = { text, tn: plural_text, no, en, norwegian: no, nb: no };
