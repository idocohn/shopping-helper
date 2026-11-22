import {test} from 'node:test';
import assert from 'node:assert/strict';
import {pdfRows, parseOrder, parseBasket, pack, cost, saving, summarize, candidatesFor} from '../mcp_server/basket/comparison.mjs';
import {canCheckout, checkoutUrl} from '../mcp_server/basket/checkout.mjs';

test('hands only selected Hahishook product IDs and combined quantities to checkout', () => {
  const mayo = {source: 'hahishook', product_id: '125771', in_stock: true};
  const marshmallows = {source: 'hahishook', product_id: '425938', in_stock: true};
  const url = new URL(checkoutUrl([
    {product: mayo, quantity: 2}, {product: marshmallows, quantity: 1}, {product: mayo, quantity: 3},
  ]));
  assert.equal(url.origin, 'https://hahishook.com');
  assert.equal(url.pathname, '/checkout-link/');
  assert.deepEqual([...url.searchParams], [['products', '125771:5,425938:1']]);
  assert.equal(checkoutUrl([]), null);
  assert.equal(canCheckout({...mayo, source: 'shufersal'}), false);
  assert.throws(() => checkoutUrl([{product: mayo, quantity: 1.5}]));
  assert.throws(() => checkoutUrl([{product: {...mayo, product_id: '125771:5'}, quantity: 1}]));
});

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
  assert.equal(pack('25 גרם * 10 יחידות').amount, 250);
  assert.deepEqual(pack('1.20 1קילוגרם', true), {dimension: 'mass', amount: 1200});
  assert.deepEqual(cost({size: '394 גרם', quantity: 2}, {size_text: '500 גרם', price_nis: 8.2}), {
    packages: 2, cents: 1640, comparable: true,
  });
  assert.equal(cost({size: '394 גרם', quantity: 2}, {size_text: '500 מ"ל', price_nis: 8.2}).comparable, false);
});

test('compares wipes by the pieces in each retail pack', () => {
  const line = {size: '4 * 56 יחידות', quantity: 3};
  assert.deepEqual(cost(line, {
    source: 'shufersal', name: 'מגב.האגיס ללא בישום 4*56', size_text: '1.00 יחידות', price_nis: 23.9,
  }), {packages: 3, cents: 7170, comparable: true});
  assert.deepEqual(cost(line, {
    name: 'מארז מגבונים ללא בישום בייביסיטר', size_text: '60*4 מגבונים, ללא בישום', price_nis: 11.9,
  }), {packages: 3, cents: 3570, comparable: true});
  assert.equal(cost(line, {source: 'shufersal', size_text: '1.00 יחידות', price_nis: 25}).comparable, false);
});

test('uses paid receipt totals after item discounts and calculates signed savings', () => {
  const [item] = parseOrder(['מיונז אמיתי הלמנס | 394 גרם', "2 יח' יחידות", '₪3.53 ל100 גרם ₪ 27.80', 'הנחה', '-₪ 7.80']);
  assert.equal(item.paidCents, 2000);
  assert.equal(parseBasket('מיונז | 2 | 394 גרם | 20.00')[0].paidCents, 2000);
  assert.equal(saving(item, {size_text: '500 גרם', price_nis: 8.2}, item.paidCents), 360);
  assert.equal(saving(item, {size_text: '500 גרם', price_nis: 14.9}, item.paidCents), -980);
  assert.equal(saving(item, {size_text: '500 מ"ל', price_nis: 8.2}, item.paidCents), null);
  assert.equal(saving(item, {size_text: '500 גרם', price_nis: 8.2}), null);
});

test('shortlists crushed tomatoes as a substitute candidate for tomato puree', () => {
  const line = {name: 'מחית עגבניות קלה MUTTI', size: '700 גרם'};
  const products = [
    {name: 'מחית קארי ירוקה', size_text: '70 גרם', price_nis: 8.9, in_stock: true},
    {name: 'עגבניות מרוסקות במיץ Polpa שלישיה', size_text: '3 יח׳, 400 גרם ליח׳', price_nis: 11.6, in_stock: true},
  ];
  const [candidate, unrelated] = candidatesFor(line, products);
  assert.equal(candidate.product, products[1]);
  assert.equal(candidate.exactName, false);
  assert.equal(unrelated, undefined);
});

test('offers a grounded substitute even when product names differ and skips options without savings', () => {
  const line = {name: 'דובונים חטיף תפוחי אדמה דובונים', quantity: 9, size: '40 גרם'};
  const base = {source: 'hahishook', size_text: '80 גרם', in_stock: true};
  const products = [
    {...base, name: 'דובונים', price_nis: 9},
    {...base, name: 'מקלות תפוח אדמה', price_nis: 5.3},
  ];
  const [candidate, expensive] = candidatesFor(line, products, 6, product => saving(line, product, 3000) > 0);
  assert.equal(candidate.product, products[1]);
  assert.match(candidate.localDifference, /Potato sticks/);
  assert.equal(expensive, undefined);
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

test('flags Hilda mayonnaise and Buli peanut puffs as brand substitutes even at the same weight', () => {
  const groceries = {source: 'hahishook', size_text: '500 גרם', price_nis: 8.2, in_stock: true};
  const hilda = {...groceries, name: 'מיונז אמיתי', product_id: '125771'};
  const hellmanns = {...groceries, name: 'מיונז אמיתי הלמנס', product_id: '200'};
  const mayo = candidatesFor({name: 'מיונז אמיתי הלמנס', size: '500 גרם'}, [hilda, hellmanns]);
  assert.equal(mayo[0].exactName, true);
  assert.equal(mayo[0].brandDifference, '');
  assert.equal(mayo[1].exactSize, true);
  assert.match(mayo[1].brandDifference, /Hilda.*Hellmann/);

  const buli = {...groceries, name: 'בולי בוטנים (במבה)', size_text: '80 גרם'};
  const [snack] = candidatesFor({name: 'במבה אסם', size: '80 גרם'}, [buli]);
  assert.equal(snack.exactSize, true);
  assert.equal(snack.exactName, false);
  assert.match(snack.brandDifference, /Buli.*Osem Bamba/);
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
