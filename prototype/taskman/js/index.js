let currentSortMode = 'algo';  // algo | manual
let draggedTaskId = null;

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('currentUser').textContent = Storage.getCurrentUser();

  document.getElementById('btnAlgoSort').addEventListener('click', () => {
    currentSortMode = 'algo';
    document.getElementById('sortModeHint').textContent = '当前：算法推荐';
    renderTasks();
  });

  document.getElementById('btnManualSort').addEventListener('click', () => {
    currentSortMode = 'manual';
    document.getElementById('sortModeHint').textContent = '当前：手动排序（拖拽调整）';
    renderTasks();
  });

  document.getElementById('filterStatus').addEventListener('change', renderTasks);
  document.getElementById('filterBlocked').addEventListener('change', renderTasks);

  document.getElementById('btnSampleData').addEventListener('click', () => {
    if (confirm('用示例任务覆盖浏览器里保存的任务数据？')) {
      Seed.load();
      renderTasks();
    }
  });

  renderTasks();
});

function renderTasks() {
  const tasks = Storage.getTasks();
  const weights = Storage.getWeights();
  const filterStatus = document.getElementById('filterStatus').value;
  const filterBlocked = document.getElementById('filterBlocked').value;

  // 筛选
  let filtered = tasks.filter(t => {
    if (filterStatus && t.status !== filterStatus) return false;
    if (filterBlocked === 'blocked' && !t.is_blocked) return false;
    if (filterBlocked === 'normal' && t.is_blocked) return false;
    return true;
  });

  // 根据模式选择排序方式（两种排序完全独立）
  let sorted;
  if (currentSortMode === 'algo') {
    sorted = Algo.sortTasks(filtered, weights);          // 纯算法排序
  } else {
    sorted = Algo.sortTasksManual(filtered, weights);    // 纯手动排序
  }

  const container = document.getElementById('taskList');
  if (sorted.length === 0) {
    container.innerHTML = '<div class="alert alert-info">暂无任务，点击右上角“新建任务”开始。</div>';
    return;
  }

  container.innerHTML = sorted.map(t => renderTaskCard(t)).join('');

  // 绑定拖拽事件（仅手动模式）
  if (currentSortMode === 'manual') {
    bindDragEvents();
  }

  // 绑定状态切换按钮
  document.querySelectorAll('[data-action="toggle-status"]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const id = btn.dataset.id;
      const task = Storage.getTask(id);
      const nextStatus = {
        pending: 'in_progress',
        in_progress: 'reviewing',
        reviewing: 'completed',
        completed: 'archived',
        archived: 'pending'
      };
      const newStatus = nextStatus[task.status] || 'pending';
      const updates = { status: newStatus };
      if (newStatus === 'completed') updates.completed_at = new Date().toISOString();
      Storage.updateTask(id, updates);
      renderTasks();
    });
  });

  // 绑定删除按钮
  document.querySelectorAll('[data-action="delete"]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (confirm('确定删除此任务？')) {
        Storage.deleteTask(btn.dataset.id);
        renderTasks();
      }
    });
  });
}

function renderTaskCard(task) {
  const statusMap = {
    pending: { label: '未开始', cls: 'secondary' },
    in_progress: { label: '进行中', cls: 'primary' },
    reviewing: { label: '待审核', cls: 'warning' },
    completed: { label: '已完成', cls: 'success' },
    archived: { label: '已归档', cls: 'dark' }
  };
  const st = statusMap[task.status] || statusMap.pending;
  const deadlineTypeLabel = task.deadline_type === 'hard' ? '🔴 硬性' : '🟡 弹性';
  const blockedLabel = task.is_blocked ? '<span class="badge bg-danger ms-1">阻塞</span>' : '';
  const docStatusMap = { draft: '草稿', revising: '修订中', finalized: '已定稿' };
  const docLabel = task.doc_status ? `<span class="badge bg-info ms-1">${docStatusMap[task.doc_status]}</span>` : '';

  return `
    <div class="card mb-2 task-card" draggable="${currentSortMode === 'manual'}" data-id="${task.id}">
      <div class="card-body py-2">
        <div class="d-flex justify-content-between align-items-start">
          <div class="flex-grow-1">
            ${currentSortMode === 'manual' ? '<span class="drag-handle me-2" style="cursor:grab;">≡</span>' : ''}
            <a href="detail.html?id=${task.id}" class="text-decoration-none fw-bold">${task.title}</a>
            <span class="badge bg-${st.cls} ms-2">${st.label}</span>
            ${blockedLabel}
            ${docLabel}
          </div>
          <div class="text-end small text-muted" style="min-width:180px;">
            <div>${task.deadline ? `截止：${task.deadline}（${deadlineTypeLabel}）` : '无截止日期'}</div>
            <div>难度：${task.difficulty} / 工作量：${task.workload}</div>
            <div>优先级分：${task.algo_score.toFixed(2)}</div>
          </div>
        </div>
        ${task.condition_note ? `<div class="small text-muted mt-1">条件：${task.condition_note}</div>` : ''}
        <div class="mt-2">
          <button class="btn btn-outline-primary btn-sm" data-action="toggle-status" data-id="${task.id}">推进状态</button>
          <a href="edit.html?id=${task.id}" class="btn btn-outline-secondary btn-sm">编辑</a>
          <button class="btn btn-outline-danger btn-sm" data-action="delete" data-id="${task.id}">删除</button>
        </div>
      </div>
    </div>
  `;
}

function bindDragEvents() {
  document.querySelectorAll('.task-card').forEach(card => {
    card.addEventListener('dragstart', (e) => {
      draggedTaskId = card.dataset.id;
      card.classList.add('dragging');
    });
    card.addEventListener('dragend', () => {
      card.classList.remove('dragging');
      draggedTaskId = null;
    });
    card.addEventListener('dragover', (e) => {
      e.preventDefault();
    });
    card.addEventListener('drop', (e) => {
      e.preventDefault();
      if (!draggedTaskId || draggedTaskId === card.dataset.id) return;
      reorderTasks(draggedTaskId, card.dataset.id);
    });
  });
}

function reorderTasks(fromId, toId) {
  const tasks = Storage.getTasks();
  const weights = Storage.getWeights();

  // 使用手动排序作为当前显示顺序的基础
  const sorted = Algo.sortTasksManual(tasks, weights);

  const fromIdx = sorted.findIndex(t => t.id === fromId);
  const toIdx = sorted.findIndex(t => t.id === toId);
  if (fromIdx < 0 || toIdx < 0) return;

  const [moved] = sorted.splice(fromIdx, 1);
  sorted.splice(toIdx, 0, moved);

  // 写入 sort_order（独立存储，不影响 algo_score）
  sorted.forEach((t, idx) => {
    Storage.updateTask(t.id, { sort_order: idx });
    Storage.addSortLog({
      task_id: t.id,
      algo_order: null,
      manual_order: idx,
      adjusted_by: Storage.getCurrentUser(),
      adjusted_at: new Date().toISOString()
    });
  });

  renderTasks();
}
