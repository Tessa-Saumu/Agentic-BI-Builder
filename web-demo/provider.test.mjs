import test from 'node:test';
import assert from 'node:assert/strict';
import {generateOnline, providerProfile} from './provider.js';
import {DEFAULT_CSV, parseCSV, profileCSV, generateOfflineSpec, runSpec} from './engine.js';

const profile = profileCSV(parseCSV(DEFAULT_CSV));
const plan = generateOfflineSpec(profile);
const answer = spec => ({ok:true, json:async()=>({candidates:[{finishReason:'STOP',content:{parts:[{text:JSON.stringify(spec)}]}}]})});

test('online request uses header credential and metadata only; returned AI plan is executed', async () => {
  const previous = globalThis.fetch;
  const sentinel = 'TEST_KEY_NOT_A_CREDENTIAL';
  let requests = 0;
  try {
    globalThis.fetch = async (url, options) => {
      requests++;
      assert.equal(url, 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent');
      assert.equal(options.headers['x-goog-api-key'], sentinel);
      assert.equal(options.credentials, 'omit');
      assert.equal(options.referrerPolicy, 'no-referrer');
      const body = JSON.parse(options.body);
      assert.equal(body.generationConfig.responseFormat.text.mimeType, 'application/json');
      assert.ok(!options.body.includes(sentinel));
      assert.ok(!options.body.includes('Artist A'));
      assert.ok(!options.body.includes('2026-01-05'));
      assert.ok(!options.body.includes('"min":'));
      assert.ok(!options.body.includes('"max":'));
      assert.ok(!options.body.includes('sampleRows'));
      assert.ok(options.body.includes('Compare countries'));
      return answer({...plan, title:'Provider proposed report'});
    };
    const result = await generateOnline(profile, sentinel, undefined, 'Compare countries');
    assert.equal(result.title, 'Provider proposed report');
    const built = runSpec(parseCSV(DEFAULT_CSV), result);
    assert.equal(built.results.find(r=>r.name==='Total Total').rows[0].value,258);
    assert.equal(requests,1);
    assert.deepEqual(Object.keys(providerProfile(profile).columns[2]).sort(), ['distinctCount','name','nullCount','type']);
  } finally {globalThis.fetch = previous;}
});

test('invalid provider plan gets at most one corrective request', async () => {
  const previous = globalThis.fetch; let calls=0;
  try {
    globalThis.fetch = async () => {calls++; return answer(calls===1?{...plan,kpis:plan.kpis.map((k,i)=>i===0?{...k,column:'invented'}:k)}:plan);};
    assert.equal((await generateOnline(profile,'test')).kpis.length,plan.kpis.length);
    assert.equal(calls,2);
    calls=0; globalThis.fetch = async()=>{calls++;return answer({title:'Bad',kpis:[]});};
    await assert.rejects(generateOnline(profile,'test'),/after one repair/);
    assert.equal(calls,2);
  } finally {globalThis.fetch=previous;}
});

test('auth/quota/network failures are visible and never return offline specs', async () => {
  const previous = globalThis.fetch; let calls=0;
  try {
    for(const status of [400,403,404,429,503]) {
      globalThis.fetch = async()=>{calls++;return {ok:false,status};};
      await assert.rejects(generateOnline(profile,'test'),new RegExp(`HTTP ${status}.*No offline run`));
    }
    assert.equal(calls,5);
    globalThis.fetch=async()=>{throw new Error('Network exception contains a secret');};
    await assert.rejects(generateOnline(profile,'test'),/Could not reach Gemini/);
    await assert.rejects(generateOnline(profile,'test','https://other-host.example'),/model ID/);
  } finally {globalThis.fetch=previous;}
});

test('cancelled request ends and no provider error body is exposed', async () => {
  const previous = globalThis.fetch;
  try {
    globalThis.fetch=async(_url, options)=>{assert.ok(options.signal.aborted);throw new Error('test');};
    const controller=new AbortController();controller.abort();
    await assert.rejects(generateOnline(profile,'test',undefined,'',controller.signal),/cancelled/);
  } finally {globalThis.fetch=previous;}
});
