document.addEventListener('DOMContentLoaded', () => {
  // 权重字段与对应的显示标签 ID 映射（驼峰命名）
  const WEIGHT_FIELDS = [
    { key: 'w_deadline',   labelId: 'wDeadlineVal' },
    { key: 'w_difficulty', labelId: 'wDifficultyVal' },
    { key: 'w_workload',   labelId: 'wWorkloadVal' },
    { key: 'w_condition',  labelId: 'wConditionVal' }
  ];

  const totalWeightEl = document.getElementById('totalWeight');
  const totalWeightHint = document.getElementById('totalWeightHint');
  const btnSave = document.getElementById('btnSave');

  // 初始化：从存储读取权重
  const savedWeights = Storage.getWeights();
  WEIGHT_FIELDS.forEach(({ key, labelId }) => {
    const input = document.getElementById(key);
    const label = document.getElementById(labelId);
    input.value = savedWeights[key];
    label.textContent = savedWeights[key].toFixed(1);
    input.addEventListener('input', () => {
      label.textContent = parseFloat(input.value).toFixed(1);
      updateTotalAndValidate();
    });
  });

  // 初始化用户名
  document.getElementById('currentUser').value = Storage.getCurrentUser();

  // 实时计算总权重并校验
  function updateTotalAndValidate() {
    let total = 0;
    WEIGHT_FIELDS.forEach(({ key }) => {
      total += parseFloat(document.getElementById(key).value);
    });
    total = Math.round(total * 10) / 10;  // 消除浮点误差
    totalWeightEl.textContent = total.toFixed(1);

    if (Math.abs(total - 1.0) < 0.001) {
      totalWeightHint.innerHTML = '<span class="text-success">✅ 总权重为 1.0，可以保存</span>';
      btnSave.disabled = false;
    } else {
      totalWeightHint.innerHTML = `<span class="text-danger">⚠️ 总权重为 ${total.toFixed(1)}，必须调整为 1.0 才能保存</span>`;
      btnSave.disabled = true;
    }
  }

  // 首次加载时校验一次
  updateTotalAndValidate();

  // 提交保存
  document.getElementById('weightForm').addEventListener('submit', (e) => {
    e.preventDefault();

    // 二次校验
    let total = 0;
    WEIGHT_FIELDS.forEach(({ key }) => {
      total += parseFloat(document.getElementById(key).value);
    });
    if (Math.abs(total - 1.0) > 0.001) {
      alert('总权重必须为 1.0 才能保存');
      return;
    }

    // 保存权重
    Storage.saveWeights({
      w_deadline:   parseFloat(document.getElementById('w_deadline').value),
      w_difficulty: parseFloat(document.getElementById('w_difficulty').value),
      w_workload:   parseFloat(document.getElementById('w_workload').value),
      w_condition:  parseFloat(document.getElementById('w_condition').value)
    });

    // 保存当前用户
    const user = document.getElementById('currentUser').value.trim();
    Storage.setCurrentUser(user || Storage.DEFAULT_USER);

    alert('已保存');
    location.href = 'index.html';
  });
});