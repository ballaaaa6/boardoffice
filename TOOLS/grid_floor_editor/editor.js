(() => {
  'use strict';

  const DEFAULT = window.GDS_DEFAULT_F2 || null;
  const PROJECT_URLS = {
    room: '../../WORLD/COMPILED_NAV/floor02_room_cells.json',
    portal: '../../WORLD/REGISTRY/portals.json',
  };
  const MAX_HISTORY = 100;
  const LAYER_LABELS = {
    room: 'Room Grid',
    portalInside: 'Portal Inside',
    portalOutside: 'Portal Outside',
  };
  const TOOL_LABELS = {
    cell: 'คลิกทีละช่อง',
    rectangle: 'คลุมเป็นกรอบ',
    pan: 'เลื่อนแผนที่',
  };

  const state = {
    canvas: null,
    context: null,
    data: null,
    base: null,
    current: null,
    occupancy: new Set(),
    sources: { room: null, portal: null, occupancy: null },
    selection: new Set(),
    previewSelection: new Set(),
    history: [],
    future: [],
    layer: 'room',
    tool: 'cell',
    viewport: null,
    view: {
      width: 0,
      height: 0,
      baseScale: 1,
      scale: 1,
      zoom: 1,
      centerX: 0,
      centerY: 0,
      panX: 0,
      panY: 0,
      ready: false,
    },
    drag: null,
    validation: null,
    toastTimer: null,
  };

  const $ = (id) => document.getElementById(id);

  function cellKey(u, v) {
    return `${u},${v}`;
  }

  function parseCell(value) {
    if (Array.isArray(value) && value.length >= 2) {
      return [Number(value[0]), Number(value[1])];
    }
    const [u, v] = String(value).split(',').map(Number);
    return [u, v];
  }

  function normalizeCells(values) {
    const result = new Set();
    for (const value of values || []) {
      const [u, v] = parseCell(value);
      if (Number.isInteger(u) && Number.isInteger(v)) result.add(cellKey(u, v));
    }
    return result;
  }

  function sortedCells(cells) {
    return [...cells]
      .map(parseCell)
      .sort((a, b) => (a[1] - b[1]) || (a[0] - b[0]))
      .map(([u, v]) => [u, v]);
  }

  function cloneSet(cells) {
    return new Set(cells || []);
  }

  function snapshot() {
    return {
      room: cloneSet(state.current?.room),
      portalInside: cloneSet(state.current?.portalInside),
      portalOutside: cloneSet(state.current?.portalOutside),
    };
  }

  function restoreSnapshot(value) {
    state.current = {
      room: cloneSet(value.room),
      portalInside: cloneSet(value.portalInside),
      portalOutside: cloneSet(value.portalOutside),
      occupancy: cloneSet(state.occupancy),
    };
  }

  function snapshotsEqual(a, b) {
    return ['room', 'portalInside', 'portalOutside'].every((name) => {
      if (a[name].size !== b[name].size) return false;
      for (const value of a[name]) if (!b[name].has(value)) return false;
      return true;
    });
  }

  function pushHistory(before) {
    state.history.push(before);
    if (state.history.length > MAX_HISTORY) state.history.shift();
    state.future = [];
  }

  function showStatus(message, kind = '') {
    const footer = $('footerStatus');
    footer.textContent = message;
    footer.className = `footer-status ${kind}`.trim();
    if (state.toastTimer) window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(() => {
      footer.textContent = 'พร้อมใช้งาน';
      footer.className = 'footer-status';
    }, 5000);
  }

  function number(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function findFloorEntry(payload, floorId) {
    if (!payload || typeof payload !== 'object') return null;
    if (payload[floorId]) return payload[floorId];
    if (payload.domains?.[floorId]) return payload.domains[floorId];
    if (payload.portals?.[`${floorId}.main_exit`]) return payload.portals[`${floorId}.main_exit`];
    if (payload.portals?.[floorId]) return payload.portals[floorId];
    return null;
  }

  function pointInPolygon(point, polygon) {
    const [x, y] = point;
    let inside = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i += 1) {
      const [xi, yi] = polygon[i];
      const [xj, yj] = polygon[j];
      const intersects = ((yi > y) !== (yj > y))
        && (x < ((xj - xi) * (y - yi)) / ((yj - yi) || Number.EPSILON) + xi);
      if (intersects) inside = !inside;
    }
    return inside;
  }

  function cellsFromPolygon(polygon) {
    if (!Array.isArray(polygon) || polygon.length < 3) return new Set();
    const us = polygon.map((point) => Number(point[0]));
    const vs = polygon.map((point) => Number(point[1]));
    const minU = Math.floor(Math.min(...us)) - 1;
    const maxU = Math.ceil(Math.max(...us)) + 1;
    const minV = Math.floor(Math.min(...vs)) - 1;
    const maxV = Math.ceil(Math.max(...vs)) + 1;
    const result = new Set();
    for (let v = minV; v <= maxV; v += 1) {
      for (let u = minU; u <= maxU; u += 1) {
        if (pointInPolygon([u + 0.5, v + 0.5], polygon)) result.add(cellKey(u, v));
      }
    }
    return result;
  }

  function extractRoomCells(payload, floorId) {
    const source = payload?.room_mask || payload || {};
    if (Array.isArray(source.room_cells_uv)) return normalizeCells(source.room_cells_uv);
    if (Array.isArray(source.cells_uv)) return normalizeCells(source.cells_uv);
    if (Array.isArray(source.row_runs)) {
      const result = new Set();
      for (const row of source.row_runs) {
        const v = Number(row.v);
        for (const run of row.u_runs_inclusive || []) {
          for (let u = Number(run[0]); u <= Number(run[1]); u += 1) {
            result.add(cellKey(u, v));
          }
        }
      }
      return result;
    }
    const domain = source.domains?.[floorId]
      || findFloorEntry(source, floorId)
      || source.domain
      || null;
    if (domain?.room_cells_uv) return normalizeCells(domain.room_cells_uv);
    if (domain?.polygon_uv) return cellsFromPolygon(domain.polygon_uv);
    if (source.polygon_uv) return cellsFromPolygon(source.polygon_uv);
    throw new Error('ไม่พบ room_cells_uv, row_runs หรือ polygon_uv ในไฟล์ Room mask');
  }

  function extractPortal(payload, floorId) {
    const source = payload?.portal || payload || {};
    let portal = null;
    if (Array.isArray(source.inside_cells_uv)) {
      portal = source;
    } else if (source.portals) {
      portal = findFloorEntry(source, floorId);
      if (!portal) {
        portal = Object.values(source.portals).find((value) => Array.isArray(value.inside_cells_uv));
      }
    } else if (source.portal) {
      portal = source.portal;
    }
    if (!portal || !Array.isArray(portal.inside_cells_uv) || !Array.isArray(portal.outside_cells_uv)) {
      throw new Error('ไม่พบ inside_cells_uv และ outside_cells_uv ในไฟล์ Portal');
    }
    return {
      portalId: portal.portal_id || `${floorId}.main_exit`,
      edgeUv: (portal.edge_uv || []).map((value) => parseCell(value)),
      inside: normalizeCells(portal.inside_cells_uv),
      outside: normalizeCells(portal.outside_cells_uv),
    };
  }

  function extractOccupancy(payload) {
    const source = payload?.occupancy || payload || {};
    if (Array.isArray(source.occupied_cells_uv)) return normalizeCells(source.occupied_cells_uv);
    if (Array.isArray(source.walkable_cells_uv)) {
      return new Set();
    }
    if (Array.isArray(source.cells_uv)) return normalizeCells(source.cells_uv);
    return new Set();
  }

  function deriveEdge(outside) {
    const cells = sortedCells(outside);
    if (!cells.length) return [];
    const us = cells.map((cell) => cell[0]);
    const vs = cells.map((cell) => cell[1]);
    const sameV = vs.every((value) => value === vs[0]);
    const sameU = us.every((value) => value === us[0]);
    if (sameV) {
      const minU = Math.min(...us);
      const maxU = Math.max(...us);
      if (maxU - minU + 1 === cells.length) return [[minU, vs[0]], [maxU + 1, vs[0]]];
    }
    if (sameU) {
      const minV = Math.min(...vs);
      const maxV = Math.max(...vs);
      if (maxV - minV + 1 === cells.length) return [[us[0], minV], [us[0], maxV + 1]];
    }
    return [];
  }

  function currentEdge() {
    const derived = deriveEdge(state.current?.portalOutside || new Set());
    return derived.length ? derived : (state.data?.edgeUv || []);
  }

  function deriveViewport(margin = 8) {
    const cells = [
      ...(state.current?.room || []),
      ...(state.current?.portalInside || []),
      ...(state.current?.portalOutside || []),
    ].map(parseCell);
    if (!cells.length) return { minU: 0, maxU: 20, minV: 0, maxV: 20 };
    const us = cells.map((cell) => cell[0]);
    const vs = cells.map((cell) => cell[1]);
    return {
      minU: Math.floor(Math.min(...us)) - margin,
      maxU: Math.ceil(Math.max(...us)) + margin,
      minV: Math.floor(Math.min(...vs)) - margin,
      maxV: Math.ceil(Math.max(...vs)) + margin,
    };
  }

  function normalizeViewport(value) {
    const viewport = {
      minU: Math.trunc(number(value.minU)),
      maxU: Math.trunc(number(value.maxU)),
      minV: Math.trunc(number(value.minV)),
      maxV: Math.trunc(number(value.maxV)),
    };
    if (viewport.minU > viewport.maxU || viewport.minV > viewport.maxV) {
      throw new Error('Viewport ต้องมี min น้อยกว่าหรือเท่ากับ max');
    }
    return viewport;
  }

  function setViewport(value, fit = true) {
    state.viewport = normalizeViewport(value);
    $('minU').value = state.viewport.minU;
    $('maxU').value = state.viewport.maxU;
    $('minV').value = state.viewport.minV;
    $('maxV').value = state.viewport.maxV;
    if (fit) fitView();
  }

  function loadData(payload, sourceLabel) {
    const floorId = payload.floor_id
      || payload.room_mask?.floor_id
      || payload.portal?.floor_id
      || 'floor02';
    const room = extractRoomCells(payload.room || payload.room_mask || payload, floorId);
    const portal = extractPortal(payload.portal || payload, floorId);
    const occupancy = extractOccupancy(payload.occupancy || {});
    if (!room.size) throw new Error('Room mask ว่างเปล่า');
    state.data = {
      floorId,
      canonicalFloorId: floorId === 'floor02' ? 'floor02' : floorId,
      gridProfileId: payload.grid_profile_id
        || payload.room_mask?.grid_profile_id
        || 'grid.iso.occupancy_fine.v1',
      portalId: portal.portalId,
      edgeUv: portal.edgeUv,
      sourceLabel,
    };
    state.occupancy = occupancy;
    state.base = { room: cloneSet(room), portalInside: cloneSet(portal.inside), portalOutside: cloneSet(portal.outside) };
    state.current = { room, portalInside: portal.inside, portalOutside: portal.outside };
    state.current.occupancy = occupancy;
    state.base.occupancy = cloneSet(occupancy);
    state.selection.clear();
    state.previewSelection.clear();
    state.history = [];
    state.future = [];
    state.viewport = deriveViewport(Number($('viewportMargin').value) || 8);
    state.view.ready = false;
    setViewport(state.viewport, false);
    fitView();
    $('floorSelect').value = floorId === 'floor02' ? 'floor02' : 'floor02';
    $('dataTitle').textContent = `${floorId === 'floor02' ? 'F2' : floorId} / ${floorId}`;
    showStatus(`โหลด ${floorId} แล้วจาก ${sourceLabel}`, 'success');
    updateUI();
  }

  function loadFromSources(sourceLabel) {
    if (!state.sources.room || !state.sources.portal) return;
    loadData({
      room: state.sources.room,
      portal: state.sources.portal,
      occupancy: state.sources.occupancy,
      floor_id: state.sources.room.floor_id || 'floor02',
    }, sourceLabel);
  }

  async function loadProjectFiles() {
    try {
      const [roomResponse, portalResponse] = await Promise.all([
        fetch(PROJECT_URLS.room, { cache: 'no-store' }),
        fetch(PROJECT_URLS.portal, { cache: 'no-store' }),
      ]);
      if (!roomResponse.ok || !portalResponse.ok) throw new Error('โหลดไฟล์จาก project path ไม่สำเร็จ');
      state.sources.room = await roomResponse.json();
      state.sources.portal = await portalResponse.json();
      loadFromSources('project files');
    } catch (error) {
      showStatus('โหลดจากโปรเจกต์ไม่ได้ — ถ้าเปิดผ่าน file:// ให้ใช้ปุ่มนำเข้าไฟล์แทน', 'error');
    }
  }

  async function readJsonFile(file) {
    if (!file) return null;
    return JSON.parse(await file.text());
  }

  async function handleFile(kind, file) {
    try {
      const parsed = await readJsonFile(file);
      state.sources[kind] = parsed;
      if (kind === 'occupancy' && !state.sources.room) state.sources.room = DEFAULT?.room_mask;
      if (kind === 'occupancy' && !state.sources.portal) state.sources.portal = DEFAULT?.portal;
      if (!state.sources.room || !state.sources.portal) throw new Error('ต้องมี Room mask และ Portal อย่างน้อยสองไฟล์');
      loadFromSources(file.name);
    } catch (error) {
      showStatus(`นำเข้าไฟล์ไม่สำเร็จ: ${error.message}`, 'error');
    }
  }

  function layerSet() {
    if (state.layer === 'room') return state.current.room;
    if (state.layer === 'portalInside') return state.current.portalInside;
    return state.current.portalOutside;
  }

  function rectangleCells(start, end) {
    const minU = Math.min(start[0], end[0]);
    const maxU = Math.max(start[0], end[0]);
    const minV = Math.min(start[1], end[1]);
    const maxV = Math.max(start[1], end[1]);
    const result = new Set();
    for (let v = minV; v <= maxV; v += 1) {
      for (let u = minU; u <= maxU; u += 1) result.add(cellKey(u, v));
    }
    return result;
  }

  function insideViewport([u, v]) {
    return state.viewport
      && u >= state.viewport.minU && u <= state.viewport.maxU
      && v >= state.viewport.minV && v <= state.viewport.maxV;
  }

  function modifySelection(cell, additive, subtractive) {
    const key = cellKey(cell[0], cell[1]);
    if (subtractive) state.selection.delete(key);
    else if (additive) state.selection.add(key);
    else state.selection = new Set([key]);
  }

  function commitRectangleSelection(cells, additive, subtractive) {
    if (subtractive) {
      for (const key of cells) state.selection.delete(key);
    } else if (additive) {
      for (const key of cells) state.selection.add(key);
    } else {
      state.selection = new Set(cells);
    }
    state.previewSelection.clear();
  }

  function applyOperation(operation) {
    if (!state.selection.size) {
      showStatus('ยังไม่ได้เลือก cell', 'error');
      return;
    }
    const before = snapshot();
    const target = layerSet();
    if (operation === 'open') {
      for (const key of state.selection) target.add(key);
    } else {
      for (const key of state.selection) target.delete(key);
    }
    if (snapshotsEqual(before, snapshot())) {
      showStatus(`selection นี้ไม่มีการเปลี่ยนแปลงใน ${LAYER_LABELS[state.layer]}`, '');
      return;
    }
    pushHistory(before);
    showStatus(`${operation === 'open' ? 'เปิด' : 'ปิด'} ${state.selection.size} cells ใน ${LAYER_LABELS[state.layer]}`, 'success');
    focusSelection();
    updateUI();
  }

  function undo() {
    if (!state.history.length) return;
    state.future.push(snapshot());
    restoreSnapshot(state.history.pop());
    showStatus('ย้อนกลับการแก้ไขแล้ว', 'success');
    updateUI();
  }

  function redo() {
    if (!state.future.length) return;
    state.history.push(snapshot());
    restoreSnapshot(state.future.pop());
    showStatus('ทำซ้ำการแก้ไขแล้ว', 'success');
    updateUI();
  }

  function reset() {
    const before = snapshot();
    if (snapshotsEqual(before, state.base)) return;
    pushHistory(before);
    restoreSnapshot(state.base);
    state.selection.clear();
    state.previewSelection.clear();
    showStatus('คืนค่าข้อมูลเริ่มต้นแล้ว', 'success');
    updateUI();
  }

  function diffSet(base, current) {
    const added = new Set();
    const removed = new Set();
    for (const key of current) if (!base.has(key)) added.add(key);
    for (const key of base) if (!current.has(key)) removed.add(key);
    return { added, removed };
  }

  function editableDiffs() {
    if (!state.current || !state.base) {
      return {
        room: { added: new Set(), removed: new Set() },
        portalInside: { added: new Set(), removed: new Set() },
        portalOutside: { added: new Set(), removed: new Set() },
      };
    }
    return {
      room: diffSet(state.base.room, state.current.room),
      portalInside: diffSet(state.base.portalInside, state.current.portalInside),
      portalOutside: diffSet(state.base.portalOutside, state.current.portalOutside),
    };
  }

  function diffCount(diffs) {
    return Object.values(diffs).reduce((total, diff) => total + diff.added.size + diff.removed.size, 0);
  }

  function floodFill(traversable, starts) {
    const seen = new Set([...starts].filter((key) => traversable.has(key)));
    const queue = [...seen];
    for (let index = 0; index < queue.length; index += 1) {
      const [u, v] = parseCell(queue[index]);
      for (const neighbor of [cellKey(u + 1, v), cellKey(u - 1, v), cellKey(u, v + 1), cellKey(u, v - 1)]) {
        if (traversable.has(neighbor) && !seen.has(neighbor)) {
          seen.add(neighbor);
          queue.push(neighbor);
        }
      }
    }
    return seen;
  }

  function addCheck(checks, name, status, detail) {
    checks.push({ name, status, detail });
  }

  function validate() {
    if (!state.current) return { checks: [], errors: [], warnings: [], valid: false };
    const { room, portalInside: inside, portalOutside: outside } = state.current;
    const checks = [];
    const errors = [];
    const warnings = [];
    const fail = (name, detail) => { addCheck(checks, name, 'fail', detail); errors.push(detail); };
    const pass = (name, detail) => addCheck(checks, name, 'pass', detail);
    const warn = (name, detail) => { addCheck(checks, name, 'warn', detail); warnings.push(detail); };

    if (room.size) pass('Room ไม่ว่าง', `${room.size.toLocaleString()} cells`);
    else fail('Room ไม่ว่าง', 'Room ไม่มี cell');

    if (inside.size && outside.size) pass('Portal มีสองฝั่ง', `inside ${inside.size} / outside ${outside.size}`);
    else fail('Portal มีสองฝั่ง', 'ต้องมี Portal Inside และ Portal Outside อย่างน้อยหนึ่ง cell');

    const insideWithinRoom = [...inside].every((key) => room.has(key));
    if (insideWithinRoom) pass('Portal Inside อยู่ใน Room', 'ทุก inside cell อยู่ใน Room Grid');
    else fail('Portal Inside อยู่ใน Room', 'มี inside cell อยู่นอก Room Grid');

    const outsideOutsideRoom = [...outside].every((key) => !room.has(key));
    if (outsideOutsideRoom) pass('Portal Outside อยู่นอก Room', 'ทุก outside cell อยู่นอก Room Grid');
    else fail('Portal Outside อยู่นอก Room', 'มี outside cell ทับกับ Room Grid');

    const pairsMatch = inside.size === outside.size;
    const insideArray = sortedCells(inside);
    const outsideArray = sortedCells(outside);
    const pairedAdjacent = pairsMatch && insideArray.every((cell, index) => {
      const other = outsideArray[index];
      return Math.abs(cell[0] - other[0]) + Math.abs(cell[1] - other[1]) === 1;
    });
    if (pairedAdjacent) pass('Portal pairing / adjacency', `${inside.size} คู่ติดกันครบ`);
    else fail('Portal pairing / adjacency', 'จำนวน cell หรือคู่ inside/outside ไม่ตรงกัน');

    const occupancy = state.current.occupancy || new Set();
    let traversable = room;
    let starts = inside;
    if (occupancy.size) {
      const occupiedOutsideRoom = [...occupancy].some((key) => !room.has(key));
      const portalOverlap = [...occupancy].some((key) => inside.has(key));
      if (occupiedOutsideRoom) fail('Occupancy อยู่ใน Room', 'มี occupancy cell อยู่นอก Room Grid');
      else pass('Occupancy อยู่ใน Room', `${occupancy.size} cells ตรวจแล้ว`);
      if (portalOverlap) fail('Portal ไม่ทับ Occupancy', 'Portal Inside ทับกับ occupancy');
      else pass('Portal ไม่ทับ Occupancy', 'ไม่พบการทับซ้อน');
      traversable = new Set([...room].filter((key) => !occupancy.has(key)));
      starts = new Set([...inside].filter((key) => traversable.has(key)));
    } else {
      warn('Occupancy overlay', 'ยังไม่ได้โหลด occupancy จึงตรวจเฉพาะ Room connectivity');
    }

    const reachable = floodFill(traversable, starts);
    if (reachable.size === traversable.size && traversable.size) {
      pass('Connectivity จาก Portal', `${reachable.size.toLocaleString()} / ${traversable.size.toLocaleString()} cells reachable`);
    } else {
      fail('Connectivity จาก Portal', `${reachable.size.toLocaleString()} / ${traversable.size.toLocaleString()} cells reachable`);
    }

    const edge = deriveEdge(outside);
    if (edge.length === 2) pass('Portal edge เป็นเส้นต่อเนื่อง', `${edge[0].join(',')} → ${edge[1].join(',')}`);
    else warn('Portal edge เป็นเส้นต่อเนื่อง', 'Portal Outside ไม่เป็นแนวต่อเนื่องแบบเส้นเดียว');

    warn('F2 family impact', 'ถ้าแก้ floor02 canonical จะกระทบ F2+ ทั้ง 23 floors');
    return { checks, errors, warnings, valid: errors.length === 0 };
  }

  function updateMetrics() {
    const current = state.current;
    if (!current) return;
    $('roomCount').textContent = current.room.size.toLocaleString();
    $('portalInsideCount').textContent = current.portalInside.size.toLocaleString();
    $('portalOutsideCount').textContent = current.portalOutside.size.toLocaleString();
    $('occupancyCount').textContent = current.occupancy?.size ? current.occupancy.size.toLocaleString() : 'ไม่ได้โหลด';
    $('selectedCount').textContent = state.selection.size.toLocaleString();
    $('selectionReadout').textContent = `เลือกแล้ว ${state.selection.size.toLocaleString()} cells`;
    $('undoButton').disabled = !state.history.length;
    $('redoButton').disabled = !state.future.length;
    $('openButton').disabled = !state.selection.size;
    $('closeButton').disabled = !state.selection.size;
    $('exportPatchButton').disabled = !state.data;
    $('exportSnapshotButton').disabled = !state.data;
  }

  function updateDiff() {
    if (!state.current || !state.base) return;
    const diffs = editableDiffs();
    const room = diffs.room;
    const inside = diffs.portalInside;
    const outside = diffs.portalOutside;
    const changed = diffCount(diffs);
    const activeDiff = diffs[state.layer];
    $('changeReadout').textContent = changed
      ? `แก้แล้ว ${changed.toLocaleString()} cells · ${LAYER_LABELS[state.layer]} +${activeDiff.added.size}/-${activeDiff.removed.size}`
      : 'แก้แล้ว 0 cells';
    if (!changed) {
      $('diffSummary').textContent = 'ยังไม่มีการเปลี่ยนแปลง';
      return;
    }
    $('diffSummary').textContent = [
      `Room       +${room.added.size} / -${room.removed.size}`,
      `Portal In  +${inside.added.size} / -${inside.removed.size}`,
      `Portal Out +${outside.added.size} / -${outside.removed.size}`,
      `รวมเปลี่ยนแปลง ${changed} cells`,
    ].join('\n');
  }

  function updateValidation() {
    const result = validate();
    state.validation = result;
    const card = $('overallStatus');
    const label = $('overallStatusLabel');
    const detail = $('overallStatusDetail');
    card.className = `status-card ${result.valid ? 'pass' : 'fail'}`;
    label.textContent = result.valid ? 'PASS' : 'NEEDS REVIEW';
    detail.textContent = result.valid
      ? `${result.warnings.length ? `${result.warnings.length} warning(s) · ` : ''}พร้อม export patch ได้`
      : `${result.errors.length} error(s) · แก้ validation ก่อนนำไปใช้จริง`;

    const list = $('checkList');
    list.replaceChildren();
    for (const check of result.checks) {
      const row = document.createElement('div');
      row.className = `check-row ${check.status}`;
      const icon = document.createElement('span');
      icon.className = 'icon';
      icon.textContent = check.status === 'pass' ? '✓' : check.status === 'fail' ? '!' : '·';
      const text = document.createElement('div');
      const name = document.createElement('div');
      name.textContent = check.name;
      const sub = document.createElement('div');
      sub.className = 'detail';
      sub.textContent = check.detail;
      text.append(name, sub);
      row.append(icon, text);
      list.append(row);
    }
  }

  function updateLayerHint() {
    const hints = {
      room: 'เลือก cell ใน Room Grid แล้วกดเปิดหรือปิด เพื่อขยายหรือหด Room Domain',
      portalInside: 'เลือก cell ฝั่งในประตู แล้วกดเปิดหรือปิด — inside ต้องอยู่ใน Room',
      portalOutside: 'เลือก cell ฝั่งนอกประตู แล้วกดเปิดหรือปิด — outside ต้องอยู่นอก Room',
    };
    $('layerHint').textContent = hints[state.layer];
    for (const button of document.querySelectorAll('[data-layer]')) {
      button.classList.toggle('active', button.dataset.layer === state.layer);
    }
    for (const button of document.querySelectorAll('[data-tool]')) {
      button.classList.toggle('active', button.dataset.tool === state.tool);
    }
  }

  function updatePortalPreview() {
    $('portalEdgePreview').textContent = JSON.stringify({
      portal_id: state.data?.portalId || null,
      edge_uv: currentEdge(),
      inside_cells: state.current ? sortedCells(state.current.portalInside).length : 0,
      outside_cells: state.current ? sortedCells(state.current.portalOutside).length : 0,
    }, null, 2);
  }

  function updateUI() {
    updateMetrics();
    updateDiff();
    updateValidation();
    updateLayerHint();
    updatePortalPreview();
    draw();
  }

  function contentFrame() {
    const { minU, maxU, minV, maxV } = state.viewport;
    const minX = 2 * (minU - (maxV + 1));
    const maxX = 2 * ((maxU + 1) - minV);
    const minY = minU + minV;
    const maxY = (maxU + 1) + (maxV + 1);
    return {
      minX, maxX, minY, maxY,
      centerX: (minX + maxX) / 2,
      centerY: (minY + maxY) / 2,
      width: maxX - minX,
      height: maxY - minY,
    };
  }

  function fitView() {
    if (!state.viewport || !state.view.width || !state.view.height) return;
    const frame = contentFrame();
    const padding = 45;
    const usableWidth = Math.max(100, state.view.width - padding * 2);
    const usableHeight = Math.max(100, state.view.height - padding * 2);
    state.view.baseScale = Math.min(usableWidth / frame.width, usableHeight / frame.height);
    state.view.scale = state.view.baseScale * state.view.zoom;
    state.view.centerX = frame.centerX;
    state.view.centerY = frame.centerY;
    state.view.panX = 0;
    state.view.panY = 0;
    state.view.ready = true;
    draw();
  }

  function setZoom(value) {
    state.view.zoom = clamp(Number(value), 0.5, 3);
    $('zoomRange').value = state.view.zoom;
    state.view.scale = state.view.baseScale * state.view.zoom;
    draw();
  }

  function projectCorner(u, v) {
    return {
      x: state.view.width / 2 + (2 * (u - v) - state.view.centerX) * state.view.scale + state.view.panX,
      y: state.view.height / 2 + (u + v - state.view.centerY) * state.view.scale + state.view.panY,
    };
  }

  function projectCenter(u, v) {
    return {
      x: state.view.width / 2 + (2 * (u - v) - state.view.centerX) * state.view.scale + state.view.panX,
      y: state.view.height / 2 + (u + v + 1 - state.view.centerY) * state.view.scale + state.view.panY,
    };
  }

  function focusSelection() {
    if (!state.selection.size || !state.view.ready) return;
    const cells = [...state.selection].map(parseCell);
    const center = cells.reduce((sum, [u, v]) => ({ u: sum.u + u, v: sum.v + v }), { u: 0, v: 0 });
    const u = center.u / cells.length;
    const v = center.v / cells.length;
    const point = projectCenter(u, v);
    state.view.panX += state.view.width / 2 - point.x;
    state.view.panY += state.view.height / 2 - point.y;
    if (cells.length <= 36 && state.view.zoom < 1.5) {
      state.view.zoom = 1.5;
      $('zoomRange').value = state.view.zoom;
      state.view.scale = state.view.baseScale * state.view.zoom;
      const zoomedPoint = projectCenter(u, v);
      state.view.panX += state.view.width / 2 - zoomedPoint.x;
      state.view.panY += state.view.height / 2 - zoomedPoint.y;
    }
  }

  function screenToCell(event) {
    const rect = state.canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const worldX = ((x - state.view.width / 2 - state.view.panX) / state.view.scale) + state.view.centerX;
    const worldY = ((y - state.view.height / 2 - state.view.panY) / state.view.scale) + state.view.centerY - 1;
    const a = worldX / 2;
    const b = worldY;
    return [Math.round((a + b) / 2), Math.round((b - a) / 2)];
  }

  function drawPolygon(points) {
    const context = state.context;
    context.beginPath();
    context.moveTo(points[0].x, points[0].y);
    for (let index = 1; index < points.length; index += 1) context.lineTo(points[index].x, points[index].y);
    context.closePath();
  }

  function drawCell(u, v, key, diffs, showChanges) {
    const context = state.context;
    const points = [
      projectCorner(u, v),
      projectCorner(u + 1, v),
      projectCorner(u + 1, v + 1),
      projectCorner(u, v + 1),
    ];
    const inRoom = state.current.room.has(key);
    const inside = state.current.portalInside.has(key);
    const outside = state.current.portalOutside.has(key);
    const occupied = state.current.occupancy?.has(key);
    let fill = inRoom ? '#236a57' : '#0d1828';
    if (occupied) fill = '#876a32';
    if (outside) fill = inRoom ? '#ae4d67' : '#9162ce';
    if (inside) fill = occupied ? '#b54961' : '#2d8fe6';
    const selected = state.selection.has(key) || state.previewSelection.has(key);
    const layerDiff = diffs[state.layer];
    const added = showChanges && layerDiff.added.has(key);
    const removed = showChanges && layerDiff.removed.has(key);
    const changed = added || removed;
    if (added) fill = '#18b47e';
    if (removed) fill = '#ce4f5e';
    drawPolygon(points);
    context.fillStyle = fill;
    context.globalAlpha = changed ? 0.97 : inRoom || inside || outside || occupied ? 0.92 : 0.42;
    context.fill();
    context.globalAlpha = 1;
    context.strokeStyle = selected
      ? '#ffe477'
      : changed
        ? (added ? '#a7ffe0' : '#ffb8c0')
        : inRoom ? 'rgba(144, 228, 204, 0.22)' : 'rgba(96, 128, 161, 0.16)';
    context.lineWidth = selected ? 2.5 : changed ? 1.25 : 0.65;
    context.stroke();

    if (selected) {
      drawPolygon(points);
      context.fillStyle = 'rgba(255, 218, 87, 0.52)';
      context.fill();
      context.strokeStyle = '#fff0a6';
      context.lineWidth = 2.5;
      context.stroke();
    }

    if (changed) {
      const center = projectCenter(u, v);
      const markerSize = Math.max(1.8, Math.min(4.8, state.view.scale * 0.22));
      context.beginPath();
      if (added) {
        context.fillStyle = '#e1fff3';
        context.arc(center.x, center.y, markerSize, 0, Math.PI * 2);
        context.fill();
      } else {
        context.strokeStyle = '#ffe3e7';
        context.lineWidth = Math.max(1.4, Math.min(2.6, state.view.scale * 0.15));
        context.moveTo(center.x - markerSize, center.y - markerSize);
        context.lineTo(center.x + markerSize, center.y + markerSize);
        context.moveTo(center.x + markerSize, center.y - markerSize);
        context.lineTo(center.x - markerSize, center.y + markerSize);
        context.stroke();
      }
    }
  }

  function draw() {
    if (!state.context || !state.current || !state.view.ready) return;
    const context = state.context;
    context.clearRect(0, 0, state.view.width, state.view.height);
    context.save();
    context.lineJoin = 'round';
    const diffs = editableDiffs();
    const showChanges = $('showChangesToggle')?.checked !== false;
    for (let v = state.viewport.minV; v <= state.viewport.maxV; v += 1) {
      for (let u = state.viewport.minU; u <= state.viewport.maxU; u += 1) {
        drawCell(u, v, cellKey(u, v), diffs, showChanges);
      }
    }

    const edge = currentEdge();
    if (edge.length === 2) {
      const start = projectCorner(edge[0][0], edge[0][1]);
      const end = projectCorner(edge[1][0], edge[1][1]);
      context.beginPath();
      context.moveTo(start.x, start.y);
      context.lineTo(end.x, end.y);
      context.strokeStyle = '#f6d56d';
      context.lineWidth = 3;
      context.stroke();
    }

    context.restore();
  }

  function resizeCanvas() {
    const rect = state.canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    state.canvas.width = Math.max(1, Math.floor(rect.width * dpr));
    state.canvas.height = Math.max(1, Math.floor(rect.height * dpr));
    state.view.width = rect.width;
    state.view.height = rect.height;
    state.context.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (!state.view.ready) fitView();
    else draw();
  }

  function updateCoordinateReadout(event) {
    if (!state.current || !state.view.ready) return;
    const [u, v] = screenToCell(event);
    $('coordinateReadout').textContent = `UV: ${u}, ${v}${insideViewport([u, v]) ? '' : ' · นอก viewport'}`;
  }

  function onPointerDown(event) {
    if (!state.current || event.button !== 0) return;
    updateCoordinateReadout(event);
    if (state.tool === 'pan') {
      state.drag = { kind: 'pan', x: event.clientX, y: event.clientY };
      state.canvas.setPointerCapture(event.pointerId);
      return;
    }
    const cell = screenToCell(event);
    if (!insideViewport(cell)) return;
    const additive = event.shiftKey;
    const subtractive = event.ctrlKey || event.metaKey;
    if (state.tool === 'cell') {
      modifySelection(cell, additive, subtractive);
      updateMetrics();
      draw();
      return;
    }
    state.drag = {
      kind: 'select',
      start: cell,
      current: cell,
      additive,
      subtractive,
    };
    state.previewSelection = rectangleCells(cell, cell);
    state.canvas.setPointerCapture(event.pointerId);
    draw();
  }

  function onPointerMove(event) {
    updateCoordinateReadout(event);
    if (!state.drag) return;
    if (state.drag.kind === 'pan') {
      state.view.panX += event.clientX - state.drag.x;
      state.view.panY += event.clientY - state.drag.y;
      state.drag.x = event.clientX;
      state.drag.y = event.clientY;
      draw();
      return;
    }
    const cell = screenToCell(event);
    const clamped = [
      clamp(cell[0], state.viewport.minU, state.viewport.maxU),
      clamp(cell[1], state.viewport.minV, state.viewport.maxV),
    ];
    state.drag.current = clamped;
    state.previewSelection = rectangleCells(state.drag.start, clamped);
    draw();
  }

  function onPointerUp(event) {
    if (!state.drag) return;
    if (state.drag.kind === 'select') {
      commitRectangleSelection(state.previewSelection, state.drag.additive, state.drag.subtractive);
      updateMetrics();
      draw();
    }
    state.drag = null;
    if (state.canvas.hasPointerCapture(event.pointerId)) state.canvas.releasePointerCapture(event.pointerId);
  }

  function patchPayload() {
    const room = diffSet(state.base.room, state.current.room);
    const inside = diffSet(state.base.portalInside, state.current.portalInside);
    const outside = diffSet(state.base.portalOutside, state.current.portalOutside);
    const result = state.validation || validate();
    return {
      schema: 'gds.floor_grid_edit_patch.v1',
      floor_id: state.data.floorId,
      canonical_floor_id: state.data.canonicalFloorId,
      grid_profile_id: state.data.gridProfileId,
      source: {
        room_mask: 'WORLD/COMPILED_NAV/floor02_room_cells.json',
        portal_registry: 'WORLD/REGISTRY/portals.json',
      },
      base_counts: {
        room: state.base.room.size,
        portal_inside: state.base.portalInside.size,
        portal_outside: state.base.portalOutside.size,
      },
      changes: {
        room: {
          add_cells_uv: sortedCells(room.added),
          remove_cells_uv: sortedCells(room.removed),
        },
        portal: {
          inside_add_cells_uv: sortedCells(inside.added),
          inside_remove_cells_uv: sortedCells(inside.removed),
          outside_add_cells_uv: sortedCells(outside.added),
          outside_remove_cells_uv: sortedCells(outside.removed),
        },
      },
      resulting_counts: {
        room: state.current.room.size,
        portal_inside: state.current.portalInside.size,
        portal_outside: state.current.portalOutside.size,
      },
      portal_preview: {
        portal_id: state.data.portalId,
        edge_uv: currentEdge(),
        inside_cells_uv: sortedCells(state.current.portalInside),
        outside_cells_uv: sortedCells(state.current.portalOutside),
      },
      impact: {
        canonical_family: 'gameplay.layout.floor02.large',
        affected_floor_count: state.data.floorId === 'floor02' ? 23 : 1,
      },
      validation: {
        status: result.valid ? 'PASS' : 'NEEDS_REVIEW',
        errors: result.errors,
        warnings: result.warnings,
      },
    };
  }

  function snapshotPayload() {
    const result = state.validation || validate();
    return {
      schema: 'gds.floor_grid_snapshot.v1',
      floor_id: state.data.floorId,
      canonical_floor_id: state.data.canonicalFloorId,
      grid_profile_id: state.data.gridProfileId,
      portal_id: state.data.portalId,
      room_cells_uv: sortedCells(state.current.room),
      portal: {
        edge_uv: currentEdge(),
        inside_cells_uv: sortedCells(state.current.portalInside),
        outside_cells_uv: sortedCells(state.current.portalOutside),
      },
      validation: {
        status: result.valid ? 'PASS' : 'NEEDS_REVIEW',
        errors: result.errors,
        warnings: result.warnings,
      },
    };
  }

  function downloadJson(filename, value) {
    const blob = new Blob([`${JSON.stringify(value, null, 2)}\n`], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(link.href), 0);
  }

  function applyPatchPayload(patch) {
    if (!patch || patch.schema !== 'gds.floor_grid_edit_patch.v1') {
      throw new Error('schema ไม่ใช่ gds.floor_grid_edit_patch.v1');
    }
    if (patch.floor_id && patch.floor_id !== state.data.floorId) {
      throw new Error(`patch เป็นของ ${patch.floor_id} แต่ editor เปิด ${state.data.floorId}`);
    }
    const before = snapshot();
    const room = patch.changes?.room || {};
    const portal = patch.changes?.portal || {};
    for (const cell of room.add_cells_uv || []) state.current.room.add(cellKey(...parseCell(cell)));
    for (const cell of room.remove_cells_uv || []) state.current.room.delete(cellKey(...parseCell(cell)));
    for (const cell of portal.inside_add_cells_uv || []) state.current.portalInside.add(cellKey(...parseCell(cell)));
    for (const cell of portal.inside_remove_cells_uv || []) state.current.portalInside.delete(cellKey(...parseCell(cell)));
    for (const cell of portal.outside_add_cells_uv || []) state.current.portalOutside.add(cellKey(...parseCell(cell)));
    for (const cell of portal.outside_remove_cells_uv || []) state.current.portalOutside.delete(cellKey(...parseCell(cell)));
    if (snapshotsEqual(before, snapshot())) return;
    pushHistory(before);
    state.selection.clear();
    showStatus('นำเข้า patch แล้ว กรุณาตรวจ validation ก่อน export ต่อ', 'success');
    updateUI();
  }

  function setLayer(layer) {
    state.layer = layer;
    updateLayerHint();
    draw();
  }

  function setTool(tool) {
    state.tool = tool;
    updateLayerHint();
    state.canvas.style.cursor = tool === 'pan' ? 'grab' : 'crosshair';
  }

  function bindEvents() {
    for (const button of document.querySelectorAll('[data-layer]')) {
      button.addEventListener('click', () => setLayer(button.dataset.layer));
    }
    for (const button of document.querySelectorAll('[data-tool]')) {
      button.addEventListener('click', () => setTool(button.dataset.tool));
    }
    $('openButton').addEventListener('click', () => applyOperation('open'));
    $('closeButton').addEventListener('click', () => applyOperation('close'));
    $('undoButton').addEventListener('click', undo);
    $('redoButton').addEventListener('click', redo);
    $('resetButton').addEventListener('click', reset);
    $('clearSelectionButton').addEventListener('click', () => {
      state.selection.clear();
      state.previewSelection.clear();
      updateUI();
    });
    $('loadProjectButton').addEventListener('click', loadProjectFiles);
    $('roomFile').addEventListener('change', (event) => handleFile('room', event.target.files[0]));
    $('portalFile').addEventListener('change', (event) => handleFile('portal', event.target.files[0]));
    $('occupancyFile').addEventListener('change', (event) => handleFile('occupancy', event.target.files[0]));
    $('patchFile').addEventListener('change', async (event) => {
      try {
        applyPatchPayload(await readJsonFile(event.target.files[0]));
      } catch (error) {
        showStatus(`นำเข้า patch ไม่สำเร็จ: ${error.message}`, 'error');
      }
    });
    $('exportPatchButton').addEventListener('click', () => {
      downloadJson(`${state.data.floorId}_grid_patch.json`, patchPayload());
      showStatus('export patch JSON แล้ว', 'success');
    });
    $('exportSnapshotButton').addEventListener('click', () => {
      downloadJson(`${state.data.floorId}_grid_snapshot.json`, snapshotPayload());
      showStatus('export snapshot JSON แล้ว', 'success');
    });
    $('applyViewportButton').addEventListener('click', () => {
      try {
        setViewport({ minU: $('minU').value, maxU: $('maxU').value, minV: $('minV').value, maxV: $('maxV').value });
        showStatus('ใช้ viewport ใหม่แล้ว', 'success');
      } catch (error) {
        showStatus(error.message, 'error');
      }
    });
    $('fitContentButton').addEventListener('click', () => {
      state.viewport = deriveViewport(Number($('viewportMargin').value) || 8);
      setViewport(state.viewport);
      showStatus('จัด viewport ตามข้อมูลปัจจุบันแล้ว', 'success');
    });
    $('expandViewportButton').addEventListener('click', () => {
      const margin = Math.max(0, Math.trunc(number($('viewportMargin').value, 8)));
      setViewport({
        minU: state.viewport.minU - margin,
        maxU: state.viewport.maxU + margin,
        minV: state.viewport.minV - margin,
        maxV: state.viewport.maxV + margin,
      });
      showStatus(`ขยาย viewport เพิ่มด้านละ ${margin} cells`, 'success');
    });
    $('zoomRange').addEventListener('input', (event) => setZoom(event.target.value));
    $('zoomInButton').addEventListener('click', () => setZoom(state.view.zoom + 0.1));
    $('zoomOutButton').addEventListener('click', () => setZoom(state.view.zoom - 0.1));
    $('centerButton').addEventListener('click', fitView);
    $('showChangesToggle').addEventListener('change', draw);

    state.canvas.addEventListener('contextmenu', (event) => event.preventDefault());
    state.canvas.addEventListener('pointerdown', onPointerDown);
    state.canvas.addEventListener('pointermove', onPointerMove);
    state.canvas.addEventListener('pointerup', onPointerUp);
    state.canvas.addEventListener('pointercancel', onPointerUp);
    state.canvas.addEventListener('pointerleave', () => {
      if (!state.drag) $('coordinateReadout').textContent = 'UV: —';
    });
    state.canvas.addEventListener('wheel', (event) => {
      event.preventDefault();
      setZoom(state.view.zoom + (event.deltaY < 0 ? 0.1 : -0.1));
    }, { passive: false });

    window.addEventListener('keydown', (event) => {
      const modifier = event.ctrlKey || event.metaKey;
      if (modifier && event.key.toLowerCase() === 'z') {
        event.preventDefault();
        if (event.shiftKey) redo(); else undo();
      } else if (modifier && event.key.toLowerCase() === 'y') {
        event.preventDefault();
        redo();
      } else if (event.key.toLowerCase() === 'o' && !event.target.matches('input, textarea, select')) {
        applyOperation('open');
      } else if (event.key.toLowerCase() === 'c' && !event.target.matches('input, textarea, select')) {
        applyOperation('close');
      }
    });
  }

  function initialize() {
    state.canvas = $('gridCanvas');
    state.context = state.canvas.getContext('2d');
    bindEvents();
    if (DEFAULT) {
      state.sources.room = DEFAULT.room_mask;
      state.sources.portal = DEFAULT.portal;
      loadFromSources('bundled F2 defaults');
    } else {
      showStatus('ไม่พบ default data — ใช้ปุ่มนำเข้าไฟล์ Room และ Portal', 'error');
    }
    if ('ResizeObserver' in window) {
      new ResizeObserver(resizeCanvas).observe(state.canvas.parentElement);
    } else {
      window.addEventListener('resize', resizeCanvas);
    }
    resizeCanvas();
    setTool('cell');
    updateUI();
  }

  window.addEventListener('DOMContentLoaded', initialize);
})();
