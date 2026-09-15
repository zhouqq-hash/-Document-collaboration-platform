document.addEventListener('DOMContentLoaded', () => {
  const params = new URLSearchParams(location.search);
  const id = params.get('id');

  document.getElementById('difficulty').addEventListener('input', e => {
    document.getElementById('difficultyVal').textContent = e.target.value;
  });
  document.getElementById('workload').addEventListener('input', e => {
    document.getElementById('workloadVal').textContent = e.target.value;
  });

  if (id) {
    document.getElementById('pageTitle').textContent = '编辑任务';
    const task = Storage.getTask(id);
    if (task) {
      document.getElementById('taskId').value = task.id;
      document.getElementById('title').value = task.title;
      document.getElementById('description').value = task.description || '';
      document.getElementById('deadline').value = task.deadline || '';
      document.getElementById('deadline_type').value = task.deadline_type || 'flexible';
      document.getElementById('difficulty').value = task.difficulty || 3;
      document.getElementById('difficultyVal').textContent = task.difficulty || 3;
      document.getElementById('workload').value = task.workload || 3;
      document.getElementById('workloadVal').textContent = task.workload || 3;
      document.getElementById('condition_note').value = task.condition_note || '';
      document.getElementById('is_blocked').checked = task.is_blocked || false;
      document.getElementById('status').value = task.status || 'pending';
      document.getElementById('doc_status').value = task.doc_status || '';
    }
  }

  document.getElementById('taskForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const idVal = document.getElementById('taskId').value;
    const data = {
      title: document.getElementById('title').value.trim(),
      description: document.getElementById('description').value.trim(),
      deadline: document.getElementById('deadline').value || null,
      deadline_type: document.getElementById('deadline_type').value,
      difficulty: parseInt(document.getElementById('difficulty').value),
      workload: parseInt(document.getElementById('workload').value),
      condition_note: document.getElementById('condition_note').value.trim(),
      is_blocked: document.getElementById('is_blocked').checked,
      status: document.getElementById('status').value,
      doc_status: document.getElementById('doc_status').value || null
    };

    if (idVal) {
      Storage.updateTask(idVal, data);
    } else {
      Storage.addTask({
        id: 'task_' + Date.now(),
        ...data,
        sort_order: null,
        algo_score: 0,
        created_by: Storage.getCurrentUser(),
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        completed_at: null
      });
    }
    location.href = 'index.html';
  });
});