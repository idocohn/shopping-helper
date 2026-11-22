export function canCheckout(product) {
  return product?.source === 'hahishook' && /^[1-9]\d*$/u.test(product.product_id || '') && product.in_stock === true;
}

export function checkoutUrl(items) {
  const quantities = new Map();
  for (const {product, quantity} of items) {
    if (!canCheckout(product) || !Number.isSafeInteger(quantity) || quantity < 1) {
      throw new Error('Every checkout item needs a Hahishook product and a positive whole quantity.');
    }
    const id = String(product.product_id);
    quantities.set(id, (quantities.get(id) || 0) + quantity);
    if (!Number.isSafeInteger(quantities.get(id))) throw new Error('The combined product quantity is too large.');
  }
  if (!quantities.size) return null;
  const link = new URL('https://hahishook.com/checkout-link/');
  link.searchParams.set('products', Array.from(quantities, ([id, quantity]) => id + ':' + quantity).join(','));
  return link.href;
}
