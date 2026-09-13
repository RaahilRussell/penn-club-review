const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const html = fs.readFileSync(path.join(__dirname, '../templates/index.html'), 'utf8');
const source = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const tick = () => new Promise(resolve => setImmediate(resolve));

// Small DOM and transport doubles exercise the actual page script without a browser dependency.
function harness() {
  const nodes = {};
  function element() {
    return {
      value: '', children: [], events: {}, attributes: {}, textContent: '',
      set innerHTML(value) { this.html = value; this.children = []; },
      get innerHTML() { return this.html || ''; },
      replaceChildren(...children) { this.children = children; this.html = ''; },
      setAttribute(key, value) { this.attributes[key] = value; },
      addEventListener(key, callback) { this.events[key] = callback; },
      focus() {},
    };
  }
  const requests = [];
  const context = vm.createContext({
    document: {
      querySelector: selector => nodes[selector] ||= element(),
      createElement: element,
    },
    fetch: (url, options) => new Promise((resolve, reject) => requests.push({
      url, options, reject,
      respond: (data, status = 200) => resolve({ ok: status < 400, status, json: async () => data }),
      html: () => resolve({ ok: false, status: 500, json: async () => { throw Error('HTML'); } }),
    })),
    setTimeout, clearTimeout, FormData: class {
      constructor(form) { this.form = form; }
      get(key) { return this.form.values[key]; }
    },
    window: { prompt: () => 'Updated description' },
  });
  vm.runInContext(source, context);
  const run = code => vm.runInContext(code, context);
  const pending = url => requests.find(request => request.url === url && !request.used);
  const respond = (url, data) => { const request = pending(url); assert.ok(request, url); request.used = true; request.respond(data); };
  return { nodes, requests, run, respond, pending };
}
const club = {code: 'sample', name: 'Sample', description: 'Full description', tags: ['Technology']};

async function ready() {
  const h = harness();
  h.respond('/api/users/josh', {favorites: []});
  h.respond('/api/tags', []);
  await tick();
  h.respond('/api/clubs', []);
  await tick();
  return h;
}

test('initial cards wait for persisted favorites; popular tags use counts', async () => {
  const h = harness();
  assert.equal(h.pending('/api/clubs'), undefined);
  h.respond('/api/tags', [{name: 'Academic', club_count: 1}, {name: 'Undergraduate', club_count: 4}]);
  h.respond('/api/users/josh', {favorites: [club]});
  await tick();
  h.respond('/api/clubs', [club]);
  await tick();
  assert.match(h.nodes['#clubs'].children[0].innerHTML, /Favorited/);
  assert.match(h.nodes['#tags'].children[0].textContent, /^Undergraduate/);
});

test('older searches cannot overwrite newer results', async () => {
  const h = await ready();
  h.nodes['#search'].value = 'old';
  const old = h.run('loadClubs()');
  await tick();
  h.nodes['#search'].value = 'new';
  const latest = h.run('loadClubs()');
  await tick();
  h.respond('/api/clubs?search=new', [{...club, name: 'Newest'}]);
  await latest;
  h.respond('/api/clubs?search=old', [{...club, name: 'Stale'}]);
  await old;
  assert.match(h.nodes['#clubs'].children[0].innerHTML, /Newest/);
  assert.doesNotMatch(h.nodes['#clubs'].children[0].innerHTML, /Stale/);
});

test('JSON, HTML and network failures clear loading and can recover', async () => {
  for (const failure of ['json', 'html', 'network']) {
    const h = await ready();
    const loading = h.run('loadClubs()');
    await tick();
    const request = h.pending('/api/clubs');
    request.used = true;
    if (failure === 'json') request.respond({error: 'Try again'}, 503);
    if (failure === 'html') request.html();
    if (failure === 'network') request.reject(Error('Offline'));
    await loading;
    assert.equal(h.nodes['#clubs'].attributes['aria-busy'], 'false');
    assert.match(h.nodes['#clubs'].children[0].textContent, /retry/i);
    const recovery = h.run('loadClubs()');
    await tick();
    h.respond('/api/clubs', []);
    await recovery;
    assert.match(h.nodes['#clubs'].children[0].textContent, /No clubs match/);
  }
});

