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
  link.searchParams.set('products', [...quantities].sort(([left], [right]) => left.localeCompare(right))
    .map(([id, quantity]) => id + ':' + quantity).join(','));
  return link.href;
}

export async function openHahishookCart(items) {
  const link = checkoutUrl(items);
  if (!link) throw new Error('Select at least one item before opening the cart.');
  const tab = window.open('about:blank', '_blank');
  if (!tab) throw new Error('Your browser blocked the cart tab. Allow pop-ups for this site and try again.');
  tab.document.title = 'Opening Hahishook cart';
  tab.document.body.textContent = 'Opening your Hahishook cart…';
  tab.location.replace(link);

  // The storefront writes the native cart cookie before navigating across origins.
  // Wait for that navigation to commit without reading a storefront URL or session token.
  await new Promise((resolve, reject) => {
    const timer = setInterval(() => {
      if (tab.closed) {
        finish(new Error('The Hahishook tab closed. Check your cart before trying again.'));
        return;
      }
      try {
        void tab.location.origin;
      } catch (error) {
        if (error.name !== 'SecurityError') {
          finish(new Error('Could not open the Hahishook cart. Check it before trying again.'));
          return;
        }
        try {
          tab.location.replace('https://hahishook.com/cart/');
          finish();
        } catch {
          finish(new Error('Hahishook opened, but the cart page could not be reached automatically. Check your cart below.'));
        }
      }
    }, 60);
    const timeout = setTimeout(() => finish(new Error('Hahishook took too long to respond. Check your cart before trying again.')), 15000);
    function finish(error) {
      clearInterval(timer);
      clearTimeout(timeout);
      if (error) reject(error);
      else resolve();
    }
  });
}
