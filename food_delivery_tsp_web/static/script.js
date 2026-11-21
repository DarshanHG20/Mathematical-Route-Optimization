(() => {
  const matrixSearch = document.querySelector('#matrix-search');
  const matrixTable = document.querySelector('#matrix-table');
  if (matrixSearch && matrixTable) {
    matrixSearch.addEventListener('input', () => {
      const query = matrixSearch.value.trim().toLocaleLowerCase();
      const headings = [...matrixTable.querySelectorAll('thead th')];
      const keepColumn = headings.map((cell, index) => index === 0 || !query || cell.textContent.toLocaleLowerCase().includes(query));
      headings.forEach((cell, index) => { cell.hidden = !keepColumn[index]; });
      matrixTable.querySelectorAll('tbody tr').forEach((row) => {
        const cells = [...row.children];
        cells.forEach((cell, index) => { cell.hidden = !keepColumn[index]; });
        const rowMatch = !query || row.dataset.node.toLocaleLowerCase().includes(query);
        const valueMatch = !query || cells.some((cell, index) => index > 0 && cell.textContent.toLocaleLowerCase().includes(query));
        row.hidden = !(rowMatch || valueMatch);
      });
    });
  }

  const heatmap = document.querySelector('#heatmap');
  if (heatmap) {
    try {
      const values = JSON.parse(heatmap.dataset.values || '[]');
      const size = Math.max(...values.map((row) => row.length), 1);
      heatmap.style.gridTemplateColumns = `repeat(${size}, minmax(8px, 1fr))`;
      values.flat().forEach((value) => {
        const cell = document.createElement('i');
        if (value === null) {
          cell.style.background = '#d8e1e8';
          cell.title = 'Missing value';
        } else {
          const fraction = Math.max(0, Math.min(1, Number(value)));
          cell.style.background = `hsl(${205 - fraction * 180} 70% ${94 - fraction * 42}%)`;
          cell.title = `Relative cost: ${fraction.toFixed(2)}`;
        }
        heatmap.append(cell);
      });
    } catch (_) {
      heatmap.textContent = 'Heatmap preview unavailable.';
    }
  }

  const planner = document.querySelector('#route-form');
  if (planner) {
    const depot = document.querySelector('#depot-select');
    const depotName = document.querySelector('#depot-place-name');
    const search = document.querySelector('#node-search');
    const list = document.querySelector('#node-list');
    const toggle = document.querySelector('#toggle-visible');
    const counter = document.querySelector('#selected-count');
    const preview = document.querySelector('#selection-preview');
    const validation = document.querySelector('#planner-validation');
    const maxStops = Number(planner.dataset.maxStops || 60);

    const boxes = () => [...planner.querySelectorAll('input[name="stops"]')];
    const refreshPlaceInputs = () => {
      boxes().forEach((box) => {
        const input = box.closest('.node-option').querySelector('.place-name-input');
        const active = box.checked && !box.disabled;
        input.hidden = !active;
        input.disabled = !active;
      });
    };
    const refreshDepot = () => {
      boxes().forEach((box) => {
        const isDepot = depot && box.value === depot.value;
        box.disabled = Boolean(isDepot);
        if (isDepot) box.checked = false;
        box.closest('.node-option').dataset.depotNode = isDepot ? 'true' : 'false';
      });
      refreshPlaceInputs();
    };
    const refreshSearch = () => {
      const query = (search?.value || '').trim().toLocaleLowerCase();
      boxes().forEach((box) => {
        const label = box.closest('.node-option');
        const placeName = label.querySelector('.place-name-input').value.toLocaleLowerCase();
        label.hidden = Boolean(query) && !label.dataset.nodeLabel.includes(query) && !placeName.includes(query);
      });
    };
    const refreshSummary = () => {
      const selected = boxes().filter((box) => box.checked);
      refreshPlaceInputs();
      if (counter) counter.textContent = String(selected.length);
      if (preview) {
        const depotLabel = depotName?.value.trim() || 'Name the depot';
        const stopLabels = selected.map((box) => {
          const row = box.closest('.node-option');
          const placeName = row.querySelector('.place-name-input').value.trim();
          return placeName || 'Name this location';
        });
        const stopsLabel = stopLabels.length ? stopLabels.join(' → ') : 'select at least one place';
        preview.textContent = `Depot: ${depotLabel} → ${stopsLabel} → ${depotLabel}`;
      }
    };
    const enforceLimit = (changed) => {
      const selected = boxes().filter((box) => box.checked && !box.disabled);
      if (selected.length > maxStops && changed) changed.checked = false;
      refreshSummary();
    };

    depot?.addEventListener('change', () => { refreshDepot(); refreshSummary(); });
    depotName?.addEventListener('input', refreshSummary);
    search?.addEventListener('input', refreshSearch);
    boxes().forEach((box) => {
      box.addEventListener('change', () => enforceLimit(box));
      box.closest('.node-option').querySelector('.place-name-input').addEventListener('input', () => {
        refreshSearch();
        refreshSummary();
      });
    });
    toggle?.addEventListener('click', () => {
      const visible = boxes().filter((box) => !box.disabled && !box.closest('.node-option').hidden);
      const allChecked = visible.length > 0 && visible.every((box) => box.checked);
      if (allChecked) visible.forEach((box) => { box.checked = false; });
      else {
        const selectedCount = boxes().filter((box) => box.checked && !box.disabled).length;
        let capacity = Math.max(0, maxStops - selectedCount);
        visible.forEach((box) => {
          if (!box.checked && capacity > 0) { box.checked = true; capacity -= 1; }
        });
      }
      refreshSummary();
    });
    planner.addEventListener('submit', (event) => {
      const selected = boxes().filter((box) => box.checked && !box.disabled);
      const placeNames = [depotName?.value.trim() || '', ...selected.map((box) => box.closest('.node-option').querySelector('.place-name-input').value.trim())];
      let message = '';
      if (!selected.length) message = 'Select at least one delivery location.';
      else if (selected.length > maxStops) message = `Select no more than ${maxStops} delivery locations.`;
      else if (selected.some((box) => box.value === depot?.value)) message = 'The depot cannot also be a delivery stop.';
      else if (placeNames.some((name) => !name)) message = 'Enter a Karnataka place name for the depot and every selected stop.';
      else if (new Set(placeNames.map((name) => name.toLocaleLowerCase())).size !== placeNames.length) message = 'Use a distinct place name for the depot and each selected stop.';
      if (message) {
        event.preventDefault();
        if (validation) validation.textContent = message;
      } else if (validation) validation.textContent = '';
    });
    refreshDepot();
    refreshSearch();
    refreshSummary();
  }

  document.querySelectorAll('.bar-chart').forEach((host) => {
    try {
      const data = JSON.parse(host.dataset.series || '[]');
      const numbers = data.map((item) => Number(item.value)).filter(Number.isFinite);
      const maximum = Math.max(...numbers, 0);
      if (!data.length || maximum <= 0) {
        host.textContent = 'No validated values available for this chart.';
        host.classList.add('muted');
        return;
      }
      data.forEach((item) => {
        const row = document.createElement('div');
        row.className = 'bar-row';
        const label = document.createElement('span');
        label.className = 'bar-label';
        label.textContent = item.label;
        const track = document.createElement('span');
        track.className = 'bar-track';
        const fill = document.createElement('span');
        fill.className = 'bar-fill';
        if (item.value === null || !Number.isFinite(Number(item.value))) {
          fill.style.width = '0%';
          fill.title = 'Unavailable';
        } else {
          fill.style.width = `${Math.max(1, Number(item.value) / maximum * 100)}%`;
          fill.title = Number(item.value).toFixed(2);
        }
        track.append(fill);
        const value = document.createElement('span');
        value.className = 'bar-value';
        value.textContent = item.value === null || !Number.isFinite(Number(item.value)) ? '—' : Number(item.value).toFixed(2);
        row.append(label, track, value);
        host.append(row);
      });
    } catch (_) {
      host.textContent = 'Chart data unavailable.';
    }
  });
})();