test('mutations encode path values and editing matches the description label', async () => {
  const h = await ready();
  const edited = h.nodes['#clubs'].events.click({target: {dataset: {edit: 'a?#'}, closest: () => ({querySelector: () => ({textContent: 'Original'})})}});
  const request = h.pending('/api/clubs/a%3F%23');
  assert.ok(request);
  assert.deepEqual(JSON.parse(request.options.body), {description: 'Updated description'});
  request.respond(club);
  await tick();
  h.respond('/api/clubs', []);
  await edited;
  assert.match(h.run('clubCard(' + JSON.stringify(club) + ').innerHTML'), /Edit description/);
});

test('club text is escaped and full descriptions remain available', async () => {
  const h = await ready();
  const markup = h.run('clubCard(' + JSON.stringify({...club, description: '<script>bad</script>'}) + ').innerHTML');
  assert.ok(markup.includes('&lt;script&gt;bad&lt;/script&gt;'));
  assert.doesNotMatch(html, /-webkit-line-clamp/);
});

test('create form sends real contract and preserves input on failure', async () => {
  const h = await ready();
  const form = {values: {code: 'new', name: 'New', description: 'Description', tags: 'Technology, Graduate'}, reset() { this.resetCalled = true; }};
  const submit = () => h.nodes['#create-form'].events.submit({preventDefault() {}, target: form});
  const failed = submit();
  let request = h.pending('/api/clubs');
  request.used = true;
  assert.equal(request.options.method, 'POST');
  assert.deepEqual(JSON.parse(request.options.body).tags, ['Technology', 'Graduate']);
  request.respond({error: 'Duplicate code'}, 409);
  await failed;
  assert.equal(form.resetCalled, undefined);
  assert.match(h.nodes['#status'].textContent, /Duplicate code/);
  const success = submit();
  request = h.pending('/api/clubs');
  request.used = true;
  request.respond(club, 201);
  await tick();
  h.respond('/api/clubs', [club]);
  h.respond('/api/tags', []);
  await success;
  assert.equal(form.resetCalled, true);
});

test('favorite posts Josh, encodes the code and refreshes persisted state', async () => {
  const h = await ready();
  const action = h.nodes['#clubs'].events.click({target: {dataset: {favorite: 'a?#'}}});
  const request = h.pending('/api/clubs/a%3F%23/favorites');
  assert.deepEqual(JSON.parse(request.options.body), {username: 'josh'});
  request.respond({favorites: [club]});
  await tick();
  h.respond('/api/clubs', [club]);
  await action;
  assert.match(h.nodes['#clubs'].children[0].innerHTML, /Favorited/);
});

test('out-of-order favorite responses preserve both saved favorites', async () => {
  const h = await ready();
  const other = {...club, code: 'other'};
  const click = code => h.nodes['#clubs'].events.click({target: {dataset: {favorite: code}}});
  const first = click(club.code);
  const second = click(other.code);
  h.respond('/api/clubs/other/favorites', {favorites: [club, other]});
  await tick();
  h.respond('/api/clubs', [club, other]);
  await second;
  h.respond('/api/clubs/sample/favorites', {favorites: [club]});
  await tick();
  h.respond('/api/clubs', [club, other]);
  await first;
  for (const card of h.nodes['#clubs'].children) {
    assert.match(card.innerHTML, /disabled>Favorited/);
  }
});

test('unexpected JSON error bodies still produce a useful status message', async () => {
  for (const body of [null, {}, {error: {detail: 'Unavailable'}}]) {
    const h = await ready();
    const result = h.run("api('/api/example').catch(error => error.message)");
    h.pending('/api/example').respond(body, 503);
    assert.equal(await result, 'Request failed (503). Please retry.');
  }
});
