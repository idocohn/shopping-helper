const quantityPattern = /^(\d+(?:\.\d+)?)\s*(יח\s*['׳]|יחידה|יחידות|ק\s*["״]?\s*ג|גרם)\s*(?:יחידות)?$/u;

export function pdfRows(items) {
  const rows = [];
  for (const item of items) {
    if (!item.str?.trim()) continue;
    const y = item.transform[5];
    let row = rows.find(row => Math.abs(row.y - y) < 2);
    if (!row) {
      row = {y, items: []};
      rows.push(row);
    }
    row.items.push(item);
  }
  return rows.sort((a, b) => b.y - a.y).map(row => {
    const rtl = row.items.some(item => item.dir === 'rtl');
    return row.items.sort((a, b) => (rtl ? -1 : 1) * (a.transform[4] - b.transform[4]))
      .map(item => item.str.trim()).join(' ').replace(/[\u200e\u200f\u202a-\u202e]/g, '');
  });
}

export function parseOrder(rows) {
  const lines = [];
  let item;
  let lastLine;
  let discount = false;
  for (const row of rows) {
    const divider = row.lastIndexOf('|');
    if (divider > 0) {
      const name = row.slice(0, divider).trim();
      const size = row.slice(divider + 1).trim();
      item = /גרם|ליטר|[ממ]"ל|יחידות|גלילים|משקל|\d/u.test(size) ? {name, size} : undefined;
      lastLine = undefined;
      discount = false;
      continue;
    }
    const quantity = row.trim().match(quantityPattern);
    if (item && quantity) {
      const [, amount, unit] = quantity;
      if (/ק|גרם/u.test(unit)) {
        item.size = amount + ' ' + unit;
        item.quantity = 1;
      } else {
        item.quantity = Number(amount);
      }
      lines.push(item);
      lastLine = item;
      item = undefined;
      continue;
    }
    if (!lastLine) continue;
    if (row.trim() === 'הנחה') {
      discount = true;
      continue;
    }
    const amount = row.match(/₪\s*([\d,]+\.\d{2})\s*$/u);
    if (!amount) continue;
    const cents = Math.round(Number(amount[1].replaceAll(',', '')) * 100);
    if (discount && /^\s*-\s*₪/u.test(row) && cents <= lastLine.paidCents) lastLine.paidCents -= cents;
    if (lastLine.paidCents == null && (row.match(/₪/gu) || []).length === 2) lastLine.paidCents = cents;
    discount = false;
  }
  return lines;
}

export function parseBasket(text) {
  return text.split('\n').flatMap(row => {
    const [name, count, size, paid] = row.split('|').map(value => value.trim());
    if (!name) return [];
    const quantity = count ? Number(count) : 1;
    if (!Number.isInteger(quantity) || quantity <= 0 || quantity > 1000) throw new Error('Use a whole-number quantity between 1 and 1,000.');
    const item = {name, quantity, size: size || ''};
    if (paid) {
      const amount = paid.replace(/[₪,\\\s]/gu, '');
      const cents = Math.round(Number(amount) * 100);
      if (!/^\d+(?:\.\d{1,2})?$/u.test(amount) || !Number.isSafeInteger(cents)) throw new Error('Enter the paid line total in shekels, for example 20.00.');
      item.paidCents = cents;
    }
    return [item];
  });
}

export function pack(text, fromFeed = false) {
  const value = (text || '').toLowerCase().replace(/[\\״"׳']/g, '').replace(/מ\s*ל/g, 'מל');
  const unit = '(מיליליטר|ליטר|מל|קילוגרם|קג|גרם|יחידות|גלילים|מגבונים|g|kg|ml|l)';
  const multiply = value.match(new RegExp('(\\d+(?:\\.\\d+)?)\\s*[*×x]\\s*(\\d+(?:\\.\\d+)?)\\s*' + unit, 'u'));
  const perUnit = value.match(new RegExp('(\\d+)\\s*יח(?:ידות)?[., ]+\\s*(\\d+(?:\\.\\d+)?)\\s*' + unit + '\\s+ליח', 'u'));
  const packed = value.match(new RegExp('(\\d+(?:\\.\\d+)?)\\s*' + unit + '\\s*[*×x]\\s*(\\d+)\\s*יח(?:ידות)?', 'u'));
  const feed = fromFeed && value.match(new RegExp('^(\\d+(?:\\.\\d+)?)\\s+(?:100|1)\\s*' + unit, 'u'));
  const single = value.match(new RegExp('(\\d+(?:\\.\\d+)?)\\s*' + unit, 'u'));
  const multi = multiply || perUnit || (packed && [packed[0], packed[1], packed[3], packed[2]]);
  const match = multi || feed || single;
  if (!match) return null;
  const amount = Number(match[1]) * (multi ? Number(match[2]) : 1);
  const label = match[multi ? 3 : 2];
  const units = {
    גרם: ['mass', 1], g: ['mass', 1], קג: ['mass', 1000], קילוגרם: ['mass', 1000], kg: ['mass', 1000],
    מל: ['volume', 1], מיליליטר: ['volume', 1], ml: ['volume', 1], ליטר: ['volume', 1000], l: ['volume', 1000],
    יחידות: ['count', 1], מגבונים: ['count', 1], גלילים: ['rolls', 1],
  };
  const [dimension, factor] = units[label];
  return amount > 0 ? {dimension, amount: amount * factor} : null;
}

function productPack(product, wanted) {
  const fromFeed = product.source === 'shufersal';
  const size = pack(product.size_text, fromFeed);
  if (!fromFeed) return size;

  const namedRolls = wanted?.dimension === 'rolls' && product.name?.match(/(\d+)\s*גלילים/u);
  if (namedRolls) return {dimension: 'rolls', amount: Number(namedRolls[1])};
  if (size?.dimension !== 'count' || size.amount !== 1) return size;

  // PriceFull's quantity of one unit can mean one retail pack, not one piece.
  const pieces = product.name?.match(/(\d+)\s*יח(?:ידות)?(?:$|\s)/u);
  if (pieces) return {dimension: 'count', amount: Number(pieces[1])};
  const wipes = product.name?.match(/מגב.*?(\d+)\s*[*×x]\s*(\d+)(?:$|\s)/u);
  return wipes ? {dimension: 'count', amount: Number(wipes[1]) * Number(wipes[2])} : null;
}

function terms(text) {
  const words = text.normalize('NFKC').toLowerCase().replace(/([א-ת])['׳"״]/g, '$1')
    .split(/[^a-zא-ת]+/u).filter(word => word.length > 1 && !['גרם', 'ליטר', 'מיליליטר', 'יחידות', 'מארז', 'בטעם', 'טעם', 'אריזה'].includes(word));
  if (/מחית עגבניות|עגבניות מרוסקות/u.test(text)) words.push('עגבניות מרוסקות');
  return words;
}

function productName(text) {
  return text.normalize('NFKC').toLowerCase().replace(/\s*\d+(?:\.\d+)?\s*(?:גרם|גר|ג['׳]?|ק["״]?ג|ליטר|מ["״]?ל|g|kg|ml|l)\s*$/u, '')
    .replace(/[^a-z0-9א-ת%]+/gu, ' ').trim();
}

const substitutionRules = [
  [/מחית עגבניות/u, /עגבניות מרוסקות/u, 'Crushed tomatoes have a coarser texture than purée.'],
  [/מיונז אמיתי/u, /מיונז אמיתי/u, 'Both are real mayonnaise. Check the catalog brand.'],
  [/מרשמלו.*טוויסטר/u, /^מרשמלו(?: אוורירי)?$/u, 'Plain marshmallows instead of the Twister variety.'],
  [/קרקר דק/u, /קרקר.*דק/u, 'Thin crackers with different seasoning.'],
  [/דובונים/u, /מקלות תפוח אדמה/u, 'Potato sticks instead of bear-shaped snacks.'],
  [/במבה/u, /בולי בוטנים/u, 'Peanut puffs from a different brand.'],
  [/מגבונים.*ללא בישום/u, /מגבונים.*ללא בישום/u, 'Fragrance-free wipes from a different brand.'],
];

function substituteBrand(orderName, product) {
  if (product.source !== 'hahishook') return '';
  const catalogName = `${product.name} ${product.brand || ''}`;
  const hellmanns = /הלמנס|hellmann/iu;
  if (hellmanns.test(orderName) && /מיונז|mayonnaise/iu.test(product.name) && !hellmanns.test(catalogName)) {
    if (String(product.product_id) === '125771' || /hilda|הילדה/iu.test(catalogName)) {
      return 'Hilda mayonnaise is a different brand from Hellmann’s.';
    }
    return 'The catalog brand is unverified for this Hellmann’s substitute.';
  }
  if (/במבה|bamba/iu.test(orderName) && !/בולי|buli/iu.test(orderName) && /בולי|buli/iu.test(catalogName)) {
    return 'Buli peanut puffs are a different brand from Osem Bamba.';
  }
  return '';
}

export function candidatesFor(line, products, limit = 6, eligible = () => true) {
  const input = new Set(terms(line.name));
  if (!input.size) return [];
  const expected = pack(line.size);
  return products.flatMap(product => {
    if (product.in_stock !== true || !Number.isFinite(product.price_nis) || product.price_nis <= 0) return [];
    const words = new Set(terms(product.name));
    if (input.has('עגבניות מרוסקות') && !words.has('עגבניות')) return [];
    const common = [...input].filter(word => words.has(word)).length;
    const rule = product.source === 'hahishook' && substitutionRules.find(([order, candidate]) => order.test(line.name) && candidate.test(product.name));
    if ((!common && !rule) || !eligible(product)) return [];
    const size = productPack(product, expected);
    const compatible = expected && size && expected.dimension === size.dimension;
    const exactSize = compatible && Math.abs(expected.amount - size.amount) < 0.01;
    const score = 2 * common / (input.size + words.size);
    const brandDifference = substituteBrand(line.name, product);
    const exactName = !brandDifference && productName(line.name) === productName(product.name);
    const localDifference = brandDifference || rule?.[2] || (common >= 2 && score >= 0.72 ? 'Compare the product names for brand or variant differences.' : '');
    return [{product, exactName, exactSize, localDifference, brandDifference,
      rank: score + (exactSize ? 0.12 : 0) + (exactName ? 0.2 : 0) + (rule ? 0.15 : 0)}];
  }).sort((a, b) => b.rank - a.rank).slice(0, limit);
}

export function cost(line, product) {
  const wanted = pack(line.size);
  const available = productPack(product, wanted);
  const comparable = Boolean(wanted && available && wanted.dimension === available.dimension);
  const packages = comparable ? Math.ceil(line.quantity * wanted.amount / available.amount - 1e-8) : line.quantity;
  return {packages, cents: Math.round(product.price_nis * 100) * packages, comparable};
}

export function saving(line, product, referenceCents) {
  const price = cost(line, product);
  return price.comparable && Number.isFinite(referenceCents) ? referenceCents - price.cents : null;
}

export function summarize(lines, stores) {
  const shared = lines.filter((_, index) => stores.every(store => store.selected[index] && cost(lines[index], store.selected[index]).comparable));
  return stores.map(store => {
    let matched = 0;
    let total = 0;
    let sharedTotal = 0;
    lines.forEach((line, i) => {
      if (!store.selected[i]) return;
      matched++;
      const {cents} = cost(line, store.selected[i]);
      total += cents;
      if (shared.includes(line)) sharedTotal += cents;
    });
    const complete = matched === lines.length && lines.every((line, i) => cost(line, store.selected[i]).comparable);
    return {...store, total, matched, sharedTotal, sharedCount: shared.length, complete};
  });
}
