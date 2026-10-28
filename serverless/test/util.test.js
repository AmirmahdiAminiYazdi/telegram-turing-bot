import test from 'node:test';
import assert from 'node:assert/strict';
import { parsePrice, esc, fmt } from '../tgcloud/lib/util.js';

test('parsePrice: ارقام فارسی/عربی، جداکننده و ورودی نامعتبر', () => {
  assert.equal(parsePrice('۱٬۲۰۰٬۰۰۰'), 1200000);
  assert.equal(parsePrice('٣٠٠٠٠'), 30000);
  assert.equal(parsePrice('1,500'), 1500);
  assert.equal(parsePrice('0'), null);
  assert.equal(parsePrice('-5'), null);
  assert.equal(parsePrice('12abc'), null);
  assert.equal(parsePrice(''), null);
});

test('esc: HTML امن', () => {
  assert.equal(esc('<b>&</b>'), '&lt;b&gt;&amp;&lt;/b&gt;');
  assert.equal(esc(null), '');
});

test('fmt: جداکننده هزارگان', () => assert.equal(fmt(1234567), '1,234,567'));
