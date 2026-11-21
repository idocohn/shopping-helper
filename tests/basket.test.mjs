import {test} from 'node:test';
import assert from 'node:assert/strict';
import {pdfRows, parseOrder, parseBasket, pack, cost, summarize, candidatesFor} from '../mcp_server/basket/comparison.mjs';

test('reads Hebrew rows in visual order and carries a grocery item across pages', () => {
  const items = [
    {str: 'גרם', dir: 'rtl', transform: [0, 0, 0, 0, 5, 200]},
    {str: '394', dir: 'ltr', transform: [0, 0, 0, 0, 25, 200]},
    {str: 'מיונז אמיתי הלמנס |', dir: 'rtl', transform: [0, 0, 0, 0, 45, 200]},
  ];
  assert.deepEqual(parseOrder([...pdfRows(items), "2 יח' יחידות"]), [
    {name: 'מיונז אמיתי הלמנס', size: '394 גרם', quantity: 2},
  ]);
  assert.deepEqual(parseOrder(['פילה סלמון | מחיר לפי משקל', '1.2 ק"ג יחידות']), [
    {name: 'פילה סלמון', size: '1.2 ק"ג', quantity: 1},
  ]);
});

test('accounts for pack size, discrete packs, and different unit dimensions', () => {
  assert.deepEqual(pack('3 יח׳, 400 גרם ליח׳'), {dimension: 'mass', amount: 1200});
  assert.deepEqual(pack('1.50 1ליטר', true), {dimension: 'volume', amount: 1500});
  assert.equal(pack('4 * 56 יחידות').amount, 224);
  assert.deepEqual(cost({size: '394 גרם', quantity: 2}, {size_text: '500 גרם', price_nis: 8.2}), {
    packages: 2, cents: 1640, comparable: true,
  });
  assert.equal(cost({size: '394 גרם', quantity: 2}, {size_text: '500 מ"ל', price_nis: 8.2}).comparable, false);
});

test('ranks an exact pack but preserves percentage variants and filters unavailable products', () => {
  const lines = parseBasket('חלב 3% תנובה | 2 | 1 ליטר\nמיונז | 1 | 500 גרם');
  const candidates = candidatesFor(lines[0], [
    {name: 'חלב 1% תנובה', price_nis: 7, size_text: '1 ליטר', in_stock: true},
    {name: 'חלב 3% תנובה', price_nis: 5, size_text: '1 ליטר', in_stock: false},
    {name: 'חלב 3% תנובה', price_nis: 8, size_text: '1 ליטר', in_stock: true},
  ]);
  assert.equal(candidates.length, 2);
  assert.equal(candidates[0].product.price_nis, 8);
  assert.ok(candidates[0].exactName);
  assert.equal(candidates[1].exactName, false);
});

test('compares shared items and avoids calling a partial basket complete', () => {
  const lines = parseBasket('חלב | 2 | 1 ליטר\nמיונז | 1 | 500 גרם');
  const milk = {size_text: '1 ליטר', price_nis: 7};
  const mayo = {size_text: '500 גרם', price_nis: 8.2};
  const [partial, complete] = summarize(lines, [{selected: [milk, null]}, {selected: [milk, mayo]}]);
  assert.equal(partial.complete, false);
  assert.equal(complete.complete, true);
  assert.equal(complete.sharedCount, 1);
  assert.equal(complete.sharedTotal, 1400);
  assert.equal(complete.total, 2220);
});
