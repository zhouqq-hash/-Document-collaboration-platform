document.addEventListener('DOMContentLoaded', () => {
  const id = new URLSearchParams(location.search).get('id');
  const task = Storage.getTask(id);
  if (!task) {
    document.getElementById('detailContent').innerHTML = '<div class="alert alert-danger">任务不存在</div>';
    return;
  }
  const weights = Storage.getWeights();
  const score = Algo.calcScore(task, weights);
  const statusMap = {
    pending: '未开始', in_progress: '进行中', reviewing: '待审核',
    completed: '已完成', archived: '已归档'
  };
  const docMap = { draft: '草稿', revising: '修订中', finalized: '已定稿' };

  document.getElementById('detailContent').innerHTML = `
    <div class="card">
      <div class="card-header d-flex justify-content-between">
        <h5 class="mb-0">${task.title}</h5>
        <span class="badge bg-primary">${statusMap[task.status]}</span>
      </div>
      <div class="card-body">
        <p><strong>描述：</strong>${task.description || '（无）'}</p>
        <p><strong>截止日期：</strong>${task.deadline || '（无）'} ${task.deadline_type === 'hard' ? '🔴 硬性' : '🟡 弹性'}</p>
        <p><strong>难度：</strong>${task.difficulty} / 5</p>
        <p><strong>工作量：</strong>${task.workload} / 5</p>
        <p><strong>所需条件：</strong>${task.condition_note || '（无）'} ${task.is_blocked ? '<span class="badge bg-danger">阻塞中</span>' : ''}</p>
        <p><strong>文档状态：</strong>${task.doc_status ? docMap[task.doc_status] : '（无）'}</p>
        <p><strong>综合优先级分：</strong>${score.toFixed(2)}</p>
        <p><strong>创建人：</strong>${task.created_by}</p>
        <p><strong>创建时间：</strong>${new Date(task.created_at).toLocaleString()}</p>
        <p><strong>更新时间：</strong>${new Date(task.updated_at).toLocaleString()}</p>
        ${task.completed_at ? `<p><strong>完成时间：</strong>${new Date(task.completed_at).toLocaleString()}</p>` : ''}
      </div>
      <div class="card-footer">
        <a href="edit.html?id=${task.id}" class="btn btn-primary btn-sm">编辑</a>
        <a href="index.html" class="btn btn-secondary btn-sm">返回</a>
      </div>
    </div>
  `;
});