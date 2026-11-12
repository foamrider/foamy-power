const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const I = require('./i18n.cjs');
const manifest = require('../manifest.json');
const tokens = s => [...s.matchAll(/%[1-9][0-9]*|\{\w+\}/g)].map(m => m[0]).sort();
for (const [key, value] of Object.entries(I.en)) {
  if (typeof value === 'object') {
    assert.equal(value.other, key, `English plural source key: ${key}`);
    assert.ok(typeof I.no[key] === 'object', `Norwegian plural for ${key}`);
    for (const form of ['one', 'other']) assert.deepEqual(tokens(I.no[key][form]), tokens(key), key);
    continue;
  }
  assert.equal(value, key, `English source key: ${key}`);
  assert.ok(Object.hasOwn(I.no, key), `Norwegian translation for ${key}`);
  assert.deepEqual(tokens(I.no[key]), tokens(value), key);
}
// Every string the plugin asks for has a catalog entry.
const used = new Set();
for (const file of fs.readdirSync(path.join(__dirname, '..')).filter(f => /\.(qml|js)$/.test(f)))
  for (const m of fs.readFileSync(path.join(__dirname, '..', file), 'utf8').matchAll(/(?:\btr|FoamyI18n\.tn?)\(\s*"((?:[^"\\]|\\.)*)"/g)) used.add(JSON.parse(`"${m[1]}"`));
for (const key of used) assert.ok(Object.hasOwn(I.en, key), `catalog entry for ${key}`);
// Every message the native helper can reply with reaches Panel.qml's
// FoamyI18n.t() and needs a translation: its fixed messages, and each
// `{program}` template for every program it runs (a closed set).
const helper = fs.readFileSync(path.join(__dirname, '../native/src/main.rs'), 'utf8').split('#[cfg(test)]')[0];
const programs = [...new Set([...helper.matchAll(/\brun\(\s*"([^"]+)"/g)].map(m => m[1]))];
const templates = [...helper.matchAll(/format!\(\s*"([^"]*\{program\}[^"]*)"/g)].map(m => m[1]);
const fixed = [...helper.matchAll(/(?:failure\(\s*"[A-Z_]+",\s*|const [A-Z_]+: &str = )"([A-Z][^"{}]*\.)"/g)].map(m => m[1]);
assert.deepEqual(programs.sort(), ['busctl', 'omarchy-powerprofiles-set'], 'programs the helper runs');
assert.equal(templates.length, 2, 'helper message templates');
const replies = [...fixed, ...templates.flatMap(t => programs.map(p => t.replace('{program}', p)))];
assert.ok(fixed.length >= 10, `fixed helper messages: ${fixed.length}`);
for (const message of replies) {
  assert.ok(Object.hasOwn(I.en, message), `catalog entry for the helper's "${message}"`);
  assert.notEqual(I.text(message, 'no'), message, `Norwegian for the helper's "${message}"`);
}
assert.equal(manifest.barWidget?.defaults?.language, undefined);
assert.equal((manifest.barWidget?.schema || []).some(f => f.key === 'language'), false);
assert.equal(I.text('Unknown %1 {name}', 'no', ['$& %2']), 'Unknown $& %2 {name}');
assert.equal(I.text('constructor', 'no'), 'constructor');
assert.equal(I.text('%1 h %2 min', 'no', ['3', '12']), '3 t 12 min');
assert.equal(I.text('%1%', 'no', ['68']), '68 %');
console.log('Power i18n catalog tests passed');
