const Algo = {
  // 计算单个任务的综合优先级分数
  calcScore(task, weights) {
    // 1. 紧迫度：越接近截止日期分数越高
    let urgency = 0;
    if (task.deadline) {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const dl = new Date(task.deadline);
      const daysLeft = Math.ceil((dl - today) / (1000 * 60 * 60 * 24));
      urgency = Math.max(0, 1 - daysLeft / 30);  // 30天内线性衰减
      if (task.deadline_type === 'hard') urgency *= 1.5;  // 硬性日期额外加权
      urgency = Math.min(urgency, 1.5);  // 上限
    }

    // 2. 难度、工作量归一化
    const difficulty = (task.difficulty || 3) / 5;
    const workload = (task.workload || 3) / 5;

    // 3. 条件依赖：阻塞任务直接降为0
    const condition = task.is_blocked ? 0 : 1;

    // 4. 加权求和
    return (
      weights.w_deadline * urgency +
      weights.w_difficulty * difficulty +
      weights.w_workload * workload +
      weights.w_condition * condition
    );
  },

  // 算法排序：纯按 algo_score 降序，完全忽略 sort_order
  sortTasks(tasks, weights) {
    const scored = tasks.map(t => ({
      ...t,
      algo_score: this.calcScore(t, weights)
    }));

    scored.sort((a, b) => {
      // 已完成/已归档的任务排最后
      const aDone = ['completed', 'archived'].includes(a.status) ? 1 : 0;
      const bDone = ['completed', 'archived'].includes(b.status) ? 1 : 0;
      if (aDone !== bDone) return aDone - bDone;

      // 纯按算法分数降序
      return b.algo_score - a.algo_score;
    });

    return scored;
  },

  // 手动排序：仅按 sort_order 排，完全忽略 algo_score
  sortTasksManual(tasks, weights) {
    const scored = tasks.map(t => ({
      ...t,
      algo_score: this.calcScore(t, weights)
    }));

    scored.sort((a, b) => {
      // 已完成/已归档的任务排最后
      const aDone = ['completed', 'archived'].includes(a.status) ? 1 : 0;
      const bDone = ['completed', 'archived'].includes(b.status) ? 1 : 0;
      if (aDone !== bDone) return aDone - bDone;

      // 仅按手动顺序排
      const aOrder = a.sort_order ?? 9999;
      const bOrder = b.sort_order ?? 9999;
      return aOrder - bOrder;
    });

    return scored;
  }
};