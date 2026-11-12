// Exercise the kit's real substitution and plural code (kit/FoamyI18nText.js,
// which FoamyI18n.qml substitutes through) with the plugin catalogs in pure
// node tests.
const I18n = require('../kit/node-loader.cjs').load('FoamyI18nText');
const en = require('../i18n/en.json');
const no = require('../i18n/no.json');
const number = (v, d) => (d === undefined ? String(v) : Number(v).toFixed(d));
const translators = { en: I18n.translator(en, en, number), no: I18n.translator(no, en, number) };
const scope = language => translators[language === 'no' || language === 'nb' ? 'no' : 'en'];
function text(key, language, values) { return scope(language).t(key, values); }
function plural_text(key, count, language) { return scope(language).tn(key, count); }
module.exports = { text, tn: plural_text, no, en, norwegian: no, nb: no };
