export default function({parentElement, data, setStateValue, setTriggerValue}) {
  const root = parentElement.querySelector('.ranking-root');
  const ids = data.options.map(o => o.id);
  const labels = new Map(data.options.map(o => [o.id, o.label]));
  const valid = a => Array.isArray(a) && a.length === ids.length && new Set(a).size === ids.length && a.every(id => labels.has(id));
  const incoming = data.value || {};
  // Keep the live DOM through the game's two-second refresh, including an active drag.
  if (root.ranking && root.ranking.ids === JSON.stringify(ids)) {
    root.ranking.publish = setStateValue;
    root.ranking.submit = setTriggerValue;
    if (data.game && JSON.stringify(data.saved) === JSON.stringify(root.ranking.order)) {
      root.querySelector('.status').textContent = 'Ranking saved.';
    }
    return;
  }
  const state = root.ranking = {
    ids: JSON.stringify(ids), order: valid(incoming.order) ? [...incoming.order] : [...ids],
    confirmed: !!incoming.confirmed, publish: setStateValue, submit: setTriggerValue,
  };
  root.replaceChildren();
  const hint = document.createElement('p');
  hint.textContent = 'Drag the handles to rank from first to last, or use the up and down buttons.';
  const list = document.createElement('ol');
  list.setAttribute('aria-label', 'Ranked answers');
  const status = document.createElement('p');
  status.className = 'status'; status.setAttribute('aria-live', 'polite');
  const confirm = document.createElement('button');
  confirm.type = 'button'; confirm.className = 'confirm';
  confirm.textContent = data.game ? 'Save ranking' : 'Confirm ranking';
  root.append(hint, list, confirm, status);
  function publish() {
    state.confirmed = false;
    state.publish('selection', {order: [...state.order], confirmed: false});
    status.textContent = data.game ? 'Order changed. Save your ranking to submit it.' : 'Order changed. Confirm your ranking when ready.';
  }
  function move(id, offset, focusClass = null) {
    const i = state.order.indexOf(id), target = i + offset;
    if (target < 0 || target >= state.order.length) return;
    state.order.splice(i, 1); state.order.splice(target, 0, id);
    render(); publish();
    const row = [...list.children].find(el => el.dataset.id === id);
    const targetControl = row.querySelector(focusClass || (offset < 0 ? '.up' : '.down'));
    (targetControl.disabled ? row.querySelector('.handle') : targetControl).focus();
  }
  function render() {
    list.replaceChildren();
    state.order.forEach((id, i) => {
      const row = document.createElement('li'); row.dataset.id = id;
      const handle = document.createElement('button'); handle.type = 'button'; handle.className = 'handle';
      handle.textContent = '⠿'; handle.setAttribute('aria-label', `Drag ${labels.get(id)}. Use arrow keys to move.`);
      handle.onkeydown = e => {
        if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {e.preventDefault(); move(id, e.key === 'ArrowUp' ? -1 : 1, '.handle');}
      };
      const position = document.createElement('span'); position.className = 'position'; position.textContent = `${i + 1}.`;
      const label = document.createElement('span'); label.className = 'label'; label.textContent = labels.get(id);
      const up = document.createElement('button'), down = document.createElement('button');
      for (const [button, direction, symbol, offset] of [[up,'up','↑',-1],[down,'down','↓',1]]) {
        button.type = 'button'; button.className = direction; button.textContent = symbol;
        button.setAttribute('aria-label', `Move ${labels.get(id)} ${direction}`);
        button.disabled = i + offset < 0 || i + offset >= state.order.length;
        button.onclick = () => move(id, offset);
      }
      // Pointer events support mouse, pen and touch without an external drag library.
      handle.onpointerdown = e => {
        if (e.button !== 0) return;
        e.preventDefault(); handle.setPointerCapture(e.pointerId); row.classList.add('dragging');
        let targetIndex = state.order.indexOf(id);
        const onMove = event => {
          const rows = [...list.children];
          const target = rows.find(el => {
            const box = el.getBoundingClientRect();
            return event.clientY >= box.top && event.clientY <= box.bottom;
          });
          if (!target) return;
          targetIndex = state.order.indexOf(target.dataset.id);
          rows.forEach(el => el.classList.toggle('drop-target', el === target && el !== row));
        };
        const end = () => {
          handle.removeEventListener('pointermove', onMove);
          handle.removeEventListener('pointerup', end); handle.removeEventListener('pointercancel', end);
          const from = state.order.indexOf(id);
          state.order.splice(from, 1); state.order.splice(targetIndex, 0, id);
          render(); if (from !== targetIndex) publish();
        };
        handle.addEventListener('pointermove', onMove); handle.addEventListener('pointerup', end); handle.addEventListener('pointercancel', end);
      };
      row.append(handle, position, label, up, down); list.append(row);
    });
  }
  confirm.onclick = () => {
    state.confirmed = true;
    if (data.game) state.submit('submitted', [...state.order]);
    else state.publish('selection', {order: [...state.order], confirmed: true});
    status.textContent = data.game ? 'Saving ranking…' : 'Ranking confirmed. Send your survey when all answers are ready.';
  };
  render();
  status.textContent = state.confirmed ? (data.game ? 'Ranking saved.' : 'Ranking confirmed.') : (data.game ? 'Arrange the answers, then save your ranking.' : 'Arrange the answers, then confirm your ranking.');
}
