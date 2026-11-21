export type ProjectCase = {
  id: string;
  title: string;
  industry: string;
  problem: string;
  solution: string;
  outcome: string;
  stack: string[];
  featured?: boolean;
  placeholder?: boolean;
};

/**
 * 首批案例占位：待用户在需求第 9 节确认后替换为真实项目。
 * 请勿在未确认前写入虚构业绩数字或客户名。
 */
export const projectCases: ProjectCase[] = [
  {
    id: 'placeholder-internal-ai',
    title: '企业内部 AI 工具（占位）',
    industry: '待补充行业',
    problem: '待补充：客户遇到的具体痛点与业务背景。',
    solution: '待补充：方案选型、Cursor / Codex 协作方式与关键模块。',
    outcome: '待补充：可量化或可演示的结果（截图 / 视频 / 指标）。',
    stack: ['待补充'],
    featured: true,
    placeholder: true,
  },
  {
    id: 'placeholder-mvp',
    title: 'AI 应用 MVP（占位）',
    industry: '待补充行业',
    problem: '待补充：从想法到可用产品的起点需求。',
    solution: '待补充：迭代节奏、技术栈与交付物形态。',
    outcome: '待补充：上线状态与客户反馈。',
    stack: ['待补充'],
    featured: true,
    placeholder: true,
  },
  {
    id: 'placeholder-system-ai',
    title: '现有系统接入 AI（占位）',
    industry: '待补充行业',
    problem: '待补充：旧系统里缺什么 AI 能力。',
    solution: '待补充：接入方式、数据边界与安全约束。',
    outcome: '待补充：接入后的业务效果。',
    stack: ['待补充'],
    featured: false,
    placeholder: true,
  },
];

export const industries = [
  ...new Set(projectCases.map((item) => item.industry)),
].sort((a, b) => a.localeCompare(b, 'zh-CN'));
