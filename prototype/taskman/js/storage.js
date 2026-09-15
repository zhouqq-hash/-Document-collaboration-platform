const Storage = {
  // 默认权重
  DEFAULT_WEIGHTS: { w_deadline: 0.4, w_difficulty: 0.2, w_workload: 0.2, w_condition: 0.2 },
  DEFAULT_USER: '胡老师',

  // 读取任务列表
  getTasks() {
    const raw = localStorage.getItem('tm_tasks');
    return raw ? JSON.parse(raw) : [];
  },

  // 保存任务列表
  saveTasks(tasks) {
    localStorage.setItem('tm_tasks', JSON.stringify(tasks));
  },

  // 根据ID获取单个任务
  getTask(id) {
    return this.getTasks().find(t => t.id === id) || null;
  },

  // 新增任务
  addTask(task) {
    const tasks = this.getTasks();
    tasks.push(task);
    this.saveTasks(tasks);
  },

  // 更新任务
  updateTask(id, updates) {
    const tasks = this.getTasks();
    const idx = tasks.findIndex(t => t.id === id);
    if (idx >= 0) {
      tasks[idx] = { ...tasks[idx], ...updates, updated_at: new Date().toISOString() };
      this.saveTasks(tasks);
      return tasks[idx];
    }
    return null;
  },

  // 删除任务
  deleteTask(id) {
    const tasks = this.getTasks().filter(t => t.id !== id);
    this.saveTasks(tasks);
  },

  // 读取权重
  getWeights() {
    const raw = localStorage.getItem('tm_weights');
    return raw ? JSON.parse(raw) : { ...this.DEFAULT_WEIGHTS };
  },

  // 保存权重
  saveWeights(weights) {
    localStorage.setItem('tm_weights', JSON.stringify(weights));
  },

  // 当前用户
  getCurrentUser() {
    return localStorage.getItem('tm_current_user') || this.DEFAULT_USER;
  },

  setCurrentUser(name) {
    localStorage.setItem('tm_current_user', name);
  },

  // 排序日志
  getSortLogs() {
    const raw = localStorage.getItem('tm_sort_logs');
    return raw ? JSON.parse(raw) : [];
  },

  addSortLog(log) {
    const logs = this.getSortLogs();
    logs.push(log);
    localStorage.setItem('tm_sort_logs', JSON.stringify(logs));
  }
};