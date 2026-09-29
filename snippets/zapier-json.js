// Paste into Code by Zapier > Run JavaScript. Configure Input Data as in docs/zapier.md.
// Build JSON in code so quotes, newlines, and booleans survive field mapping.
const booleanValue = inputData.fail_once;
if (![undefined, null, '', true, false, 'true', 'false'].includes(booleanValue)) {
  throw new Error('fail_once must be true or false');
}
const payload = {
  event_id: inputData.event_id,
  customer_email: inputData.customer_email,
  message: inputData.message,
  fail_once: booleanValue === true || booleanValue === 'true',
};
if (inputData.queue) {
  payload.category = inputData.category;
  payload.priority = inputData.priority;
  payload.queue = inputData.queue;
  payload.source = 'zapier';
}
return { body: JSON.stringify(payload) };
