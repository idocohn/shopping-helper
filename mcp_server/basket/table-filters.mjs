const matchChoices = [
  {id: 'all', label: 'All matches', matches: () => true},
  {id: 'good', label: 'Good match', matches: value => value === 'good'},
  {id: 'similar', label: 'Similar', matches: value => value === 'similar'},
];

const columns = {
  item: {type: 'text'},
  match: {type: 'single', choices: matchChoices, sortOrder: ['good', 'similar']},
  product: {type: 'multi'},
  packs: {type: 'range', scale: 1},
  total: {type: 'range', scale: 100},
  savings: {type: 'range', scale: 100},
};

function element(tag, className = '', text = '') {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function normalize(text) {
  return text.normalize('NFKC').trim().toLocaleLowerCase();
}

export function mountTableFilters(table, count, onUpdate) {
  const body = table.tBodies[0];
  const scrollRegion = table.closest('.match-table-scroll');
  const rowData = new WeakMap();
  const filters = new Map();
  const headers = new Map();
  const collator = new Intl.Collator(['he', 'en'], {numeric: true, sensitivity: 'base'});
  let sort = null;
  let opened = null;
  let positionFrame = 0;
  const popover = element('div', 'column-popover');
  popover.id = 'column-popover';
  popover.setAttribute('role', 'dialog');
  popover.hidden = true;
  document.body.append(popover);

  for (const cell of table.tHead.querySelectorAll('[data-column]')) {
    const key = cell.dataset.column;
    const label = cell.textContent.trim();
    const button = element('button', 'column-button');
    button.type = 'button';
    button.setAttribute('aria-haspopup', 'dialog');
    button.setAttribute('aria-controls', popover.id);
    button.setAttribute('aria-expanded', 'false');
    const title = element('span', 'column-title', label);
    const dot = element('span', 'column-dot');
    dot.setAttribute('aria-hidden', 'true');
    const icon = element('span', 'column-icon');
    icon.setAttribute('aria-hidden', 'true');
    title.append(dot);
    button.append(title, icon);
    cell.replaceChildren(button);
    headers.set(key, {cell, button, label});
    button.addEventListener('click', () => opened === key ? close() : open(key));
  }

  function isIncluded(data) {
    for (const [key, filter] of filters) {
      const column = columns[key];
      const value = data[key];
      if (column.type === 'text' && !normalize(value || '').includes(filter)) return false;
      if (column.type === 'multi' && !filter.has(value)) return false;
      if (column.type === 'single' && !column.choices.find(choice => choice.id === filter).matches(value)) return false;
      if (column.type === 'range' && (value == null || value < (filter.min ?? -Infinity) || value > (filter.max ?? Infinity))) return false;
    }
    return true;
  }

  function compareRows(a, b) {
    const first = rowData.get(a);
    const second = rowData.get(b);
    const rank = columns.match.sortOrder.indexOf(first.match) - columns.match.sortOrder.indexOf(second.match);
    const original = rank || first.order - second.order;
    if (!sort) return original;
    const {key, direction} = sort;
    const order = columns[key].sortOrder;
    const left = first[key];
    const right = second[key];
    if (left == null) return right == null ? original : 1;
    if (right == null) return -1;
    const comparison = order ? order.indexOf(left) - order.indexOf(right)
      : typeof left === 'number' ? left - right : collator.compare(left, right);
    return (direction === 'ascending' ? comparison : -comparison) || original;
  }

  function update() {
    const rows = Array.from(body.rows).sort(compareRows);
    let visible = 0;
    rows.forEach((row, index) => {
      row.hidden = !isIncluded(rowData.get(row));
      if (!row.hidden) visible++;
      if (body.rows[index] !== row) body.insertBefore(row, body.rows[index]);
    });
    count.textContent = !rows.length ? 'No cheaper Hahishook alternatives with a verified comparison price.'
      : visible ? visible + ' of ' + rows.length + ' cheaper options' : 'No rows match the column filters.';
    for (const [key, {cell, button, label}] of headers) {
      const sorted = sort?.key === key ? sort.direction : '';
      button.dataset.sort = sorted;
      button.classList.toggle('has-filter', filters.has(key));
      button.setAttribute('aria-label', label + (filters.has(key) ? ', filter active' : ''));
      if (sorted) cell.setAttribute('aria-sort', sorted);
      else cell.removeAttribute('aria-sort');
    }
    onUpdate();
  }

  function close(restoreFocus = false) {
    if (!opened) return;
    const {button} = headers.get(opened);
    opened = null;
    popover.hidden = true;
    document.body.classList.remove('column-popover-open');
    button.setAttribute('aria-expanded', 'false');
    if (restoreFocus) button.focus({preventScroll: true});
  }

  function place() {
    positionFrame = 0;
    if (!opened) return;
    const anchor = headers.get(opened).button.getBoundingClientRect();
    const clip = scrollRegion.getBoundingClientRect();
    const viewport = window.visualViewport;
    const margin = 8;
    const leftEdge = viewport?.offsetLeft ?? 0;
    const topEdge = viewport?.offsetTop ?? 0;
    const width = viewport?.width ?? document.documentElement.clientWidth;
    const height = viewport?.height ?? window.innerHeight;
    const rightEdge = leftEdge + width;
    const bottomEdge = topEdge + height;
    if (Math.min(anchor.right, clip.right, rightEdge) <= Math.max(anchor.left, clip.left, leftEdge)
        || anchor.bottom <= topEdge || anchor.top >= bottomEdge) {
      close();
      return;
    }
    const panelWidth = Math.min(276, width - 2 * margin);
    popover.style.width = panelWidth + 'px';
    popover.style.left = Math.min(Math.max(anchor.left, clip.left, leftEdge + margin), rightEdge - panelWidth - margin) + 'px';
    const gap = 6;
    const below = Math.max(0, bottomEdge - anchor.bottom - gap - margin);
    const above = Math.max(0, anchor.top - topEdge - gap - margin);
    const flip = below < Math.min(popover.scrollHeight, above);
    popover.style.maxHeight = (flip ? above : below) + 'px';
    popover.style.top = (flip ? anchor.top - gap - popover.getBoundingClientRect().height : anchor.bottom + gap) + 'px';
  }

  function requestPosition() {
    if (opened && !positionFrame) positionFrame = requestAnimationFrame(place);
  }

  function menuButton(label, active, action, total) {
    const button = element('button', 'popover-option');
    button.type = 'button';
    const check = element('span', 'popover-check');
    check.setAttribute('aria-hidden', 'true');
    button.append(check, element('span', '', label));
    if (total !== undefined) button.append(element('span', 'popover-count', String(total)));
    if (active !== undefined) button.setAttribute('aria-pressed', String(active));
    button.addEventListener('click', action);
    return button;
  }

  function searchInput(label) {
    const input = element('input', 'popover-search');
    input.type = 'search';
    input.dir = 'auto';
    input.autocomplete = 'off';
    input.placeholder = label;
    input.setAttribute('aria-label', label);
    return input;
  }

  function setFilter(key, value) {
    if (value == null) filters.delete(key);
    else filters.set(key, value);
    update();
  }

  function renderFilter(key, label, column) {
    const filter = filters.get(key);
    const rows = Array.from(body.rows, row => rowData.get(row)[key]);
    if (column.type === 'text') {
      const search = searchInput('Search ' + label.toLowerCase());
      search.value = filter || '';
      search.addEventListener('input', () => setFilter(key, normalize(search.value) || null));
      popover.append(search);
    } else if (column.type === 'single') {
      const list = element('div', 'popover-options');
      for (const {id, label, matches} of column.choices) {
        list.append(menuButton(label, (filter || 'all') === id, () => {
          setFilter(key, id === 'all' ? null : id);
          close(true);
        }, rows.filter(matches).length));
      }
      popover.append(list);
    } else if (column.type === 'multi') {
      const counts = new Map();
      for (const value of rows) counts.set(value, (counts.get(value) || 0) + 1);
      const choices = Array.from(counts.keys()).sort(collator.compare);
      const selected = new Set(filter || choices);
      const search = searchInput('Search ' + label.toLowerCase());
      const list = element('div', 'popover-options');
      const checks = [];
      for (const value of choices) {
        const option = element('label', 'popover-checkbox');
        const input = element('input');
        input.type = 'checkbox';
        input.checked = selected.has(value);
        option.append(input, element('span', '', value), element('span', 'popover-count', String(counts.get(value))));
        input.addEventListener('change', () => {
          if (input.checked) selected.add(value);
          else selected.delete(value);
          setFilter(key, selected.size === choices.length ? null : new Set(selected));
        });
        checks.push({value, option});
        list.append(option);
      }
      const empty = element('p', 'popover-empty', 'No options match.');
      empty.hidden = Boolean(choices.length);
      list.append(empty);
      search.addEventListener('input', () => {
        const query = normalize(search.value);
        for (const {value, option} of checks) option.hidden = !normalize(value).includes(query);
        empty.hidden = checks.some(({option}) => !option.hidden);
        list.scrollTop = 0;
        requestPosition();
      });
      popover.append(search, list);
    } else {
      const range = element('div', 'popover-range');
      for (const [bound, title] of [['min', 'Minimum'], ['max', 'Maximum']]) {
        const field = element('label', '', title + (column.scale === 100 ? ' (₪)' : ''));
        const input = element('input');
        input.type = 'number';
        input.min = '0';
        input.step = column.scale === 100 ? '0.01' : '1';
        input.placeholder = 'Any';
        input.value = filter?.[bound] == null ? '' : String(filter[bound] / column.scale);
        input.addEventListener('input', () => {
          const next = {...filters.get(key)};
          if (input.value === '' || !Number.isFinite(input.valueAsNumber)) delete next[bound];
          else next[bound] = Math.round(input.valueAsNumber * column.scale);
          setFilter(key, Object.keys(next).length ? next : null);
        });
        field.append(input);
        range.append(field);
      }
      popover.append(range);
    }
  }

  function open(key) {
    close();
    opened = key;
    const {button, label} = headers.get(key);
    button.setAttribute('aria-expanded', 'true');
    popover.setAttribute('aria-label', 'Sort and filter ' + label);
    const sortButtons = ['ascending', 'descending'].map(direction => menuButton(
      'Sort ' + direction, sort?.key === key && sort.direction === direction, () => {
        sort = {key, direction};
        update();
        close(true);
      },
    ));
    popover.replaceChildren(...sortButtons, element('hr', 'popover-divider'));
    renderFilter(key, label, columns[key]);
    if (sort?.key === key) popover.append(element('hr', 'popover-divider'), menuButton('Clear sort', undefined, () => {
      sort = null;
      update();
      close(true);
    }));
    popover.hidden = false;
    document.body.classList.add('column-popover-open');
    place();
    if (opened) sortButtons[0].focus({preventScroll: true});
  }

  document.addEventListener('pointerdown', event => {
    if (opened && !popover.contains(event.target) && !headers.get(opened).button.contains(event.target)) close();
  });
  document.addEventListener('keydown', event => {
    if (opened && event.key === 'Escape') {
      event.preventDefault();
      close(true);
    } else if (opened && event.key === 'Tab' && popover.contains(document.activeElement)) {
      const controls = Array.from(popover.querySelectorAll('button, input')).filter(node => !node.closest('[hidden]'));
      if (document.activeElement === (event.shiftKey ? controls[0] : controls.at(-1))) {
        event.preventDefault();
        close(true);
      }
    }
  });
  document.addEventListener('scroll', requestPosition, true);
  window.addEventListener('resize', requestPosition);
  window.visualViewport?.addEventListener('resize', requestPosition);
  window.visualViewport?.addEventListener('scroll', requestPosition);

  return {
    setRowData: (row, data) => rowData.set(row, data),
    update,
    reset() {
      close();
      filters.clear();
      sort = null;
      update();
    },
    close,
  };
}
