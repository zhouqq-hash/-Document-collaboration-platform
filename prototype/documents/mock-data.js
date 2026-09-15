const MOCK_CATEGORIES = [
  { id: 1, name: "专业培养计划", description: "各专业人才培养方案与培养目标" },
  { id: 2, name: "教学大纲", description: "课程教学大纲与教学要求" },
  { id: 3, name: "毕业设计要求", description: "毕业设计选题、要求和规范" },
  { id: 4, name: "考核分析报告", description: "课程考核与达成度分析" },
  { id: 5, name: "其他", description: "其他教学管理文档" },
];

const MOCK_DOCUMENTS = [
  {
    id: 101,
    title: "2026级计算机科学与技术专业培养计划",
    categoryId: 1,
    owner: { username: "teacher", name: "胡军成", role: "teacher" },
    updatedAt: "2026-09-12 15:30",
  },
  {
    id: 102,
    title: "数据结构课程教学大纲",
    categoryId: 2,
    owner: { username: "teacher", name: "胡军成", role: "teacher" },
    updatedAt: "2026-09-10 10:12",
  },
  {
    id: 103,
    title: "2026届本科毕业设计工作要求",
    categoryId: 3,
    owner: { username: "admin", name: "管理员", role: "admin" },
    updatedAt: "2026-09-08 09:05",
  },
];

const MOCK_VERSIONS = {
  101: [
    {
      id: 1003,
      versionNumber: 3,
      filename: "2026级培养计划_v3.pdf",
      changelog: "根据评估反馈调整学分结构",
      uploader: "胡军成",
      createdAt: "2026-09-12 15:30",
    },
    {
      id: 1002,
      versionNumber: 2,
      filename: "2026级培养计划_v2.pdf",
      changelog: "补充实践教学环节说明",
      uploader: "胡军成",
      createdAt: "2026-09-05 11:20",
    },
    {
      id: 1001,
      versionNumber: 1,
      filename: "2026级培养计划_v1.pdf",
      changelog: "初始版本",
      uploader: "胡军成",
      createdAt: "2026-08-28 09:00",
    },
  ],
  102: [
    {
      id: 2002,
      versionNumber: 2,
      filename: "数据结构教学大纲_v2.pdf",
      changelog: "更新实验课时",
      uploader: "胡军成",
      createdAt: "2026-09-10 10:12",
    },
    {
      id: 2001,
      versionNumber: 1,
      filename: "数据结构教学大纲_v1.pdf",
      changelog: "初始版本",
      uploader: "胡军成",
      createdAt: "2026-09-01 14:00",
    },
  ],
  103: [
    {
      id: 3001,
      versionNumber: 1,
      filename: "2026届本科毕业设计工作要求_v1.pdf",
      changelog: "初始版本",
      uploader: "管理员",
      createdAt: "2026-09-08 09:05",
    },
  ],
};

const DEFAULT_USER = {
  username: "admin",
  name: "管理员",
  role: "admin",
};
