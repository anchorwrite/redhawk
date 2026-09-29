const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const code = fs.readFileSync(path.join(__dirname, '../snippets/zapier-json.js'), 'utf8');
const serialize = new Function('inputData', code);

test('preserves quoted multiline text and real booleans', () => {
  const input = { event_id: 'one', customer_email: 'a@example.test', message: 'A "quote"\nand a newline', fail_once: 'false' };
  const payload = JSON.parse(serialize(input).body);
  assert.equal(payload.message, input.message);
  assert.equal(payload.fail_once, false);
  assert.equal(JSON.parse(serialize({ ...input, fail_once: 'true' }).body).fail_once, true);
});

test('ticket mode adds platform source and queue', () => {
  const payload = JSON.parse(serialize({ event_id: 'two', queue: 'review', category: 'incident', priority: 'high' }).body);
  assert.equal(payload.source, 'zapier');
  assert.equal(payload.queue, 'review');
  assert.equal(payload.category, 'incident');
});

test('rejects ambiguous boolean values and leaves missing email for API validation', () => {
  assert.throws(() => serialize({ fail_once: 'yes' }), /true or false/);
  assert.equal(Object.hasOwn(JSON.parse(serialize({ event_id: 'bad' }).body), 'customer_email'), false);
});
