// 示例数据：首次打开页面时自动写入，方便直接看到算法排序的效果。
// 数据只存在浏览器 localStorage 里，和 Flask 后端没有任何关系。
const Seed = {
  FLAG_KEY: 'tm_seeded',

  // 生成相对今天的日期字符串，n 是天数偏移（负数表示已经过期）
  dateOffset(n) {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() + n);
    return d.toISOString().slice(0, 10);
  },

  samples() {
    const now = new Date().toISOString();
    const base = {
      sort_order: null,
      algo_score: 0,
      created_by: Storage.getCurrentUser(),
      created_at: now,
      updated_at: now,
      completed_at: null
    };

    return [
      {
        ...base,
        id: 'sample_1',
        title: '2026 版专业培养计划定稿送审',
        description: '教务处要求本周内提交最终版，需要完成教研室内部会签。',
        deadline: this.dateOffset(3),
        deadline_type: 'hard',
        difficulty: 5,
        workload: 4,
        condition_note: '',
        is_blocked: false,
        status: 'in_progress',
        doc_status: 'revising'
      },
      {
        ...base,
        id: 'sample_2',
        title: '《数据结构》教学大纲修订',
        description: '按新版培养计划调整学时分配。',
        deadline: this.dateOffset(21),
        deadline_type: 'flexible',
        difficulty: 3,
        workload: 3,
        condition_note: '',
        is_blocked: false,
        status: 'pending',
        doc_status: 'draft'
      },
      {
        ...base,
        id: 'sample_3',
        title: '上学期考核分析报告归档',
        description: '截止日期已经过了，用来观察逾期任务的分数表现。',
        deadline: this.dateOffset(-5),
        deadline_type: 'hard',
        difficulty: 2,
        workload: 2,
        condition_note: '',
        is_blocked: false,
        status: 'reviewing',
        doc_status: 'finalized'
      },
      {
        ...base,
        id: 'sample_4',
        title: '毕业设计题目汇总表',
        description: '被阻塞的任务，算法里条件项记 0 分，排名会被压低。',
        deadline: this.dateOffset(10),
        deadline_type: 'flexible',
        difficulty: 2,
        workload: 3,
        condition_note: '等待教务处下发统一模板',
        is_blocked: true,
        status: 'pending',
        doc_status: null
      }
    ];
  },

  // 首次打开时自动写入；如果已经载入过就跳过，避免覆盖用户自己加的任务
  ensure() {
    if (localStorage.getItem(this.FLAG_KEY)) return false;
    if (Storage.getTasks().length > 0) {
      localStorage.setItem(this.FLAG_KEY, '1');
      return false;
    }
    this.load();
    return true;
  },

  // 覆盖写入示例任务，只在用户主动点击“载入示例数据”时调用
  load() {
    Storage.saveTasks(this.samples());
    localStorage.setItem(this.FLAG_KEY, '1');
  }
};

Seed.ensure();
